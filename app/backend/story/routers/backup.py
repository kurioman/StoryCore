from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Database
from ..deps import get_ctx, get_db
from ..models import LocalCanon, UserNote, now_iso
from ..services import backup as backup_svc
from ..services import settings_service, story_tree
from ..services.runtime import AppContext

router = APIRouter(tags=["backup"])
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name)[:50] or "story"


@router.get("/stories/{sid}/export")
def export_story(sid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    s = story_tree.get_story(db, sid)
    out = ctx.settings.tmp_dir / f"{_safe(s.title)}_{now_iso()[:10]}.storycore-story.zip"
    backup_svc.export_story(db, sid, ctx.settings.uploads_dir, out)
    return FileResponse(out, filename=out.name, media_type="application/zip")


@router.post("/import/story/preview")
async def import_preview(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    token = uuid.uuid4().hex
    p = ctx.settings.tmp_dir / f"import_{token}.zip"
    p.write_bytes(await file.read())
    try:
        report = backup_svc.preview_import(db, p)
    except Exception:
        p.unlink(missing_ok=True)
        raise
    return {"token": token, "report": report}


@router.post("/import/story/confirm")
def import_confirm(body: dict[str, Any], ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    token = str(body.get("token", ""))
    if not TOKEN_RE.match(token):
        raise ValueError("Invalid import token")
    p = ctx.settings.tmp_dir / f"import_{token}.zip"
    if not p.is_file():
        raise ValueError("The uploaded package expired; upload it again.")
    new_id = backup_svc.import_story(db, p, ctx.settings.uploads_dir, title_suffix=body.get("title_suffix", " (imported)"))
    p.unlink(missing_ok=True)
    return {"story_id": new_id}


# --------------------------------------------------------------------------- full backups
@router.get("/backups")
def list_backups(ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    files = sorted(ctx.settings.backups_dir.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
    return {"backups": [{"name": f.name, "size": f.stat().st_size, "modified": f.stat().st_mtime} for f in files],
            "folder": str(ctx.settings.backups_dir), "last_backup_at": settings_service.get(db, "last_backup_at")}


@router.post("/backups")
def create_backup(ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    out = ctx.settings.backups_dir / f"storycore_backup_{now_iso()[:19].replace(':', '-')}.zip"
    db.commit()  # make sure everything visible to this session is flushed before snapshotting
    res = backup_svc.full_backup(ctx.settings.db_path, ctx.settings.uploads_dir, out)
    settings_service.set_many(db, {"last_backup_at": now_iso()})
    return {"name": out.name, **res}


def _backup_file(ctx: AppContext, name: str) -> Path:
    if "/" in name or "\\" in name or not name.endswith(".zip"):
        raise HTTPException(404)
    p = (ctx.settings.backups_dir / name).resolve()
    if ctx.settings.backups_dir.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404)
    return p


@router.get("/backups/{name}/download")
def download_backup(name: str, ctx: AppContext = Depends(get_ctx)):
    p = _backup_file(ctx, name)
    return FileResponse(p, filename=p.name, media_type="application/zip")


@router.post("/backups/{name}/verify")
def verify_backup(name: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return backup_svc.verify_backup(_backup_file(ctx, name))


@router.post("/backups/upload")
async def upload_backup(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    name = f"uploaded_{now_iso()[:19].replace(':', '-')}.zip"
    p = ctx.settings.backups_dir / name
    p.write_bytes(await file.read())
    try:
        report = backup_svc.verify_backup(p)
    except Exception:
        p.unlink(missing_ok=True)
        raise
    return {"name": name, "verify": report}


@router.post("/backups/{name}/restore")
def restore_backup(name: str, body: dict[str, Any], ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    if not body.get("confirm"):
        raise ValueError("Restoring replaces ALL current data; confirmation required.")
    p = _backup_file(ctx, name)
    report = backup_svc.verify_backup(p)
    if not report["ok"]:
        raise ValueError(f"Backup failed its integrity check: {report['integrity']}")
    if any(j.status == "streaming" for j in ctx.generations.jobs.values()):
        raise ValueError("Stop running generations before restoring.")
    safety = ctx.settings.backups_dir / f"pre_restore_{now_iso()[:19].replace(':', '-')}.zip"
    backup_svc.full_backup(ctx.settings.db_path, ctx.settings.uploads_dir, safety)
    backup_svc.restore_full(p, ctx.settings.db_path, ctx.settings.uploads_dir)
    ctx.db.dispose()  # drop pooled connections so new sessions start fresh on the restored schema
    ctx.db = Database(ctx.settings.db_path)
    ctx.db.migrate(ctx.settings.backups_dir)
    return {"ok": True, "restored": name, "safety_backup": safety.name, "counts": report["counts"]}


# --------------------------------------------------------------------------- separate exports
@router.get("/notes/export")
def export_notes(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"format": "storycore-notes", "format_version": 1, "exported_at": now_iso(),
            "notes": [n.to_dict() for n in db.scalars(select(UserNote))]}


@router.post("/notes/import")
def import_notes(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.get("format") not in ("storycore-notes", "lumencia-notes"):
        raise ValueError("Not a StoryCore notes file.")
    g = next((n for n in body.get("notes", []) if n.get("scope") == "global"), None)
    if g:
        cur = db.scalar(select(UserNote).where(UserNote.scope == "global"))
        if cur and cur.content.strip() and cur.content != g.get("content"):
            cur.content = cur.content + "\n\n--- imported ---\n" + g.get("content", "")  # append, never overwrite silently
        elif cur:
            cur.content = g.get("content", "")
    return {"ok": True, "note": "Global note imported (appended to the existing note). Story notes travel with story packages."}


@router.get("/local-canon/export")
def export_canon(fmt: str = "json", db: Session = Depends(get_db)):
    rows = list(db.scalars(select(LocalCanon).where(LocalCanon.status != "rejected")))
    if fmt == "md":
        from fastapi.responses import PlainTextResponse

        md = "# Local canon\n\n" + "\n\n".join(f"## {c.title}\n_status: {c.status}, scope: {c.scope}_\n\n{c.content}" for c in rows)
        return PlainTextResponse(md, media_type="text/markdown")
    return {"format": "storycore-local-canon", "format_version": 1, "items": [c.to_dict() for c in rows]}


@router.post("/local-canon/import")
def import_canon(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.get("format") not in ("storycore-local-canon", "lumencia-local-canon"):
        raise ValueError("Not a StoryCore local-canon file.")
    n = 0
    for it in body.get("items", []):
        db.add(LocalCanon(title=it.get("title", "Imported"), content=it.get("content", ""), world_id=it.get("world_id"),
                          story_id=None, scope="local" if it.get("scope") == "story" else it.get("scope", "local"),
                          tags_json=it.get("tags_json") or [], entity_ids_json=it.get("entity_ids_json") or [],
                          status="pending"))
        n += 1
    return {"added": n, "note": "Imported entries are pending until you approve them."}
