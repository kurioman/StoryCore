"""Scene presentation (speakers/portraits), suggested next actions, and the per-story known-character roster."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import Message, StateProposal, TurnAnalysis
from ..services import assets as assets_svc
from ..services import canon as canon_svc
from ..services import discovery, settings_service, state_service, story_tree, turn_analysis
from ..services.context_builder import visible_facts
from ..services.entities import build_index
from ..services.runtime import AppContext

router = APIRouter(tags=["narrative"])


def _ctx(db: Session, sid: str):
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    st_row = state_service.current(db, b.id)
    state = state_service.normalize(st_row.state_json if st_row else {})
    return s, b, state, build_index(db, s.world_id, state)


def _portrait(pmap: dict[str, dict[int, str]], cid: str, slot: int) -> dict[str, Any]:
    asset_id, used, fallback = assets_svc.resolve_expression(pmap.get(cid, {}), slot)
    return {"asset_id": asset_id, "slot_used": used, "is_fallback": fallback}


# --------------------------------------------------------------------------- scene
def _recent(m: Message, seconds: int = 60) -> bool:
    from datetime import datetime, timezone
    at = (m.generation_metadata_json or {}).get("finished_at")
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds() < seconds
    except (TypeError, ValueError):
        return False


@router.get("/stories/{sid}/scene")
def scene(sid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Speakers and suggestions for the latest assistant reply on the active branch (never another branch/story)."""
    s, b, state, index = _ctx(db, sid)
    path = story_tree.path_messages(db, b.head_message_id)
    last = next((m for m in reversed(path) if m.role == "assistant" and m.kind == "story"), None)
    out = turn_analysis.scene_for(db, s, last)
    pmap = assets_svc.portrait_map(db, s.world_id)
    speakers = []
    for sp in out["speakers"]:
        cid = sp["character_id"]
        if cid not in index.entities:
            continue
        speakers.append({**sp, "name": index.name(cid), **_portrait(pmap, cid, int(sp.get("expression") or 1))})
    out["speakers"] = speakers
    if out["active_speaker_id"] not in {x["character_id"] for x in speakers}:
        out["active_speaker_id"] = speakers[-1]["character_id"] if speakers else None
    out["beats"] = [{**bt, "name": index.name(bt["character_id"]), **_portrait(pmap, bt["character_id"], int(bt.get("expression") or 1))}
                    for bt in out["beats"] if bt.get("character_id") in index.entities]
    # relationship notices only about people the protagonist knows of or sees here (no hidden NPC-to-NPC news)
    visible = set(discovery.roster(db, s, b)) | set(state["scene"].get("present", [])) | {x["character_id"] for x in out["beats"]}
    out["relationship_changes"] = [
        {**c, "source_name": index.name(c["source_id"]), "target_name": "you" if c["target_id"] == "protagonist" else index.name(c["target_id"])}
        for c in out["relationship_changes"]
        if c.get("source_id") in visible and (c.get("target_id") == "protagonist" or c.get("target_id") in visible)]
    cfg = settings_service.get_all(db)
    # suggestions only for a completed reply that is still the head: anything else would be stale
    out["is_head"] = bool(last and b.head_message_id == last.id and last.status == "complete")
    no_record_yet = out["status"] == "none"
    # An intended "not analysed" comes from today's settings, never from the row: a stored reason can be years out of date
    if last is not None and out["status"] in ("none", "skipped"):
        reason = turn_analysis.skip_reason(cfg["turn_analysis_mode"], turn_analysis.analysis_is_cloud(ctx, db, s, cfg))
        out["status"], out["error"] = ("skipped", reason) if reason else ("none", None)
    if out["status"] == "none" and no_record_yet and out["is_head"] and _recent(last):
        out["status"] = "pending"  # the post-turn hook has not created its record yet: tell the UI to wait for it
    out["story_id"], out["branch_id"] = s.id, b.id
    out["settings"] = {k: cfg.get(k) for k in ("turn_analysis_mode", "action_suggestions_enabled", "show_scene_portraits",
                                                "relationship_mode")}
    return out


@router.post("/messages/{mid}/analysis")
def rerun_analysis(mid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.get(Message, mid)
    if m is None or m.role != "assistant" or m.kind != "story":
        raise HTTPException(404, "Reply not found")
    if m.status != "complete":
        raise ValueError("Only a completed reply can be analysed.")
    row = db.scalar(select(TurnAnalysis).where(TurnAnalysis.message_id == mid))
    if row is not None and row.status == "running":
        return {"status": "running"}
    if row is None:
        row = TurnAnalysis(message_id=m.id, story_id=m.story_id, branch_id=m.branch_id)
        db.add(row)
    row.status, row.error, row.suggestions_error = "pending", None, None
    db.commit()
    ctx.spawn(turn_analysis.analyse(ctx, mid, force=True))
    return {"status": "pending"}


# --------------------------------------------------------------------------- known characters
def _relationships(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["target_id"]: r for r in state["relationships"] if r.get("target_id") and not r.get("source_id")}


@router.get("/stories/{sid}/characters")
def known_characters(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, state, index = _ctx(db, sid)
    roster = discovery.roster(db, s, b)
    present = [c for c in state["scene"].get("present", []) if c in index.entities and index.entities[c].category == "character"]
    path = story_tree.path_messages(db, b.head_message_id)
    head_reply = next((m for m in reversed(path) if m.role == "assistant"), None)
    speaking = {head_reply.speaker_character_id} if head_reply and head_reply.speaker_character_id else set()
    seq_by_id = {m.id: m.seq for m in path}
    rels = _relationships(state)
    pmap = assets_svc.portrait_map(db, s.world_id)
    exprs = ((s.settings_json or {}).get("expressions") or {}).get(b.id, {})
    out = []
    for cid in dict.fromkeys([*present, *roster.keys()]):
        if cid not in index.entities:
            continue
        r = roster.get(cid)
        e = index.entities[cid]
        slot = int((exprs.get(cid) or {}).get("slot") or 1)
        out.append({
            "character_id": cid, "name": e.name, "type": e.type, "local": e.local,
            # present characters without a record were placed in the scene by the user/setup: shown as encountered
            "status": r.status if r else "encountered", "capture_method": r.capture_method if r else "scene",
            "evidence": r.evidence if r else "", "source_message_id": r.source_message_id if r else None,
            "source_seq": seq_by_id.get(r.source_message_id) if r and r.source_message_id else None,
            "discovered_at": r.created_at if r else None,
            "in_scene": cid in present or cid in speaking, "relationship": rels.get(cid),
            **_portrait(pmap, cid, slot),
        })
    out.sort(key=lambda c: (not c["in_scene"], -(c["source_seq"] if c["source_seq"] is not None else -1), c["name"].casefold()))
    return {"characters": out, "branch_id": b.id}


class DiscoveryIn(BaseModel):
    character_id: str
    status: str  # rumored | encountered | known | removed
    note: Optional[str] = None


@router.post("/stories/{sid}/characters")
def set_discovery(sid: str, body: DiscoveryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Manual correction (mark as met / rumoured / known, or remove an accidental discovery) with an audit record."""
    s, b, state, index = _ctx(db, sid)
    if body.character_id not in index.entities or index.entities[body.character_id].category != "character":
        raise ValueError("Unknown character. Add story-local characters in the Cast tab first.")
    row = discovery.record(db, s, b, character_id=body.character_id, name=index.name(body.character_id), status=body.status,
                           source_message_id=b.head_message_id, evidence=body.note or "Set manually", method="manual")
    if body.status == "removed" and body.character_id in state["scene"].get("present", []):
        st, _ = state_service.apply_change(state, "scene", {"present_remove": [body.character_id]}, source="manual")
        state_service.save(db, s.id, b.id, st, source="manual", summary=f"{index.name(body.character_id)} removed from the scene")
    return {"discovery": discovery.to_dict(row, db) if row else None}


@router.get("/stories/{sid}/characters/{cid}")
def character_detail(sid: str, cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Discovery audit trail, relationship history and proposals, and what this NPC knows / believes / must not know."""
    s, b, state, index = _ctx(db, sid)
    if cid not in index.entities:
        raise HTTPException(404, "Character not found")
    path_ids = story_tree.live_path_ids(db, b)
    seqs = {m.id: m.seq for m in story_tree.path_messages(db, b.head_message_id, include_deleted=True)}
    hist = [dict(discovery.to_dict(r), source_seq=seqs.get(r.source_message_id)) for r in discovery.history(db, s, b, cid)]
    rel = _relationships(state).get(cid)
    if rel:  # approved changes stay applied, but say when their source reply was regenerated away or deleted
        rel = {**rel, "history": [{**h, "source_replaced": bool(h.get("message_id")) and h["message_id"] not in path_ids}
                                  for h in rel.get("history") or []]}
    name = index.name(cid).casefold()
    props = []
    for p in db.scalars(select(StateProposal).where(StateProposal.branch_id == b.id, StateProposal.kind == "relationship")
                        .order_by(StateProposal.created_at.desc())):
        pl = p.payload_json or {}
        if pl.get("target_id") != cid and str(pl.get("target_name") or "").casefold() != name:
            continue
        src = p.source_message_ids_json or []
        if src and not set(src) & path_ids:
            continue  # from an unselected alternative/branch
        props.append({**p.to_dict(), "source_seqs": [seqs[x] for x in src if x in seqs]})
    knowledge: dict[str, list[dict[str, Any]]] = {"knows": [], "believes": [], "unaware": []}
    for f in visible_facts(db, s, b, path_ids):
        if f.status in ("rejected", "superseded"):
            continue
        k = f.knowledge_json or {}
        item = {"id": f.id, "content": f.content, "fact_kind": f.fact_kind, "status": f.status, "confidence": f.confidence,
                "source_seqs": [seqs[x] for x in (f.source_message_ids_json or []) if x in seqs]}
        if cid in (k.get("hidden_from") or []):
            knowledge["unaware"].append(item)
        elif f.belief_holder_id == cid or (f.fact_kind in ("rumour", "belief", "claim") and cid in (k.get("known_by") or [])):
            knowledge["believes"].append(item)
        elif cid in (k.get("known_by") or []):
            knowledge["knows"].append(item)
    e = index.entities[cid]
    # v1.4 foundation: relationships between characters by canonical id — lore background (read-only, initial) kept
    # apart from what the story has changed (directional state records, A -> B is A's view of B)
    from ..services import relationships as rel_svc
    evolved = [{"source_id": r["source_id"], "source_name": r.get("source_name") or index.name(r["source_id"]),
                "target_id": r.get("target_id"), "target_name": r.get("target_name") or index.name(r.get("target_id") or ""),
                "label": r.get("label", ""), "axes": r.get("axes") or {}, "origin": "story",
                "history": [{**h, "source_replaced": bool(h.get("message_id")) and h["message_id"] not in path_ids}
                            for h in (r.get("history") or [])][-10:]}
               for r in state["relationships"]
               if r.get("source_id") and r["source_id"] != "protagonist" and cid in (r["source_id"], r.get("target_id"))]
    return {"character": {"character_id": cid, "name": e.name, "type": e.type, "local": e.local},
            "discovery_history": hist, "relationship": rel, "relationship_proposals": props, "knowledge": knowledge,
            "lore_relationships": rel_svc.lore_relationships(db, s.world_id, {cid}), "character_relationships": evolved,
            # v1.5: canon facts about who this character is (kinship, family branch, classes taught/attended)
            "canon": canon_svc.for_character(canon_svc.facts(db, s.world_id, index), cid, index)}


# --------------------------------------------------------------------------- codex (v1.8)
@router.get("/stories/{sid}/codex")
def codex(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Characters and places discovered in this story (active branch); undiscovered ones are counted as locked."""
    from ..services import codex as codex_svc
    s, b, state, index = _ctx(db, sid)
    return codex_svc.build(db, s, b, index)
