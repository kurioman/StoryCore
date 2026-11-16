"""The AI's memory of a story (v0.5, phase 7.4): the memory panel, summarise / close a chapter now, the player recap."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import MemorySummary, now_iso
from ..services import story_tree
from ..services import summaries
from ..services.runtime import AppContext

router = APIRouter(tags=["memory"])


@router.get("/stories/{sid}/memory")
def memory(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    return summaries.memory_view(db, s, story_tree.get_branch(db, s))


class SummaryEdit(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


@router.patch("/stories/{sid}/memory/{rid}")
def edit_summary(sid: str, rid: str, body: SummaryEdit, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(MemorySummary, rid)
    if r is None or r.story_id != sid or r.status != "active":
        raise HTTPException(404, "Summary not found")
    r.content, r.source, r.updated_at = body.content.strip(), "edited", now_iso()
    s = story_tree.get_story(db, sid)
    return summaries.memory_view(db, s, story_tree.get_branch(db, s))


class ThreadIn(BaseModel):
    key: str = Field(min_length=3, max_length=80)


def _threads(db: Session, sid: str, key: str, closed: bool) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    keys = set((s.settings_json or {}).get("memory_closed_threads") or [])
    keys = keys | {key} if closed else keys - {key}
    s.settings_json = {**(s.settings_json or {}), "memory_closed_threads": sorted(keys)}
    db.flush()
    return summaries.memory_view(db, s, story_tree.get_branch(db, s))


@router.post("/stories/{sid}/memory/threads/close")
def close_thread(sid: str, body: ThreadIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _threads(db, sid, body.key, True)


@router.post("/stories/{sid}/memory/threads/reopen")
def reopen_thread(sid: str, body: ThreadIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _threads(db, sid, body.key, False)


class SummariseIn(BaseModel):
    chapter: bool = False  # close a chapter: the latest messages too, then every active scene merged
    title: Optional[str] = Field(default=None, max_length=120)


@router.post("/stories/{sid}/memory/summarise")
async def summarise_now(sid: str, body: SummariseIn | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    body = body or SummariseIn()
    out = await summaries.catch_up(ctx, sid, max_chunks=8, automatic=False, max_merges=3, force=body.chapter,
                                   chapter_title=(body.title or "") if body.chapter else None)
    if out.get("status") in ("no_model", "failed"):
        raise ValueError(out.get("error") or "The summary could not be written.")
    with ctx.db.session() as db:
        s = story_tree.get_story(db, sid)
        return {**out, "memory": summaries.memory_view(db, s, story_tree.get_branch(db, s))}


@router.get("/stories/{sid}/usage")
def usage_of(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """v0.5 phase 7.5: token use of the story (narrator replies on this path, side requests, the latest turn)."""
    from ..services import usage
    s = story_tree.get_story(db, sid)
    return usage.summary(db, s, story_tree.path_ids(db, story_tree.get_branch(db, s)))


class RecapIn(BaseModel):
    refresh: bool = False


@router.post("/stories/{sid}/player-recap")
async def player_recap(sid: str, body: RecapIn | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return await summaries.player_recap(ctx, sid, refresh=bool(body and body.refresh))
