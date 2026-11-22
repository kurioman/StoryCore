"""World creator API (Phase 8): create, edit, copy, delete and share lore packs from inside the app.

Every change is written to the pack's files in ``Lorepack/`` (services/pack_editor.py), then the world is reloaded the
same way as at start-up (bundled._sync_pack), so a story started right after plays the saved version.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import now_iso
from ..services import pack_editor
from ..services.pack_editor import EditorError
from ..services.runtime import AppContext

router = APIRouter(tags=["creator"])
log = logging.getLogger("story")


class AssistIn(BaseModel):
    kind: str  # character, location, group, starter, premise, narrator
    idea: str = ""
    lang: str = "en"  # the player's interface language: the draft is written in it


class NewWorldIn(BaseModel):
    name: str
    copy_from: str = ""  # id of a pack to copy (any pack: bundled, hand-made or made with the creator)


def _root(ctx: AppContext) -> Path:
    return ctx.settings.project_root


def _fail(e: Exception) -> HTTPException:
    if isinstance(e, LookupError):
        return HTTPException(404, str(e) or "World not found")
    return HTTPException(400, str(e))


def _reload(ctx: AppContext, db: Session, pid: str) -> dict[str, Any]:
    """Import the saved files again (lore and portraits). A problem never loses the save: it is reported."""
    from ..bundled import _sync_pack

    db.commit()  # the reload uses its own database sessions
    try:
        folder, _raw = pack_editor.find(_root(ctx), pid)
        return {"reloaded": _sync_pack(ctx, folder.resolve(), {})}
    except Exception as e:  # noqa: BLE001 - shown to the player, the files are saved anyway
        log.exception("world creator: %s could not be reloaded", pid)
        return {"reload_error": str(e)}


@router.get("/creator/worlds")
def list_worlds(ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"worlds": pack_editor.list_packs(_root(ctx), db)}


@router.post("/creator/worlds")
def new_world(body: NewWorldIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        if body.copy_from:
            pid = pack_editor.copy(_root(ctx), db, body.copy_from, body.name, now_iso())
        else:
            pid = pack_editor.create(_root(ctx), db, body.name, now_iso())
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return {"id": pid, **_reload(ctx, db, pid)}


@router.get("/creator/worlds/{pid}")
def get_world(pid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    try:
        return pack_editor.read(_root(ctx), pid)
    except (EditorError, LookupError) as e:
        raise _fail(e)


@router.put("/creator/worlds/{pid}")
def save_world(pid: str, body: dict[str, Any], ctx: AppContext = Depends(get_ctx),
               db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        doc = pack_editor.write(_root(ctx), pid, body, now_iso())
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return {"world": doc, **_reload(ctx, db, pid)}


@router.delete("/creator/worlds/{pid}")
def delete_world(pid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        pack_editor.delete(_root(ctx), db, pid)
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return {"ok": True}


@router.post("/creator/worlds/{pid}/assist")
async def assist(pid: str, body: AssistIn, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    """A draft written by the player's model from a short idea (never saved here: the player edits it first)."""
    from ..services import creator_assist

    try:
        return await creator_assist.suggest(ctx, pid, body.kind, body.idea, body.lang)
    except LookupError as e:
        raise _fail(e)


@router.get("/creator/worlds/{pid}/check")
def check_world(pid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    from ..services import pack_check

    try:
        folder, _raw = pack_editor.find(_root(ctx), pid)
    except LookupError as e:
        raise _fail(e)
    return pack_check.check_pack(folder)


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(pack_editor.UPLOAD_MAX_BYTES + 1)
    if len(data) > pack_editor.UPLOAD_MAX_BYTES:
        raise HTTPException(400, "This file is too large (25 MB at most).")
    return data


@router.post("/creator/worlds/{pid}/cover")
async def upload_cover(pid: str, file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx),
                       db: Session = Depends(get_db)) -> dict[str, Any]:
    data = await _read_upload(file)
    try:
        pack_editor.set_cover(_root(ctx), pid, data, now_iso())
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return _reload(ctx, db, pid)


@router.delete("/creator/worlds/{pid}/cover")
def delete_cover(pid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        pack_editor.set_cover(_root(ctx), pid, None, now_iso())
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return _reload(ctx, db, pid)


@router.post("/creator/worlds/{pid}/portraits/{char_id}/{n}")
async def upload_portrait(pid: str, char_id: str, n: int, file: UploadFile = File(...),
                          ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    data = await _read_upload(file)
    try:
        pack_editor.set_portrait(_root(ctx), pid, char_id, n, data)
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return _reload(ctx, db, pid)


@router.delete("/creator/worlds/{pid}/portraits/{char_id}")
def delete_portraits(pid: str, char_id: str, n: int = 0, ctx: AppContext = Depends(get_ctx),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        pack_editor.remove_portraits(_root(ctx), pid, char_id, n or None)
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return _reload(ctx, db, pid)


@router.post("/creator/worlds/{pid}/places/{place_id}/image")
async def upload_place_image(pid: str, place_id: str, file: UploadFile = File(...),
                             ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """v0.6.2: the background picture of a place."""
    data = await _read_upload(file)
    try:
        pack_editor.set_place_image(_root(ctx), pid, place_id, data)
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return _reload(ctx, db, pid)


@router.delete("/creator/worlds/{pid}/places/{place_id}/image")
def delete_place_image(pid: str, place_id: str, ctx: AppContext = Depends(get_ctx),
                       db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        pack_editor.set_place_image(_root(ctx), pid, place_id, None)
    except (EditorError, LookupError) as e:
        raise _fail(e)
    return _reload(ctx, db, pid)


@router.get("/creator/worlds/{pid}/image")
def world_image(pid: str, path: str, ctx: AppContext = Depends(get_ctx)) -> FileResponse:
    """The cover or a portrait of a world being edited (only files of its images folder and its cover)."""
    try:
        p = pack_editor.image_path(_root(ctx), pid, path)
    except LookupError as e:
        raise _fail(e)
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@router.get("/creator/worlds/{pid}/export")
def export_world(pid: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    try:
        data, name = pack_editor.export_zip(_root(ctx), pid)
    except LookupError as e:
        raise _fail(e)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/creator/import")
async def import_world(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx),
                       db: Session = Depends(get_db)) -> dict[str, Any]:
    """A shared world (.zip): copied into Lorepack, loaded, and checked."""
    from ..services import pack_check

    data = await file.read(512 * 1024 * 1024 + 1)
    if len(data) > 512 * 1024 * 1024:
        raise HTTPException(400, "This file is too large (512 MB at most).")
    try:
        pid = pack_editor.import_zip(_root(ctx), db, data, file.filename or "world.zip")
    except EditorError as e:
        raise _fail(e)
    out = {"id": pid, **_reload(ctx, db, pid)}
    folder, _raw = pack_editor.find(_root(ctx), pid)
    out["check"] = pack_check.check_pack(folder)
    return out
