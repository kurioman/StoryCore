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
from ..services.entities import EntityIndex, norm
from ..services.runtime import AppContext

router = APIRouter(tags=["assets"])


def global_index(db: Session) -> EntityIndex:
    """Every world's characters (kept for callers that need it; scans use assets_svc.index_for_root)."""
    return assets_svc.character_index(db)


@router.get("/assets/expressions")
def expressions() -> dict[str, Any]:
    return {"expressions": assets_svc.EXPRESSIONS}


@router.get("/assets/roots")
def roots(world_id: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    """The portrait folders; with ``world_id``: that world's folders and the shared ones (v0.5)."""
    out = []
    for r in db.scalars(select(AssetRoot)):
        if world_id and r.world_id not in (world_id, None):
            continue
        d = r.to_dict()
        d["exists"] = Path(r.path).is_dir()
        d["file_count"] = db.query(AssetManifestEntry).filter(AssetManifestEntry.root_id == r.id).count()
        out.append(d)
    return {"roots": out}


class RootIn(BaseModel):
    path: str
    label: Optional[str] = None
    scan: bool = True
    world_id: Optional[str] = None  # v0.5: the story world the folder belongs to (None: shared)


class RootPatch(BaseModel):
    world_id: Optional[str] = None


@router.patch("/assets/roots/{rid}")
def patch_root(rid: str, body: RootPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    """v0.5: tie a portrait folder to one story world (or make it shared), then match it again against those characters."""
    from ..models import World
    r = db.get(AssetRoot, rid)
    if r is None:
        raise HTTPException(404, "Root not found")
    if body.world_id and db.get(World, body.world_id) is None:
        raise ValueError("Unknown world")
    r.world_id = body.world_id or None
    db.flush()
    report = assets_svc.scan_root(db, r, assets_svc.index_for_root(db, r)) if Path(r.path).is_dir() else None
    return {"root": r.to_dict(), "report": report}


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
        r.world_id = body.world_id or None
        db.add(r)
        db.flush()
    report = assets_svc.scan_root(db, r, assets_svc.index_for_root(db, r)) if body.scan else None
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
    return assets_svc.scan_root(db, r, assets_svc.index_for_root(db, r))


@router.post("/assets/rescan-all")
def rescan_all(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"reports": [assets_svc.scan_root(db, r, assets_svc.index_for_root(db, r))
                        for r in db.scalars(select(AssetRoot)) if Path(r.path).is_dir()]}


@router.get("/assets/manifest")
def manifest(status: str = "", character_id: str = "", world_id: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(AssetManifestEntry)
    if world_id:  # v0.5: that world's folders and the shared ones
        q = q.where(AssetManifestEntry.root_id.in_(select(AssetRoot.id).where(
            (AssetRoot.world_id == world_id) | AssetRoot.world_id.is_(None))))
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
    # v0.5: portraits are per world (the same character can look different from one story to the next); without a
    # world_id every world is listed with its own portraits (an entry per world: "world_id" tells them apart)
    pmaps = {w: assets_svc.portrait_map(db, w) for w in ([world_id] if world_id else
                                                         [x for (x,) in db.execute(select(LoreEntity.world_id).distinct())])}
    out = []
    for le in db.scalars(q.order_by(LoreEntity.name)):
        slots = pmaps.get(le.world_id, {}).get(le.entity_id, {})
        out.append({"id": le.entity_id, "world_id": le.world_id, "name": le.name, "type": le.entity_type,
                    "aliases": le.aliases_json, "slots": {str(k): v for k, v in slots.items()},
                    "missing": [s for s in range(1, 7) if s not in slots]})
    if world_id:
        known = {c["id"] for c in out}
        for cid, slots in pmaps[world_id].items():  # portraits mapped to ids not (yet) in lore, e.g. local NPCs
            if cid not in known:
                out.append({"id": cid, "world_id": world_id, "name": cid, "type": "unknown", "aliases": [],
                            "slots": {str(k): v for k, v in slots.items()}, "missing": [s for s in range(1, 7) if s not in slots]})
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
    return assets_svc.scan_root(db, r, assets_svc.index_for_root(db, r))


@router.delete("/assets/overrides/{asset_id}")
def clear_override(asset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = db.get(AssetManifestEntry, asset_id)
    if e is None:
        raise HTTPException(404, "Asset not found")
    o = db.scalar(select(AssetOverride).where(AssetOverride.root_id == e.root_id, AssetOverride.rel_path == e.rel_path))
    if o:
        db.delete(o)
        db.flush()
    return assets_svc.scan_root(db, (root := db.get(AssetRoot, e.root_id)), assets_svc.index_for_root(db, root))


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
    return {"reports": [assets_svc.scan_root(db, r, assets_svc.index_for_root(db, r))
                        for r in db.scalars(select(AssetRoot)) if Path(r.path).is_dir()]}


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
async def upload(files: list[UploadFile] = File(...), relative_paths: str = Form(""), world_id: str = Form(""),
                 ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
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
    r = AssetRoot(path=str(batch.resolve()), kind="uploaded", label=f"Uploaded images ({saved})",
                  world_id=world_id or None)  # v0.5: the story shown on the Portraits page
    db.add(r)
    db.flush()
    return {"root": r.to_dict(), "report": assets_svc.scan_root(db, r, assets_svc.index_for_root(db, r))}


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
    nr = AssetRoot(path=str(dst.resolve()), kind="uploaded", label=f"{r.label} (app copy)", world_id=r.world_id)
    db.add(nr)
    db.flush()
    for o in db.scalars(select(AssetOverride).where(AssetOverride.root_id == r.id)):
        db.add(AssetOverride(root_id=nr.id, rel_path=o.rel_path, character_id=o.character_id, slot=o.slot, ignored=o.ignored))
    db.flush()
    return {"root": nr.to_dict(), "copied": n, "report": assets_svc.scan_root(db, nr, assets_svc.index_for_root(db, nr)),
            "note": "The original folder is still registered; remove it if you only want to use the copy."}
