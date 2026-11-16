"""Music library (v1.8): list, add (.mp3 upload), edit title/tags, delete, stream; and what a story should play now."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import LoreEntity, World
from ..services import music as music_svc
from ..services import state_service, story_tree
from ..services.runtime import AppContext

router = APIRouter(tags=["music"])


@router.get("/music/tags")
def tags() -> dict[str, Any]:
    return {"tags": music_svc.TAGS, "groups": music_svc.GROUPS}


@router.get("/music/tracks")
def tracks(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"tracks": music_svc.load(ctx.settings.music_dir)["tracks"], "folder": str(ctx.settings.music_dir)}


@router.post("/music/tracks")
async def upload(files: list[UploadFile] = File(...), ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    added, errors = [], []
    for f in files:
        try:
            added.append(music_svc.add(ctx.settings.music_dir, f.filename or "track.mp3", await f.read()))
        except ValueError as e:
            errors.append(str(e))
    if not added and errors:
        raise ValueError(" ".join(errors))
    return {"added": added, "errors": errors}


class TrackIn(BaseModel):
    title: Optional[str] = None
    tags: Optional[list[str]] = None
    artist: Optional[str] = None
    license: Optional[str] = None


@router.patch("/music/tracks/{tid}")
def edit(tid: str, body: TrackIn, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    try:
        return {"track": music_svc.update(ctx.settings.music_dir, tid, body.model_dump(exclude_none=True))}
    except KeyError:
        raise HTTPException(404, "Track not found")


@router.delete("/music/tracks/{tid}")
def remove(tid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    try:
        music_svc.delete(ctx.settings.music_dir, tid)
    except KeyError:
        raise HTTPException(404, "Track not found")
    return {"ok": True}


@router.get("/music/tracks/{tid}/file")
def stream(tid: str, ctx: AppContext = Depends(get_ctx)):
    f = music_svc.file_of(ctx.settings.music_dir, tid)
    if f is None:
        raise HTTPException(404, "Track not found")
    return FileResponse(f, media_type=music_svc.AUDIO_EXTS.get(f.suffix.lower(), "audio/mpeg"))


@router.get("/stories/{sid}/music")
def story_music(sid: str, skip: int = 0, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """The track to play now in this story (active branch). ``skip`` asks for another track with the same tag."""
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    world = db.get(World, s.world_id) if s.world_id else None
    path = story_tree.path_messages(db, b.head_message_id)
    replies = [m for m in path if m.role == "assistant" and m.kind == "story"]
    st_row = state_service.current(db, b.id)
    scene = (state_service.normalize(st_row.state_json if st_row else {})).get("scene") or {}
    loc_type = ""
    if world is not None and scene.get("location"):
        le = db.scalar(select(LoreEntity).where(LoreEntity.world_id == world.id, LoreEntity.category == "location",
                                                LoreEntity.name == scene["location"]))
        loc_type = f"{le.entity_type} {le.name}" if le else ""
    return music_svc.for_story(ctx.settings.music_dir, world, replies, scene, loc_type, skip=skip)
