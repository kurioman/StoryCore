from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import AssetManifestEntry, AssetOverride, AssetRoot, LoreEntity, SlugOverride
from ..services import assets as assets_svc
from ..services.entities import Entity, EntityIndex, norm
from ..services.runtime import AppContext

router = APIRouter(tags=["assets"])


def global_index(db: Session) -> EntityIndex:
    ents = [Entity(le.entity_id, le.name, "character", le.entity_type, list(le.aliases_json or []))
            for le in db.scalars(select(LoreEntity).where(LoreEntity.category == "character"))]
    return EntityIndex(ents)


@router.get("/assets/expressions")
def expressions() -> dict[str, Any]:
    return {"expressions": assets_svc.EXPRESSIONS}


@router.get("/assets/roots")
def roots(db: Session = Depends(get_db)) -> dict[str, Any]:
    out = []
    for r in db.scalars(select(AssetRoot)):
        d = r.to_dict()
        d["exists"] = Path(r.path).is_dir()
        d["file_count"] = db.query(AssetManifestEntry).filter(AssetManifestEntry.root_id == r.id).count()
        out.append(d)
    return {"roots": out}


class RootIn(BaseModel):
    path: str
    label: Optional[str] = None
    scan: bool = True


@router.post("/assets/roots")
def add_root(body: RootIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = Path(body.path.strip().strip('"')).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f"Folder not found: {p}")
    if p == Path(p.anchor):
        raise ValueError("Choose a specific image folder, not a drive root.")
    existing = db.scalar(select(AssetRoot).where(AssetRoot.path == str(p)))
    r = existing or AssetRoot(path=str(p), kind="folder", label=body.label or p.name)
    if existing is None:
        db.add(r)
        db.flush()
    report = assets_svc.scan_root(db, r, global_index(db)) if body.scan else None
    return {"root": r.to_dict(), "report": report}


@router.delete("/assets/roots/{rid}")
def remove_root(rid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(AssetRoot, rid)
    if r is None:
        raise HTTPException(404, "Root not found")
    db.delete(r)  # only the registration and manifest; image files are never deleted
    return {"ok": True}


@router.post("/assets/roots/{rid}/scan")
def scan(rid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(AssetRoot, rid)
    if r is None:
        raise HTTPException(404, "Root not found")
    return assets_svc.scan_root(db, r, global_index(db))


@router.post("/assets/rescan-all")
def rescan_all(db: Session = Depends(get_db)) -> dict[str, Any]:
    idx = global_index(db)
    return {"reports": [assets_svc.scan_root(db, r, idx) for r in db.scalars(select(AssetRoot)) if Path(r.path).is_dir()]}


@router.get("/assets/manifest")
def manifest(status: str = "", character_id: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(AssetManifestEntry)
    if status:
        q = q.where(AssetManifestEntry.status.in_(status.split(",")))
    if character_id:
        q = q.where(AssetManifestEntry.character_id == character_id)
    return {"assets": [e.to_dict() for e in db.scalars(q.order_by(AssetManifestEntry.rel_path))]}


@router.get("/assets/characters")
def characters(world_id: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(LoreEntity).where(LoreEntity.category == "character")
    if world_id:
        q = q.where(LoreEntity.world_id == world_id)
    pmap = assets_svc.portrait_map(db)
    out = []
    for le in db.scalars(q.order_by(LoreEntity.name)):
        slots = pmap.get(le.entity_id, {})
        out.append({"id": le.entity_id, "name": le.name, "type": le.entity_type, "aliases": le.aliases_json,
                    "slots": {str(k): v for k, v in slots.items()}, "missing": [s for s in range(1, 7) if s not in slots]})
    known = {c["id"] for c in out}
    for cid, slots in pmap.items():  # portraits mapped to ids not (yet) in lore, e.g. local NPCs
        if cid not in known:
            out.append({"id": cid, "name": cid, "type": "unknown", "aliases": [], "slots": {str(k): v for k, v in slots.items()},
                        "missing": [s for s in range(1, 7) if s not in slots]})
    return {"characters": out}


class OverrideIn(BaseModel):
    asset_id: str
    character_id: Optional[str] = None
    slot: Optional[int] = None
    ignored: bool = False


@router.post("/assets/overrides")
def set_override(body: OverrideIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = db.get(AssetManifestEntry, body.asset_id)
    if e is None:
        raise HTTPException(404, "Asset not found")
    if body.slot is not None and not 1 <= body.slot <= 6:
        raise ValueError("Slot must be 1–6")
    o = db.scalar(select(AssetOverride).where(AssetOverride.root_id == e.root_id, AssetOverride.rel_path == e.rel_path))
    if o is None:
        o = AssetOverride(root_id=e.root_id, rel_path=e.rel_path)
        db.add(o)
    o.character_id, o.slot, o.ignored = body.character_id, body.slot, body.ignored
    db.flush()
    r = db.get(AssetRoot, e.root_id)
    return assets_svc.scan_root(db, r, global_index(db))


@router.delete("/assets/overrides/{asset_id}")
def clear_override(asset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = db.get(AssetManifestEntry, asset_id)
    if e is None:
        raise HTTPException(404, "Asset not found")
    o = db.scalar(select(AssetOverride).where(AssetOverride.root_id == e.root_id, AssetOverride.rel_path == e.rel_path))
    if o:
        db.delete(o)
        db.flush()
    return assets_svc.scan_root(db, db.get(AssetRoot, e.root_id), global_index(db))


class SlugIn(BaseModel):
    slug: str
    character_id: Optional[str] = None  # None removes the mapping


@router.post("/assets/slug-overrides")
def slug_override(body: SlugIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    key = norm(body.slug)
    row = db.get(SlugOverride, key)
    if body.character_id:
        if row is None:
            db.add(SlugOverride(slug=key, character_id=body.character_id))
        else:
            row.character_id = body.character_id
    elif row is not None:
        db.delete(row)
    db.flush()
    idx = global_index(db)
    return {"reports": [assets_svc.scan_root(db, r, idx) for r in db.scalars(select(AssetRoot)) if Path(r.path).is_dir()]}


@router.get("/assets/{asset_id}/image")
def image(asset_id: str, variant: str = "card", ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    try:
        src = assets_svc.file_for(db, asset_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Image not available")
    if variant == "full":
        return FileResponse(src, headers={"Cache-Control": "max-age=3600"})
    if variant not in assets_svc.VARIANTS:
        raise HTTPException(400, "Unknown variant")
    key = hashlib.sha1(str(src).encode()).hexdigest()[:16]
    try:
        out = assets_svc.derivative(src, ctx.settings.cache_dir, key, variant)
    except Exception:
        raise HTTPException(422, "Image could not be decoded")
    return FileResponse(out, media_type="image/webp", headers={"Cache-Control": "max-age=86400"})


@router.post("/assets/upload")
async def upload(files: list[UploadFile] = File(...), relative_paths: str = Form(""), ctx: AppContext = Depends(get_ctx),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    """Folder upload from the browser (webkitdirectory). Files are copied into the app data folder."""
    rels = [r for r in relative_paths.split("\n")] if relative_paths else []
    batch = ctx.settings.uploads_dir / "assets" / f"upload_{uuid.uuid4().hex[:8]}"
    saved = 0
    for i, f in enumerate(files):
        name = rels[i] if i < len(rels) and rels[i] else (f.filename or f"file{i}")
        parts = [re.sub(r"[^A-Za-z0-9._\- ()]", "_", p) for p in Path(name).parts if p not in ("..", ".", "/", "\\")]
        if len(parts) > 1:
            parts = parts[1:]  # drop the top-level folder name the browser includes
        if not parts or Path(parts[-1]).suffix.lower() not in assets_svc.IMAGE_EXTS:
            continue
        dst = batch.joinpath(*parts)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(await f.read())
        saved += 1
    if not saved:
        raise ValueError("No image files found in the selection.")
    r = AssetRoot(path=str(batch.resolve()), kind="uploaded", label=f"Uploaded images ({saved})")
    db.add(r)
    db.flush()
    return {"root": r.to_dict(), "report": assets_svc.scan_root(db, r, global_index(db))}


@router.post("/assets/roots/{rid}/copy-to-app-data")
def copy_to_app_data(rid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(AssetRoot, rid)
    if r is None:
        raise HTTPException(404, "Root not found")
    dst = ctx.settings.uploads_dir / "assets" / f"copy_{re.sub(r'[^A-Za-z0-9_]', '_', r.label)[:30]}_{uuid.uuid4().hex[:6]}"
    src = Path(r.path)
    n = 0
    for f in src.rglob("*"):
        if f.is_file() and f.suffix.lower() in assets_svc.IMAGE_EXTS:
            t = dst / f.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
            n += 1
    # carry manual mappings over to the copy
    nr = AssetRoot(path=str(dst.resolve()), kind="uploaded", label=f"{r.label} (app copy)")
    db.add(nr)
    db.flush()
    for o in db.scalars(select(AssetOverride).where(AssetOverride.root_id == r.id)):
        db.add(AssetOverride(root_id=nr.id, rel_path=o.rel_path, character_id=o.character_id, slot=o.slot, ignored=o.ignored))
    db.flush()
    return {"root": nr.to_dict(), "copied": n, "report": assets_svc.scan_root(db, nr, global_index(db)),
            "note": "The original folder is still registered; remove it if you only want to use the copy."}
