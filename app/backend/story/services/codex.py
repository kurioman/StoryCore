"""Codex (v1.8): the in-story encyclopedia of characters and places the protagonist has discovered.

Characters come from the per-story discovery roster (heard of / met / known, see discovery.py), plus anyone who has
been in a scene. Places are derived from the story itself, so they follow branches exactly like everything else:
a place is "visited" when it was the scene's location on this branch, "heard of" when a reply on the branch's path
names it. Undiscovered entries are counted and shown as locked "???" cards without their name or id (no spoilers).

Only public lore is used: narrator-only "hidden" notes are removed at import and never reach this module.
A pack can switch the codex off (pack.json "codex": false) and leave a record out ("codex": false on the record).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LoreEntity, MessageBranch, Story, StoryState, TurnAnalysis, World
from . import assets as assets_svc
from . import discovery, story_tree
from .entities import EntityIndex

CHAR_RANK = {"locked": 0, "rumored": 1, "encountered": 2, "known": 3}
PLACE_RANK = {"locked": 0, "rumored": 1, "visited": 2}
# public lore fields shown per level (the summary is shown from "encountered" / "visited")
CHAR_BASIC = ("type", "title", "race")
CHAR_MET = ("affiliation", "rank", "occupation", "department", "year", "age", "appearance")
CHAR_KNOWN = ("personality_traits", "speech", "likes", "dislikes", "hobbies")
PLACE_FIELDS = ("type", "location", "region", "map_hint")


def enabled(world: World | None) -> bool:
    pack = ((world.data_json or {}).get("pack") or {}) if world else {}
    raw = pack.get("codex", True) if isinstance(pack, dict) else True
    if isinstance(raw, dict):
        raw = raw.get("enabled", True)
    return raw is not False


def _fields(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for k in keys:
        v = data.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (str, int, float)) or (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            out[k] = v
        elif isinstance(v, dict) and all(isinstance(x, (str, int, float)) for x in v.values()):
            out[k] = v
    return out


def _states(db: Session, branch: MessageBranch) -> list[dict[str, Any]]:
    lineage = story_tree.lineage_branch_ids(db, branch)
    return [r.state_json or {} for r in db.scalars(select(StoryState).where(StoryState.branch_id.in_(lineage)))]


def build(db: Session, story: Story, branch: MessageBranch, index: EntityIndex) -> dict[str, Any]:
    world = db.get(World, story.world_id) if story.world_id else None
    if not enabled(world) or world is None:
        return {"enabled": False, "characters": [], "places": [], "counts": {}}
    ents = [e for e in db.scalars(select(LoreEntity).where(LoreEntity.world_id == world.id,
                                                             LoreEntity.category.in_(("character", "location"))))
            if (e.data_json or {}).get("codex") is not False]
    path = story_tree.path_messages(db, branch.head_message_id)
    replies = [m for m in path if m.role == "assistant" and m.kind == "story" and m.content]
    seq = {m.id: m.seq for m in path}
    states = _states(db, branch)

    # ---- characters: discovery roster, plus anyone who was present in a scene
    status: dict[str, str] = {cid: r.status for cid, r in discovery.roster(db, story, branch).items()}
    for st in states:
        for cid in (st.get("scene") or {}).get("present") or []:
            if CHAR_RANK.get(status.get(cid, "locked"), 0) < CHAR_RANK["encountered"]:
                status[cid] = "encountered"
    first: dict[str, dict[str, Any]] = {}
    for r in discovery.history(db, story, branch):
        if r.status in ("encountered", "known") and r.character_id not in first:
            first[r.character_id] = {"seq": seq.get(r.source_message_id), "evidence": r.evidence or ""}
    seen_slots: dict[str, set[int]] = {}
    ids = [m.id for m in replies]
    if ids:
        for row in db.scalars(select(TurnAnalysis).where(TurnAnalysis.message_id.in_(ids), TurnAnalysis.status == "succeeded")):
            for b in row.beats_json or []:
                if b.get("beat") in ("speaking", "reacting") and b.get("character_id"):
                    seen_slots.setdefault(b["character_id"], set()).add(int(b.get("expression") or 1))
    pmap = assets_svc.portrait_map(db, world.id)

    characters = []
    for e in sorted((e for e in ents if e.category == "character"), key=lambda e: e.name.lower()):
        st = status.get(e.entity_id, "locked")
        if st == "locked":
            characters.append({"status": "locked"})
            continue
        data = e.data_json or {}
        item: dict[str, Any] = {"id": e.entity_id, "name": e.name, "status": st, "fields": _fields(data, CHAR_BASIC)}
        slots = pmap.get(e.entity_id, {})
        if st in ("encountered", "known"):
            item["summary"] = e.summary
            item["fields"].update(_fields(data, CHAR_MET))
            seen = sorted(s for s in (seen_slots.get(e.entity_id, set()) | {1}) if s in slots) or sorted(slots)[:1]
            item["portrait"] = slots.get(1) or (slots[seen[0]] if seen else None)
            item["expressions"] = {str(s): slots[s] for s in seen}
            item["expressions_total"] = len(slots)
            item["first_met"] = first.get(e.entity_id)
        if st == "known":
            item["fields"].update(_fields(data, CHAR_KNOWN))
        characters.append(item)

    # ---- places: visited (scene location on this branch) or heard of (named in a reply on the path)
    places_idx = EntityIndex([en for en in index.entities.values() if en.category == "location"])
    pstatus: dict[str, str] = {}
    for st in states:
        loc = str((st.get("scene") or {}).get("location") or "")
        for pid in ([places_idx.resolve(loc)] if places_idx.resolve(loc) else places_idx.find_mentions(loc, ("location",))):
            pstatus[pid] = "visited"
    for m in replies:
        for pid in places_idx.find_mentions(m.content, ("location",)):
            pstatus.setdefault(pid, "rumored")
    places = []
    for e in sorted((e for e in ents if e.category == "location"), key=lambda e: e.name.lower()):
        st = pstatus.get(e.entity_id, "locked")
        if st == "locked":
            places.append({"status": "locked"})
            continue
        item = {"id": e.entity_id, "name": e.name, "status": st, "fields": _fields(e.data_json or {}, ("type",))}
        if st == "visited":
            item["summary"] = e.summary
            item["fields"].update(_fields(e.data_json or {}, PLACE_FIELDS))
        places.append(item)

    # discovered entries first (alphabetical); locked cards after them, so their position gives nothing away
    characters = [c for c in characters if c["status"] != "locked"] + [c for c in characters if c["status"] == "locked"]
    places = [p for p in places if p["status"] != "locked"] + [p for p in places if p["status"] == "locked"]

    def count(items: list[dict[str, Any]]) -> dict[str, int]:
        return {"found": sum(1 for i in items if i["status"] != "locked"), "total": len(items)}

    return {"enabled": True, "characters": characters, "places": places,
            "counts": {"characters": count(characters), "places": count(places)}}
