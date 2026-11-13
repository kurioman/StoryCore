from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import StateProposal, UserNote, now_iso
from ..services import state_service, story_tree, world_state
from ..services.runtime import AppContext

router = APIRouter(tags=["state"])


def _state(db: Session, sid: str) -> tuple[Any, Any, dict[str, Any], int]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    row = state_service.current(db, b.id)
    if row is None:
        row = state_service.save(db, s.id, b.id, state_service.default_state("none"), source="manual", summary="Initial state")
    return s, b, state_service.normalize(row.state_json), row.state_version


def _follow(db: Session, s: Any, b: Any, old: dict[str, Any], row: Any) -> None:
    """v1.5.1: a scene correction is shown in the latest reply's chronology header (older headers keep their values)."""
    from ..services import chrono
    chrono.follow_manual_edit(db, s, b, (old or {}).get("scene"), (row.state_json or {}).get("scene"))


@router.get("/stories/{sid}/state")
def get_state(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, st, ver = _state(db, sid)
    path = story_tree.live_path_ids(db, b)
    pending = [p for p in db.scalars(select(StateProposal).where(StateProposal.branch_id == b.id, StateProposal.status == "pending"))
               if _on_path(p, path)]
    hist = state_service.history(db, b.id, 2)
    from ..services import relationships
    difficulty = relationships.difficulty_of(s.settings_json)
    return {"state": st, "version": ver, "branch_id": b.id, "pending_proposals": len(pending),
            "can_undo": len(hist) > 1, "last_change": hist[0].summary if hist else "",
            "templates": list(state_service.STAT_TEMPLATES.keys()),
            # v1.5: derived stages (deterministic, from the values) and the story's progression difficulty
            "relationship_tiers": relationships.tiers_for(st, difficulty), "relationship_difficulty": difficulty,
            # v1.5.1: calendar conventions from the world's lore and an optional first-year start date to *offer*
            "calendar": world_state.calendar_of(db, s.world_id),
            "date_suggestion": world_state.date_suggestion(db, s, st["scene"])}


@router.get("/stories/{sid}/relationships/duplicates")
def relationship_duplicates(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Read-only: records that describe the same direction and the same person (legacy duplicates)."""
    from ..services import relationships
    from ..services.entities import build_index
    s, _b, st, ver = _state(db, sid)
    return {"duplicates": relationships.find_duplicates(st, build_index(db, s.world_id, st)), "version": ver}


class MergeIn(BaseModel):
    keep_id: str
    drop_ids: list[str]
    base_version: Optional[int] = None


@router.post("/stories/{sid}/relationships/merge")
def relationship_merge(sid: str, body: MergeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Explicit merge chosen by the player (keeps the chosen record's values, merges histories; undoable)."""
    from ..services import relationships
    s, b, st, ver = _state(db, sid)
    if body.base_version is not None and body.base_version != ver:
        raise HTTPException(409, f"State changed since you opened it (now v{ver}). Reload and try again.")
    new, summary = relationships.merge_records(st, body.keep_id, body.drop_ids)
    row = state_service.save(db, s.id, b.id, new, source="manual", summary=summary)
    return {"state": row.state_json, "version": row.state_version, "summary": summary}


class StatePut(BaseModel):
    state: dict[str, Any]
    summary: str = "Manual edit"
    base_version: Optional[int] = None


@router.put("/stories/{sid}/state")
def put_state(sid: str, body: StatePut, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, old, ver = _state(db, sid)
    if body.base_version is not None and body.base_version != ver:
        raise HTTPException(409, f"State changed since you opened it (now v{ver}). Reload and re-apply your edit.")
    row = state_service.save(db, s.id, b.id, body.state, source="manual", summary=body.summary)
    _follow(db, s, b, old, row)
    return {"state": row.state_json, "version": row.state_version}


class ChangeIn(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    message_id: Optional[str] = None


@router.post("/stories/{sid}/state/change")
def apply_change(sid: str, body: ChangeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, st, _ver = _state(db, sid)
    new, summary = state_service.apply_change(st, body.kind, body.payload, source="manual", message_id=body.message_id)
    row = state_service.save(db, s.id, b.id, new, source="manual", summary=summary, message_id=body.message_id)
    _follow(db, s, b, st, row)
    return {"state": row.state_json, "version": row.state_version, "summary": summary}


@router.post("/stories/{sid}/state/undo")
def undo(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, old, _ver = _state(db, sid)
    row = state_service.undo_last(db, s.id, b.id)
    _follow(db, s, b, old, row)
    return {"state": row.state_json, "version": row.state_version, "summary": row.summary}


@router.get("/stories/{sid}/state/history")
def history(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    return {"history": [{"version": r.state_version, "source": r.source, "summary": r.summary, "message_id": r.message_id,
                         "created_at": r.created_at} for r in state_service.history(db, b.id, 200)]}


@router.get("/stories/{sid}/state/history/{version}")
def history_version(sid: str, version: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    from ..models import StoryState

    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    r = db.scalar(select(StoryState).where(StoryState.branch_id == b.id, StoryState.state_version == version))
    if r is None:
        raise HTTPException(404, "Version not found")
    return {"version": r.state_version, "state": r.state_json, "summary": r.summary, "source": r.source}


# --------------------------------------------------------------------------- proposals (review queue)
@router.get("/stories/{sid}/proposals")
def proposals(sid: str, status: str = "pending", db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    q = select(StateProposal).where(StateProposal.branch_id == b.id)
    if status != "all":
        q = q.where(StateProposal.status == status)
    path = story_tree.live_path_ids(db, b)
    # proposals extracted from an unselected regenerated alternative must not be offered for the active story
    return {"proposals": [p.to_dict() for p in db.scalars(q.order_by(StateProposal.created_at.desc())) if _on_path(p, path)]}


def _on_path(p: StateProposal, path: set[str]) -> bool:
    src = p.source_message_ids_json or []
    return not src or bool(set(src) & path)


def _already_applied(state: dict[str, Any], p: StateProposal) -> str | None:
    """A relationship change on the same axis, for the same pair, from the same reply that is already in effect (applied
    automatically or accepted earlier from another pipeline) — accepting it again would count one moment twice."""
    pl = p.payload_json or {}
    src_ids = set(p.source_message_ids_json or [])
    if not src_ids or not pl.get("axis"):
        return None
    name = str(pl.get("target_name") or "").casefold()
    for rel in state.get("relationships") or []:
        if (rel.get("source_id") or None) != (pl.get("source_id") or None):
            continue
        if not ((pl.get("target_id") and rel.get("target_id") == pl.get("target_id"))
                or (name and str(rel.get("target_name") or "").casefold() == name)):
            continue
        for h in rel.get("history") or []:
            if (h.get("message_id") in src_ids and h.get("axis") == pl["axis"] and not h.get("reverted_at")
                    and h.get("source") in ("analysis_auto", "accepted_ai_suggestion")):
                return h.get("change") or pl["axis"]
    return None


class ProposalAction(BaseModel):
    action: str  # accept | reject
    payload: Optional[dict[str, Any]] = None  # edited payload before accepting


@router.post("/stories/{sid}/proposals/{pid}")
def resolve_proposal(sid: str, pid: str, body: ProposalAction, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, st, _ver = _state(db, sid)
    p = db.get(StateProposal, pid)
    if p is None or p.story_id != s.id:
        raise HTTPException(404, "Proposal not found")
    if p.status != "pending":
        raise ValueError("This proposal was already resolved.")
    if body.action == "accept" and (p.branch_id != b.id or not _on_path(p, story_tree.live_path_ids(db, b))):
        raise ValueError("This proposal comes from a reply that is not part of the active story path; switch to it first.")
    if body.action == "reject":
        p.status, p.resolved_at = "rejected", now_iso()
        return {"proposal": p.to_dict()}
    if body.action != "accept":
        raise ValueError("action must be accept or reject")
    if body.payload is not None:
        p.payload_json = body.payload
    if p.kind == "relationship":
        from ..services.entities import build_index
        from ..services.relationships import PROTAGONIST_WORDS
        pl = dict(p.payload_json or {})
        if not pl.get("source_id") and str(pl.get("target_name") or "").strip().casefold() in PROTAGONIST_WORDS:
            raise ValueError("This proposal has no character whose view changes (its target is the player character). "
                             "Reject it, or edit it to name the character first.")
        if pl.get("target_name") and not pl.get("target_id"):
            tid = build_index(db, s.world_id, st).resolve(pl["target_name"])
            if tid:  # v1.5: the canonical id, so an existing record is found instead of creating a second card
                pl["target_id"] = tid
                p.payload_json = pl
        dup = _already_applied(st, p)
        if dup:
            raise ValueError(f"This change was already applied for the same reply ({dup}). Reject this duplicate, or "
                             "edit the relationship directly if you want a different value.")
    try:
        new, summary = state_service.apply_change(st, p.kind, p.payload_json, source="accepted_ai_suggestion",
                                                  message_id=(p.source_message_ids_json or [None])[-1])
    except (ValueError, KeyError, TypeError) as e:
        p.error = str(e)
        raise ValueError(f"Could not apply this proposal: {e}")
    row = state_service.save(db, s.id, b.id, new, source="accepted_ai_suggestion", summary=summary,
                             message_id=(p.source_message_ids_json or [None])[-1])
    _follow(db, s, b, st, row)
    p.status, p.resolved_at, p.applied_state_version, p.error = "accepted", now_iso(), row.state_version, None
    return {"proposal": p.to_dict(), "state": row.state_json, "version": row.state_version}


# --------------------------------------------------------------------------- user notes
@router.get("/notes")
def get_notes(story_id: Optional[str] = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    g = db.scalar(select(UserNote).where(UserNote.scope == "global"))
    if g is None:
        g = UserNote(scope="global", content="", enabled=True)
        db.add(g)
        db.flush()
    out: dict[str, Any] = {"global": g.to_dict()}
    if story_id:
        sn = db.scalar(select(UserNote).where(UserNote.scope == "story", UserNote.story_id == story_id))
        if sn is None:
            sn = UserNote(scope="story", story_id=story_id, content="", enabled=True)
            db.add(sn)
            db.flush()
        out["story"] = sn.to_dict()
        s = story_tree.get_story(db, story_id)
        out["global_disabled_for_story"] = bool((s.settings_json or {}).get("disable_global_note"))
    return out


class NoteIn(BaseModel):
    content: Optional[str] = None
    enabled: Optional[bool] = None


@router.put("/notes/{nid}")
def put_note(nid: str, body: NoteIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.get(UserNote, nid)
    if n is None:
        raise HTTPException(404, "Note not found")
    if body.content is not None:
        if len(body.content) > 50_000:
            raise ValueError("Notes are limited to 50,000 characters to protect the context budget.")
        n.content = body.content
    if body.enabled is not None:
        n.enabled = body.enabled
    return n.to_dict()


@router.post("/stories/{sid}/suggest-state")
async def suggest_state(sid: str, body: dict[str, Any] | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return await ctx.extraction.suggest_state_changes(sid, (body or {}).get("message_id"))
