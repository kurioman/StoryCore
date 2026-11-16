from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import ImportRun, LocalCanon, LoreChunk, LoreEntity, World, now_iso
from ..services import context_builder, lore_import
from ..services.runtime import AppContext

router = APIRouter(tags=["lore"])


def public_world(w: World) -> dict[str, Any]:
    """A world as the player may see it: the narrator-only notes (``data_json["hidden"]``) are never sent."""
    d = w.to_dict()
    d["data_json"] = {k: v for k, v in (w.data_json or {}).items() if k != "hidden"}
    return d


@router.get("/worlds")
def worlds(db: Session = Depends(get_db)) -> dict[str, Any]:
    out = []
    for w in db.scalars(select(World)):
        d = public_world(w)
        d.pop("system_prompt", None)
        d["has_system_prompt"] = bool(w.system_prompt)
        d["entity_count"] = db.query(LoreEntity).filter(LoreEntity.world_id == w.id).count()
        out.append(d)
    return {"worlds": out}


@router.get("/worlds/{wid}/cover")
def world_cover(wid: str, db: Session = Depends(get_db)):
    """The pack's cover image for the story library (pack.json "cover", format 2). 404 when there is none."""
    from fastapi.responses import FileResponse
    w = db.get(World, wid)
    rel = ((w.data_json or {}).get("library") or {}).get("cover") if w else None
    if not w or not rel or not w.source_path:
        raise HTTPException(404, "No cover")
    base = Path(w.source_path).resolve()
    f = (base / rel).resolve()
    if base not in f.parents or not f.is_file():
        raise HTTPException(404, "No cover")
    return FileResponse(f, headers={"Cache-Control": "no-cache"})


@router.get("/worlds/{wid}/roles")
def world_roles(wid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Established posts and closed groups (lore-derived + owner-confirmed), ambiguous titles and lore/owner conflicts."""
    from ..services import roles
    from ..services.entities import build_index

    if db.get(World, wid) is None:
        raise HTTPException(404, "World not found")
    return roles.build_registry(db, wid, build_index(db, wid))


@router.get("/worlds/{wid}")
def world(wid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    w = db.get(World, wid)
    if w is None:
        raise HTTPException(404, "World not found")
    cats: dict[str, int] = {}
    for (c,) in db.execute(select(LoreEntity.category).where(LoreEntity.world_id == wid)):
        cats[c] = cats.get(c, 0) + 1
    last = db.scalar(select(ImportRun).where(ImportRun.world_id == wid).order_by(ImportRun.started_at.desc()).limit(1))
    return {**public_world(w), "categories": cats, "last_import": last.to_dict() if last else None}


class ImportIn(BaseModel):
    path: str


def _approved_lore_path(ctx: AppContext, raw: str) -> Path:
    """Only folders/zips found by discovery (inside the project) or previously imported sources are accepted."""
    p = Path(raw).resolve()
    allowed = {Path(c["path"]).resolve() for c in lore_import.discover(ctx.settings.project_root)}
    with ctx.db.session() as db:
        allowed |= {Path(w.source_path).resolve() for w in db.scalars(select(World)) if w.source_path}
    if p in allowed:
        return p
    if p.is_dir() and lore_import.looks_like_pack(p):
        return p  # an explicit, user-typed folder that looks like a lore pack
    if p.is_file() and p.suffix.lower() == ".zip":
        return p
    raise ValueError("That path is not a recognised lore pack folder or .zip file.")


@router.post("/lore/import")
def import_lore(body: ImportIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    p = _approved_lore_path(ctx, body.path)
    if p.suffix.lower() == ".zip":
        p = lore_import.extract_zip(p, ctx.settings.data_dir / "imports")
    return lore_import.import_pack(db, p)


@router.post("/lore/import-zip")
async def import_lore_zip(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(dir=ctx.settings.tmp_dir) as td:
        zp = Path(td) / Path(file.filename or "lore.zip").name
        zp.write_bytes(await file.read())
        pack = lore_import.extract_zip(zp, ctx.settings.data_dir / "imports")
    return lore_import.import_pack(db, pack)


@router.post("/worlds/{wid}/reimport")
def reimport(wid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    w = db.get(World, wid)
    if w is None or not w.source_path:
        raise HTTPException(404, "World not found")
    if not Path(w.source_path).is_dir():
        raise ValueError(f"Source folder no longer exists: {w.source_path}")
    return lore_import.import_pack(db, Path(w.source_path))


@router.get("/lore/packs/check")
def check_packs(world_id: str = "", ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Lore pack checker (services/pack_check.py): every pack in the Lorepack folder, or the source folder of one
    world. Read-only: runs on a throw-away database."""
    from ..services import pack_check

    if world_id:
        w = db.get(World, world_id)
        if w is None or not w.source_path:
            raise HTTPException(404, "World not found")
        return {"packs": [pack_check.check_pack(Path(w.source_path))]}
    return {"packs": pack_check.check_all(ctx.settings.project_root / "Lorepack")}


@router.get("/lore/import-runs")
def import_runs(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(ImportRun).where(ImportRun.kind == "lore").order_by(ImportRun.started_at.desc()).limit(20))
    return {"runs": [r.to_dict() for r in rows]}


@router.get("/worlds/{wid}/entities")
def entities(wid: str, category: str = "", q: str = "", confidence: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    query = select(LoreEntity).where(LoreEntity.world_id == wid)
    if category:
        query = query.where(LoreEntity.category == category)
    if confidence:
        query = query.where(LoreEntity.confidence == confidence)
    rows = list(db.scalars(query.order_by(LoreEntity.category, LoreEntity.name)))
    if q:
        ids = set()
        fq = context_builder.fts_query(q) or q
        try:
            ids = {r[0] for r in db.execute(text("SELECT entity_id FROM lore_fts WHERE lore_fts MATCH :q AND world_id = :w"), {"q": fq, "w": wid})}
        except Exception:
            pass
        ql = q.lower()
        rows = [r for r in rows if r.entity_id in ids or ql in r.name.lower() or any(ql in a.lower() for a in r.aliases_json or [])]
    return {"entities": [entity_summary(r) for r in rows]}


def entity_summary(r: LoreEntity) -> dict[str, Any]:
    """The one public shape for a lore record (list and detail share it; detail adds `data` and `chunk_id`)."""
    return {"id": r.id, "entity_id": r.entity_id, "category": r.category, "type": r.entity_type or "", "name": r.name,
            "aliases": [a for a in (r.aliases_json or []) if isinstance(a, str)], "summary": r.summary or "",
            "confidence": r.confidence, "canon_status": r.canon_status,
            "source_ids": [s for s in (r.source_ids_json or []) if isinstance(s, str)], "file": r.file or ""}


@router.get("/worlds/{wid}/entities/{entity_id}")
def entity(wid: str, entity_id: str, category: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(LoreEntity).where(LoreEntity.world_id == wid, LoreEntity.entity_id == entity_id)
    if category:  # entity ids are only unique per category (e.g. a faction and a polity can share one)
        q = q.where(LoreEntity.category == category)
    rows = list(db.scalars(q))
    if not rows:
        raise HTTPException(404, "Lore record not found")
    r = rows[0]
    sources = {s.entity_id: s.data_json or {} for s in db.scalars(select(LoreEntity).where(LoreEntity.world_id == wid, LoreEntity.category == "source"))}
    chunk = db.scalar(select(LoreChunk).where(LoreChunk.entity_row_id == r.id))
    canon = list(db.scalars(select(LocalCanon).where(LocalCanon.overrides_entity_id == entity_id)))
    src_out = []
    for sid in entity_summary(r)["source_ids"]:
        s = sources.get(sid) or {}
        src_out.append({"id": sid, "title": s.get("title") or sid, "url": s.get("url"), "reliability": s.get("reliability")})
    return {"entity": {**entity_summary(r), "data": r.data_json if isinstance(r.data_json, dict) else {},
                       "chunk_id": chunk.id if chunk else None},
            "sources": src_out,
            "local_canon": [{"id": c.id, "title": c.title, "content": c.content, "status": c.status} for c in canon],
            "read_only": True}


@router.get("/worlds/{wid}/search")
def search(wid: str, q: str, limit: int = 20, db: Session = Depends(get_db)) -> dict[str, Any]:
    fq = context_builder.fts_query(q) or q
    out = []
    try:
        rows = db.execute(text("SELECT id, snippet(lore_fts, 5, '[', ']', ' … ', 18) FROM lore_fts WHERE lore_fts MATCH :q "
                               "AND world_id = :w ORDER BY rank LIMIT :n"), {"q": fq, "w": wid, "n": limit}).fetchall()
    except Exception:
        rows = []
    for cid, snip in rows:
        c = db.get(LoreChunk, cid)
        if c:
            out.append({"chunk_id": c.id, "title": c.title, "category": c.category, "entity_id": c.entity_id,
                        "snippet": snip, "confidence": c.confidence, "canon_status": c.canon_status})
    canon = []
    try:
        for (cid,) in db.execute(text("SELECT id FROM canon_fts WHERE canon_fts MATCH :q LIMIT 10"), {"q": fq}):
            c = db.get(LocalCanon, cid)
            if c and c.status != "rejected":
                canon.append(c.to_dict())
    except Exception:
        pass
    return {"results": out, "local_canon": canon}


@router.get("/lore/chunks/{cid}")
def chunk(cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(LoreChunk, cid)
    if c is None:
        raise HTTPException(404, "Chunk not found")
    return c.to_dict()


# --------------------------------------------------------------------------- local canon
class CanonIn(BaseModel):
    title: str
    content: str
    world_id: Optional[str] = None
    story_id: Optional[str] = None
    scope: str = "story"  # story | local | global_draft
    tags: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    overrides_entity_id: Optional[str] = None
    source_message_id: Optional[str] = None
    confidence: float = 1.0
    approve: bool = False


@router.get("/local-canon")
def list_canon(story_id: Optional[str] = None, world_id: Optional[str] = None, status: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(LocalCanon)
    if story_id:
        q = q.where((LocalCanon.story_id == story_id) | (LocalCanon.scope != "story"))
    if world_id:
        q = q.where((LocalCanon.world_id == world_id) | (LocalCanon.world_id.is_(None)))
    if status:
        q = q.where(LocalCanon.status == status)
    return {"items": [c.to_dict() for c in db.scalars(q.order_by(LocalCanon.created_at.desc()))]}


@router.post("/local-canon")
def create_canon(body: CanonIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.scope not in ("story", "local", "global_draft"):
        raise ValueError("Invalid scope")
    c = LocalCanon(title=body.title[:300], content=body.content, world_id=body.world_id, story_id=body.story_id if body.scope == "story" else None,
                   scope=body.scope, tags_json=body.tags, entity_ids_json=body.entity_ids, overrides_entity_id=body.overrides_entity_id,
                   source_message_id=body.source_message_id, confidence=body.confidence,
                   status="approved" if body.approve else "pending")
    db.add(c)
    db.flush()
    return c.to_dict()


class CanonPatch(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    entity_ids: Optional[list[str]] = None


@router.patch("/local-canon/{cid}")
def patch_canon(cid: str, body: CanonPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(LocalCanon, cid)
    if c is None:
        raise HTTPException(404, "Not found")
    if body.status is not None and body.status not in ("pending", "approved", "rejected"):
        raise ValueError("Invalid status")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, {"tags": "tags_json", "entity_ids": "entity_ids_json"}.get(k, k), v)
    c.updated_at = now_iso()
    return c.to_dict()


@router.post("/lore/copy-to-canon")
def copy_to_canon(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    """'Create local override': copy a baseline record into editable local canon. The baseline stays untouched."""
    le = db.scalar(select(LoreEntity).where(LoreEntity.world_id == body.get("world_id"), LoreEntity.entity_id == body.get("entity_id")))
    if le is None:
        raise HTTPException(404, "Entity not found")
    ch = db.scalar(select(LoreChunk).where(LoreChunk.entity_row_id == le.id))
    c = LocalCanon(title=f"Local override: {le.name}", content=ch.content if ch else le.summary, world_id=le.world_id,
                   story_id=body.get("story_id"), scope="story" if body.get("story_id") else "local",
                   entity_ids_json=[le.entity_id], overrides_entity_id=le.entity_id, status="pending")
    db.add(c)
    db.flush()
    return c.to_dict()
