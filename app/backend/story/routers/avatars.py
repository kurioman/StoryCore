from __future__ import annotations

import base64
import io
import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..services.avatar_profile import simplify
from ..deps import get_ctx, get_db
from ..models import Avatar, Story, now_iso
from ..services.context_builder import est_tokens, render_avatar
from ..services.runtime import AppContext

router = APIRouter(tags=["avatars"])
MAX_PROFILE_BYTES = 200_000
MAX_IMAGE_BYTES = 15_000_000
ALLOWED_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "GIF": ".gif"}


def avatar_out(db: Session, a: Avatar) -> dict[str, Any]:
    d = a.to_dict()
    d["used_by"] = [s.title for s in db.scalars(select(Story).where(Story.active_avatar_id == a.id))]
    text = render_avatar({"name": a.name, "profile": a.profile_json})
    d["prompt_tokens"] = est_tokens(text)
    return d


class AvatarIn(BaseModel):
    name: str
    profile: dict[str, Any] = Field(default_factory=dict)
    favourite: bool = False
    tags: list[str] = Field(default_factory=list)


def _check(profile: dict[str, Any]) -> None:
    if len(json.dumps(profile, ensure_ascii=False).encode()) > MAX_PROFILE_BYTES:
        raise ValueError("This avatar profile is very large (over 200 KB). Trim it to protect the context budget.")


@router.get("/avatars")
def list_avatars(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Avatar).order_by(Avatar.favourite.desc(), Avatar.updated_at.desc()))
    return {"avatars": [avatar_out(db, a) for a in rows]}


@router.post("/avatars")
def create_avatar(body: AvatarIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check(body.profile)
    profile, name = simplify(body.profile, body.name.strip() or "Unnamed")
    a = Avatar(name=name or "Unnamed", profile_json=profile, favourite=body.favourite, tags_json=body.tags)
    db.add(a)
    db.flush()
    return avatar_out(db, a)


@router.get("/avatars/{aid}")
def get_avatar(aid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    return avatar_out(db, a)


class AvatarPatch(BaseModel):
    name: Optional[str] = None
    profile: Optional[dict[str, Any]] = None
    favourite: Optional[bool] = None
    tags: Optional[list[str]] = None


@router.put("/avatars/{aid}")
def update_avatar(aid: str, body: AvatarPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    if body.profile is not None:
        _check(body.profile)
        a.profile_json, simple_name = simplify(body.profile, a.name)
        if simple_name and body.name is None:
            a.name = simple_name
    if body.name is not None:
        a.name = body.name.strip() or a.name
    if body.favourite is not None:
        a.favourite = body.favourite
    if body.tags is not None:
        a.tags_json = body.tags
    a.updated_at = now_iso()
    return avatar_out(db, a)


@router.delete("/avatars/{aid}")
def delete_avatar(aid: str, confirm: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    users = list(db.scalars(select(Story).where(Story.active_avatar_id == aid)))
    if users and not confirm:
        raise ValueError(f"This avatar is bound to {len(users)} story(ies). Confirm to delete; those stories keep a snapshot of the profile.")
    for s in users:
        s.active_avatar_id = None  # the story keeps avatar_snapshot_json
    db.delete(a)
    return {"ok": True}


@router.get("/avatars/{aid}/preview")
def preview(aid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    text = render_avatar({"name": a.name, "profile": a.profile_json})
    return {"text": text, "tokens": est_tokens(text), "approximate": True}


@router.post("/avatars/preview")
def preview_unsaved(body: AvatarIn) -> dict[str, Any]:
    text = render_avatar({"name": body.name, "profile": body.profile})
    return {"text": text, "tokens": est_tokens(text), "approximate": True}


def _store_image(ctx: AppContext, data: bytes, sub: str) -> str:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image is larger than 15 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
    except Exception:
        raise ValueError("That file is not a readable image.")
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("Use a PNG, JPEG, WEBP or GIF image.")
    rel = f"{sub}/{uuid.uuid4().hex}{ALLOWED_FORMATS[fmt]}"
    dst = ctx.settings.uploads_dir / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return rel


@router.post("/avatars/{aid}/portrait")
async def upload_portrait(aid: str, file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    a.portrait_path = _store_image(ctx, await file.read(), "avatars")
    a.updated_at = now_iso()
    return avatar_out(db, a)


class PortraitFromAsset(BaseModel):
    asset_id: str


@router.post("/avatars/{aid}/portrait-from-asset")
def portrait_from_asset(aid: str, body: PortraitFromAsset, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    from ..services import assets as assets_svc

    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    src = assets_svc.file_for(db, body.asset_id)
    a.portrait_path = _store_image(ctx, src.read_bytes(), "avatars")  # copy, so the avatar stays portable
    return avatar_out(db, a)


@router.delete("/avatars/{aid}/portrait")
def remove_portrait(aid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    a.portrait_path = None
    return avatar_out(db, a)


@router.get("/uploads/{sub}/{name}")
def serve_upload(sub: str, name: str, ctx: AppContext = Depends(get_ctx)):
    if sub not in ("avatars", "covers") or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(404)
    root = (ctx.settings.uploads_dir / sub).resolve()
    p = (root / name).resolve()
    if root not in p.parents or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "max-age=86400"})


@router.get("/avatars/{aid}/export")
def export_avatar(aid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Avatar, aid)
    if a is None:
        raise HTTPException(404, "Avatar not found")
    out: dict[str, Any] = {"format": "storycore-avatar", "format_version": 1, "name": a.name, "profile": a.profile_json,
                           "favourite": a.favourite, "tags": a.tags_json, "exported_at": now_iso()}
    if a.portrait_path:
        p = ctx.settings.uploads_dir / a.portrait_path
        if p.is_file():
            out["portrait"] = {"filename": p.name, "base64": base64.b64encode(p.read_bytes()).decode()}
    return out


@router.post("/avatars/import")
def import_avatar(body: dict[str, Any], ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.get("format") != "storycore-avatar":
        raise ValueError("Not a StoryCore avatar file.")
    profile = body.get("profile") or {}
    _check(profile)
    profile, name = simplify(profile, str(body.get("name") or "Imported avatar"))
    a = Avatar(name=name or "Imported avatar", profile_json=profile, favourite=bool(body.get("favourite")),
               tags_json=list(body.get("tags") or []))
    db.add(a)
    db.flush()
    if (body.get("portrait") or {}).get("base64"):
        a.portrait_path = _store_image(ctx, base64.b64decode(body["portrait"]["base64"]), "avatars")
    return avatar_out(db, a)
