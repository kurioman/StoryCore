"""Phase 2, step 4: the info table the narrator writes at the end of each reply.

The narrator ends its reply with a short block of plain lines saying what changed (place, time, who is here,
relationships, HP, mana, conditions, items, moods, important facts):

    <info>
    place: infirmary
    time: night
    present: Lilia, Sera
    Lilia: trust +1 (Kurio saved the group)
    hp: -10
    condition: +bruised
    mood: Lilia 3, Sera 1
    fact: Mirabel was stabbed by a cultist in the old library tower
    </info>

The block never reaches the story text (it is taken out while the reply streams, services/runtime.py). The app reads
it, checks every line and records it in the story state the screens already show; each line is shown to the player
under the reply, as a reminder and as a safety net: a line can be cancelled or corrected. Plain lines instead of JSON:
a 12B local model writes them reliably, and they cost fewer tokens. When the block is there, the separate scene
analysis request is not sent any more (services: main.after_generation).

Checks: unknown names are ignored, HP and mana stay between 0 and their maximum, a relationship moves by at most 2 per
axis and per reply (more becomes a proposal to review, as with the scene analysis), and everything from one reply is
undone when that reply is regenerated or the player cancels the line.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import Message, Story
from . import settings_service, state_service, story_tree

log = logging.getLogger(__name__)

OPEN_TAG = re.compile(r"<\s*info\s*>", re.I)
CLOSE_TAG = re.compile(r"<\s*/\s*info\s*>", re.I)
# a model that forgets the tags but writes the block anyway ("Info:" then lines "key: value" to the end)
LOOSE_BLOCK = re.compile(r"\n\s*(?:\*\*)?\[?\s*info(?:\s+table)?\s*\]?(?:\*\*)?\s*:?\s*\n((?:[ \t]*[-*•]?[ \t]*[^\n:]{1,40}:[^\n]*\n?)+)\s*$",
                         re.I)
MAX_LINES = 20
REL_MAX = 2  # per axis and per reply; more becomes a proposal
AXES = {"trust": "trust", "affection": "affection", "respect": "respect", "familiarity": "familiarity",
        "rivalry": "rivalry", "fear": "fear", "confiance": "trust", "affinité": "affection", "affinite": "affection",
        "respect ": "respect", "familiarité": "familiarity", "rivalité": "rivalry", "peur": "fear"}
KEYS = {"place": "place", "location": "place", "lieu": "place", "time": "time", "heure": "time", "moment": "time",
        "days": "days", "day": "days", "jours": "days", "jour": "days", "present": "present", "présents": "present",
        "presents": "present", "here": "present", "hp": "hp", "pv": "hp", "health": "hp", "mana": "mana", "aura": "mana",
        "condition": "condition", "conditions": "condition", "état": "condition", "etat": "condition", "status": "condition",
        "item": "item", "items": "item", "inventory": "item", "objet": "item", "mood": "mood", "moods": "mood",
        "humeur": "mood", "fact": "fact", "facts": "fact", "fait": "fact"}

INSTRUCTION = (
    "After the story, add the info block: one line per thing that changed in this reply, nothing else. The player sees "
    "it and can correct it.\n"
    "<info>\n"
    "place: <where the scene is now, if it changed>\n"
    "time: <morning, noon, afternoon, evening, night or HH:MM, if it changed>\n"
    "days: +1 <only when a new day starts>\n"
    "present: <names of everyone here now, if it changed>\n"
    "<Name>: <trust|affection|respect|familiarity|rivalry|fear> <+1 or -1, at most ±2> (<short reason>)  "
    "<how that character now regards {name}>\n"
    "hp: <-10 or +5>   mana: <-15>   condition: <+bruised or -bruised>   item: <+healing potion or -healing potion>\n"
    "mood: <Name> <1 neutral|2 happy|3 sad|4 angry|5 disgust|6 love/shy>, ...\n"
    "fact: <one important new fact, if any>\n"
    "</info>\n"
    "Write <info></info> when nothing changed. Never mention the block in the story."
)
REMINDER = " End with the <info> block."


def enabled(db: Session) -> bool:
    return settings_service.get(db, "info_table") is not False


# --------------------------------------------------------------------------- streaming
class InfoFilter:
    """Takes the <info> block out of a streamed reply. ``feed`` returns what the player may see."""

    def __init__(self) -> None:
        self.buf = ""
        self.hidden: str | None = None

    def feed(self, piece: str) -> str:
        if self.hidden is not None:
            self.hidden += piece
            return ""
        self.buf += piece
        m = OPEN_TAG.search(self.buf)
        if m:
            out, self.hidden, self.buf = self.buf[:m.start()], self.buf[m.end():], ""
            return out
        i = self.buf.rfind("<")
        if i != -1 and len(self.buf) - i < 9 and re.fullmatch(r"<\s*(?:i(?:n(?:f(?:o\s*)?)?)?)?", self.buf[i:], re.I):
            out, self.buf = self.buf[:i], self.buf[i:]  # maybe the start of "<info>": held back
            return out
        out, self.buf = self.buf, ""
        return out

    def flush(self) -> str:
        out, self.buf = self.buf, ""
        return out if self.hidden is None else ""

    @property
    def block(self) -> str | None:
        if self.hidden is None:
            return None
        m = CLOSE_TAG.search(self.hidden)
        return self.hidden[:m.start()] if m else self.hidden


def split_loose(text: str) -> tuple[str, str | None]:
    """A block written without its tags at the very end of the reply ("Info:" and "key: value" lines)."""
    m = LOOSE_BLOCK.search(text)
    if not m:
        return text, None
    lines = [l for l in m.group(1).splitlines() if l.strip()]
    known = sum(1 for l in lines if _key(l.split(":", 1)[0]) in KEYS.values())
    if known < max(1, len(lines) // 2):
        return text, None
    return text[:m.start()].rstrip(), m.group(1)


# --------------------------------------------------------------------------- parsing
def _key(k: str) -> str:
    k = re.sub(r"^[\s\-*•]+", "", k).strip().strip("*").strip().casefold()
    return KEYS.get(k, k)


def _signed(v: str) -> int | None:
    m = re.search(r"([+\-−]?)\s*(\d{1,4})", v)
    if not m:
        return None
    n = int(m.group(2))
    return -n if m.group(1) in ("-", "−") else n


def parse(block: str | None) -> list[dict[str, Any]]:
    """The lines of a block as {"kind", ..., "text"} (relationship lines keep the raw name: resolved later)."""
    out: list[dict[str, Any]] = []
    for raw in (block or "").splitlines():
        line = raw.strip()
        if not line or ":" not in line or len(out) >= MAX_LINES:
            continue
        k, v = line.split(":", 1)
        key, v = _key(k), v.strip()
        if not v or v.lower() in ("none", "no change", "unchanged", "-", "n/a", "aucun", "rien"):
            continue
        if key == "place":
            out.append({"kind": "place", "value": v[:80], "text": line})
        elif key == "time":
            out.append({"kind": "time", "value": v[:40], "text": line})
        elif key == "days":
            n = _signed(v)
            if n:
                out.append({"kind": "days", "value": n, "text": line})
        elif key == "present":
            names = [n.strip() for n in re.split(r",|\band\b|\bet\b", v) if n.strip()]
            out.append({"kind": "present", "names": names[:12], "text": line})
        elif key in ("hp", "mana"):
            n = _signed(v)
            if n:
                out.append({"kind": "stat", "stat": key, "delta": n, "text": line})
        elif key in ("condition", "item"):
            for part in [p.strip() for p in v.split(",") if p.strip()][:4]:
                remove = part.startswith(("-", "−"))
                name = part.lstrip("+-− ").strip()
                if name:
                    out.append({"kind": key, "name": name[:60], "remove": remove, "text": line})
        elif key == "mood":
            for part in [p.strip() for p in v.split(",") if p.strip()][:8]:
                m = re.match(r"(.+?)\s*[:=]?\s*([1-6])\b", part)
                if m:
                    out.append({"kind": "mood", "who": m.group(1).strip(), "slot": int(m.group(2)), "text": line})
        elif key == "fact":
            out.append({"kind": "fact", "value": v[:240], "text": line})
        else:  # "<Name>: trust +1, affection +1 (reason)"
            reason = ""
            rm = re.search(r"\(([^)]*)\)\s*$", v)
            if rm:
                reason, v = rm.group(1).strip(), v[:rm.start()]
            for part in [p.strip() for p in re.split(r",|;", v) if p.strip()][:3]:
                am = re.match(r"([A-Za-zÀ-ÿ]+)\s*([+\-−]?\s*\d+)", part)
                if am and am.group(1).casefold() in AXES:
                    out.append({"kind": "relationship", "who": k.strip().strip("*-• "), "axis": AXES[am.group(1).casefold()],
                                "delta": _signed(am.group(2)), "reason": reason[:160], "text": line})
    return out


# --------------------------------------------------------------------------- applying
def _label(item: dict[str, Any], index) -> str:
    k = item["kind"]
    if k == "relationship":
        return f"{item.get('name') or item['who']}: {item['axis']} {item['delta']:+d}" + (f" ({item['reason']})" if item.get("reason") else "")
    if k == "stat":
        return f"{item['stat'].upper()} {item['delta']:+d}"
    if k in ("condition", "item"):
        return f"{k}: {'-' if item['remove'] else '+'}{item['name']}"
    if k == "present":
        return "present: " + ", ".join(item.get("resolved_names") or item["names"])
    if k == "mood":
        return f"mood: {item.get('name') or item['who']} {item['slot']}"
    if k == "days":
        return f"days: {item['value']:+d}"
    return f"{k}: {item['value']}"


def _stat_row(state: dict[str, Any], key: str) -> dict[str, Any] | None:
    words = {"hp": ("hp", "health", "pv", "vie"), "mana": ("mana", "aura", "mp")}[key]
    for s in state.get("stats") or []:
        lab = str(s.get("label") or "").casefold()
        if any(re.search(rf"\b{w}\b", lab) for w in words):
            return s
    return None


def revert(db: Session, story: Story, branch, m: Message, why: str) -> None:
    """Undo what an earlier reading of this reply's block changed (stats, conditions, items, facts)."""
    from . import relationships, scene_cast, world_state
    from ..models import StoryEvent
    md = dict(m.generation_metadata_json or {})
    info = md.get("info_table") or {}
    undo = info.get("undo") or []
    if undo:
        row = state_service.current(db, branch.id)
        state = state_service.normalize(json.loads(json.dumps(row.state_json)) if row else {})
        done = []
        for op in reversed(undo):
            try:
                state, summary = state_service.apply_change(state, op["kind"], op["payload"], source="info_table_undo",
                                                            message_id=m.id)
                done.append(summary)
            except ValueError:
                continue
        if done:
            state_service.save(db, story.id, branch.id, state, source="info_table_undo",
                               summary=f"Info table undone ({why}): " + "; ".join(done), message_id=m.id)
    for e in db.query(StoryEvent).filter(StoryEvent.story_id == story.id, StoryEvent.dedupe_key.like(f"info:{m.id}:%")):
        db.delete(e)
    relationships.revert_message(db, story, branch, {m.id}, why)
    world_state.revert_message(db, story, branch, {m.id}, why)
    scene_cast.revert_message(db, story, branch, {m.id}, why)
    info["undo"] = []
    md["info_table"] = info
    m.generation_metadata_json = md


def apply(db: Session, story: Story, m: Message, *, block: str | None = None, edited: bool = False) -> dict[str, Any] | None:
    """Read, check and record one reply's block (idempotent: an earlier reading of the same reply is undone first).
    Returns the info record stored with the reply, or None when the reply has no block."""
    from . import discovery, relationships, scene_cast, world_state
    from .entities import build_index
    from ..models import StoryEvent

    md = dict(m.generation_metadata_json or {})
    info = dict(md.get("info_table") or {})
    if block is None:
        block = info.get("raw") if "raw" in info else md.get("info_raw")
    if block is None:
        return None
    branch = story_tree.get_branch(db, story, m.branch_id)
    if info.get("undo"):
        revert(db, story, branch, m, "read again")
        md = dict(m.generation_metadata_json or {})
    is_head = branch.head_message_id == m.id
    on_path = m.id in story_tree.live_path_ids(db, branch)
    row = state_service.current(db, branch.id)
    state = state_service.normalize(json.loads(json.dumps(row.state_json)) if row else {})
    index = build_index(db, story.world_id, state)
    items = parse(block)
    lines: list[dict[str, Any]] = []
    undo: list[dict[str, Any]] = []
    applied: list[str] = []
    rel_changes: list[dict[str, Any]] = []
    scene_update: dict[str, Any] = {"changes": {}, "days_passed": 0, "evidence": {}, "dropped": []}
    present_ids: list[str] | None = None
    moods: list[dict[str, Any]] = []
    sc = state["scene"]

    def char(name: str) -> str | None:
        cid = index.resolve(name)
        return cid if cid and cid in index.entities and index.entities[cid].category == "character" else None

    for i, it in enumerate(items):
        status, reason = "applied", ""
        k = it["kind"]
        if not on_path:
            status, reason = "dropped", "not on the story's current path"
        elif k in ("place", "time", "days", "present") and not is_head:
            status, reason = "dropped", "only the latest reply moves the scene"
        elif k == "place":
            val = world_state.clean_value("location", it["value"])
            if val is None:
                status, reason = "dropped", "not a place"
            elif val != sc.get("location"):
                scene_update["changes"]["location"] = val
                scene_update["evidence"]["location"] = "info table"
            else:
                status, reason = "unchanged", ""
        elif k == "time":
            val = world_state.clean_value("time", it["value"])
            refused = None
            if val is not None:
                val, refused = world_state.resolve_time(val, it["value"], sc.get("time"))
            if val is None or refused:
                status, reason = "dropped", refused or "not a time of day"
            elif val != sc.get("time"):
                scene_update["changes"]["time"] = val
                scene_update["evidence"]["time"] = "info table"
            else:
                status = "unchanged"
        elif k == "days":
            if 0 < it["value"] <= 30:
                scene_update["days_passed"] = it["value"]
            else:
                status, reason = "dropped", "days only move forward (1 to 30)"
        elif k == "present":
            ids = [c for c in (char(n) for n in it["names"]) if c]
            it["resolved_names"] = [index.name(c) for c in ids]
            if not ids and it["names"]:
                status, reason = "dropped", "unknown names"
            else:
                present_ids = list(dict.fromkeys(ids))
        elif k == "relationship":
            cid = char(it["who"])
            if cid is None:
                status, reason = "dropped", f"unknown character “{it['who']}”"
            elif not it.get("delta"):
                status, reason = "dropped", "no change"
            else:
                it["name"] = index.name(cid)
                big = abs(it["delta"]) > REL_MAX
                rel_changes.append({"source_id": cid, "target_id": relationships.PROTAGONIST, "dimension": it["axis"],
                                    "delta": it["delta"], "impact": "major" if big else "minor", "confidence": 0.9,
                                    "evidence": it.get("reason") or "info table", "evidence_verified": True, "_line": i})
                status = "pending"
        elif k == "stat":
            st = _stat_row(state, it["stat"])
            if st is None:
                status, reason = "dropped", "this story has no such stat"
            else:
                old = st.get("value")
                state, summary = state_service.apply_change(state, "stat", {"stat": st["label"], "delta": it["delta"]},
                                                            source="info_table", message_id=m.id)
                new = _stat_row(state, it["stat"]).get("value")
                real = (new or 0) - (old or 0)
                if real:
                    undo.append({"kind": "stat", "payload": {"stat": st["label"], "delta": -real}})
                    applied.append(summary)
                    if real != it["delta"]:
                        reason = f"kept between 0 and {st.get('max')}: {old} → {new}"
                else:
                    status, reason = "unchanged", f"already at {old}"
        elif k == "condition":
            try:
                if it["remove"]:
                    state, summary = state_service.apply_change(state, "condition_remove", {"label": it["name"]})
                    undo.append({"kind": "condition_add", "payload": {"label": it["name"]}})
                elif any(str(c.get("label")).casefold() == it["name"].casefold() for c in state["conditions"]):
                    status, summary = "unchanged", ""
                else:
                    state, summary = state_service.apply_change(state, "condition_add", {"label": it["name"]})
                    undo.append({"kind": "condition_remove", "payload": {"label": it["name"]}})
                if summary:
                    applied.append(summary)
            except ValueError as e:
                status, reason = "dropped", str(e)
        elif k == "item":
            try:
                kind = "inventory_remove" if it["remove"] else "inventory_add"
                state, summary = state_service.apply_change(state, kind, {"name": it["name"]})
                undo.append({"kind": "inventory_add" if it["remove"] else "inventory_remove", "payload": {"name": it["name"]}})
                applied.append(summary)
            except ValueError as e:
                status, reason = "dropped", str(e)
        elif k == "mood":
            cid = char(it["who"])
            if cid is None:
                status, reason = "dropped", f"unknown character “{it['who']}”"
            else:
                it["name"] = index.name(cid)
                moods.append({"character_id": cid, "slot": it["slot"], "evidence": "info table"})
        elif k == "fact":
            ents = [c for c in index.find_mentions(it["value"], ("character",))] if hasattr(index, "find_mentions") else []
            db.add(StoryEvent(story_id=story.id, branch_id=branch.id,
                              branch_sequence=story_tree.next_event_sequence(db, branch), event_type="fact",
                              title=it["value"][:80], summary=it["value"], entity_ids_json=ents[:6],
                              verification_status="recorded_unverified", evidence_kind="witnessed",
                              source_message_ids_json=[m.id], dedupe_key=f"info:{m.id}:{i}"))
        lines.append({"i": i, "kind": k, "label": _label(it, index), "status": status, "reason": reason, "text": it["text"]})

    if applied:
        state_service.save(db, story.id, branch.id, state, source="info_table",
                           summary="Info table: " + "; ".join(applied), message_id=m.id)
    if rel_changes:
        mode = settings_service.get(db, "relationship_mode") or "auto_conservative"
        outcomes = relationships.apply_from_analysis(db, story, branch, m.id,
                                                     [{k2: v for k2, v in c.items() if k2 != "_line"} for c in rel_changes],
                                                     index, "auto_conservative" if mode == "off" else mode)
        for c, o in zip(rel_changes, outcomes):
            ln = next(x for x in lines if x["i"] == c["_line"])
            ln["status"] = o.get("status", "applied")
            if o.get("status") == "proposed":
                ln["reason"] = "more than ±2 in one reply: to review in Journal & memory"
            elif o.get("status") == "dropped":
                ln["reason"] = o.get("reason") or ""
    if is_head and on_path and (scene_update["changes"] or scene_update["days_passed"]):
        world_state.apply_from_analysis(db, story, branch, m.id, scene_update, index)
        from . import chrono
        chrono.record_current(db, m, branch, "analysis")
    if is_head and on_path and present_ids is not None:
        before = list(sc.get("present") or [])
        scene_cast.apply_from_analysis(db, story, branch, m.id, present_ids, [c for c in before if c not in present_ids],
                                       index, location_changed="location" in scene_update["changes"])
        for cid in present_ids:
            discovery.record(db, story, branch, character_id=cid, name=index.name(cid), status="encountered",
                             source_message_id=m.id, evidence="info table", method="analysis")
    if moods and is_head:
        from .turns import apply_expressions
        tagged = {t.get("character_id") for t in md.get("portrait_tags") or []}
        moods = [x for x in moods if x["character_id"] not in tagged]
        if moods:
            apply_expressions(story, branch.id, moods, source="info_table", message_id=m.id)
    info = {"raw": block[:2000], "lines": lines, "undo": undo, "edited_by_player": bool(edited or info.get("edited_by_player")),
            "missing": False}
    md = dict(m.generation_metadata_json or {})
    md["info_table"] = info
    md.pop("info_raw", None)
    m.generation_metadata_json = md
    return info


def edit_line(db: Session, story: Story, m: Message, line: int, value: str | None) -> dict[str, Any]:
    """The player cancels (``value`` None) or rewrites one line; the whole block is read again from the new text."""
    md = dict(m.generation_metadata_json or {})
    info = md.get("info_table") or {}
    raw_lines = [l for l in (info.get("raw") or "").splitlines()]
    texts = [x["text"] for x in info.get("lines") or []]
    if not 0 <= line < len(texts):
        raise ValueError("No such line in the info table.")
    target = texts[line]
    out, replaced = [], False
    for l in raw_lines:
        if not replaced and l.strip() == target:
            replaced = True
            if value is not None and value.strip():
                out.append(value.strip())
            continue
        out.append(l)
    if not replaced:
        raise ValueError("That line has changed; reload the story.")
    return apply(db, story, m, block="\n".join(out), edited=True) or {}
