"""Story export/import packages and full backups. API keys/secrets are never included."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import APP_VERSION, EXPORT_FORMAT_VERSION
from ..models import (Avatar, CharacterDiscovery, EntityFact, ExtractionCursor, LocalCanon, MemoryExtractionRun, Message,
                      MessageBranch, MessageVersion, Recap, Savepoint, SlashCommand, StateProposal, Story, StoryEvent,
                      StoryState, TurnAnalysis, UserNote, World, now_iso)
from .idmap import remap, unresolved

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
STORY_TABLES: list[tuple[str, type]] = [
    ("branches", MessageBranch), ("messages", Message), ("message_versions", MessageVersion), ("states", StoryState),
    ("proposals", StateProposal), ("events", StoryEvent), ("facts", EntityFact), ("extraction_runs", MemoryExtractionRun),
    ("cursors", ExtractionCursor), ("recaps", Recap), ("savepoints", Savepoint), ("notes", UserNote),
    ("local_canon", LocalCanon), ("commands", SlashCommand),
    # added in 1.1 (packages from 1.0 simply have none of these)
    ("turn_analyses", TurnAnalysis), ("discoveries", CharacterDiscovery),
]
NEVER_EXPORTED = ["API keys and other secrets", "provider credentials", "app logs"]


def _rows(db: Session, model: type, story_id: str) -> list[dict[str, Any]]:
    if model is MessageVersion:
        q = select(MessageVersion).join(Message, Message.id == MessageVersion.message_id).where(Message.story_id == story_id)
    else:
        q = select(model).where(model.story_id == story_id)
    return [r.to_dict() for r in db.scalars(q)]


def export_story(db: Session, story_id: str, uploads_dir: Path, out_path: Path) -> dict[str, Any]:
    story = db.get(Story, story_id)
    if story is None:
        raise ValueError("Story not found")
    payload: dict[str, Any] = {"story": story.to_dict()}
    for key, model in STORY_TABLES:
        payload[key] = _rows(db, model, story_id)
    avatar = db.get(Avatar, story.active_avatar_id) if story.active_avatar_id else None
    payload["avatar"] = avatar.to_dict() if avatar else None
    world = db.get(World, story.world_id) if story.world_id else None
    payload["world_ref"] = {"id": world.id, "slug": world.slug, "name": world.name, "import_version": world.import_version} if world else None
    assets = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if avatar and avatar.portrait_path:
            src = (uploads_dir / avatar.portrait_path).resolve()
            if src.is_file() and uploads_dir.resolve() in src.parents:
                arc = f"assets/{avatar.portrait_path}"
                zf.write(src, arc)
                assets.append({"kind": "avatar_portrait", "path": arc, "ref": avatar.portrait_path})
        if story.cover_path:
            src = (uploads_dir / story.cover_path).resolve()
            if src.is_file() and uploads_dir.resolve() in src.parents:
                zf.write(src, f"assets/{story.cover_path}")
                assets.append({"kind": "cover", "path": f"assets/{story.cover_path}", "ref": story.cover_path})
        manifest = {"format": "story-story", "format_version": EXPORT_FORMAT_VERSION, "app_version": APP_VERSION,
                    "exported_at": now_iso(), "story_id": story.id, "title": story.title,
                    "counts": {k: len(payload[k]) for k, _ in STORY_TABLES}, "assets": assets,
                    "never_included": NEVER_EXPORTED}
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr("story.json", json.dumps(payload, ensure_ascii=False))
    return manifest


def read_package(path: Path) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "manifest.json" not in names or "story.json" not in names:
                raise ValueError("This file is not a story package (manifest.json/story.json missing).")
            manifest = json.loads(zf.read("manifest.json"))
            payload = json.loads(zf.read("story.json"))
    except zipfile.BadZipFile:
        raise ValueError("This file is not a story package (it is not a ZIP archive or it is damaged).") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"This story package is damaged (invalid JSON: {e.msg}).") from None
    if not isinstance(manifest, dict) or not isinstance(payload, dict) or "story" not in payload:
        raise ValueError("This story package is incomplete (story data missing).")
    if manifest.get("format") not in ("story-story", "lumencia-story"):  # lumencia-story: Lumencia Story Desk exports
        raise ValueError("Unknown package format.")
    if int(manifest.get("format_version", 0)) > EXPORT_FORMAT_VERSION:
        raise ValueError("This package was made by a newer version of the app.")
    return manifest, payload, names


def preview_import(db: Session, path: Path) -> dict[str, Any]:
    manifest, payload, names = read_package(path)
    known: set[str] = {payload["story"]["id"]}
    for key, _ in STORY_TABLES:
        for r in payload.get(key, []):
            known.add(r.get("id") or r.get("branch_id"))
    if payload.get("avatar"):
        known.add(payload["avatar"]["id"])
    world_ref = payload.get("world_ref")
    if world_ref:
        known.add(world_ref["id"])
    refs: set[str] = set()
    for key in ("events", "facts", "proposals", "recaps", "branches", "cursors"):
        refs |= unresolved(payload.get(key, []), known, UUID_RE.match)
    missing_assets = [a["path"] for a in manifest.get("assets", []) if a["path"] not in names]
    world_match = None
    if world_ref:
        w = db.get(World, world_ref["id"]) or db.scalar(select(World).where(World.slug == world_ref.get("slug")))
        world_match = {"found": w is not None, "name": world_ref.get("name"), "local_id": w.id if w else None}
    existing = db.get(Story, payload["story"]["id"])
    return {"manifest": manifest, "title": payload["story"]["title"], "counts": manifest.get("counts"),
            "missing_assets": missing_assets, "unresolved_ids": sorted(refs)[:50], "unresolved_count": len(refs),
            "world": world_match, "already_exists": existing is not None,
            "policy": "The story will be imported as a new copy with new IDs. Existing data is never overwritten.",
            "has_avatar": bool(payload.get("avatar"))}


def import_story(db: Session, path: Path, uploads_dir: Path, *, title_suffix: str = "") -> str:
    manifest, payload, names = read_package(path)
    mapping: dict[str, str] = {}

    def new(old: str | None) -> None:
        if old and old not in mapping:
            mapping[old] = str(uuid.uuid4())

    new(payload["story"]["id"])
    for key, _ in STORY_TABLES:
        for r in payload.get(key, []):
            new(r.get("id") or r.get("branch_id"))
    if payload.get("avatar"):
        new(payload["avatar"]["id"])
    world_ref = payload.get("world_ref")
    local_world = None
    if world_ref:
        local_world = db.get(World, world_ref["id"]) or db.scalar(select(World).where(World.slug == world_ref.get("slug")))
        mapping[world_ref["id"]] = local_world.id if local_world else world_ref["id"]

    asset_map: dict[str, str] = {}
    with zipfile.ZipFile(path) as zf:
        for a in manifest.get("assets", []):
            if a["path"] in names:
                ext = Path(a["ref"]).suffix.lower()
                if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    continue
                sub = "avatars" if a["kind"] == "avatar_portrait" else "covers"
                rel = f"{sub}/{uuid.uuid4().hex}{ext}"
                dst = uploads_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(zf.read(a["path"]))
                asset_map[a["ref"]] = rel

    s = remap(payload["story"], mapping)
    s["title"] = (s["title"] + title_suffix)[:300]
    s["world_id"] = local_world.id if local_world else None
    if world_ref and not local_world:  # attached by lore_import once that world is imported here
        s["settings_json"] = {**(s.get("settings_json") or {}),
                              "pending_world": {k: world_ref.get(k) for k in ("id", "slug", "name")}}
    s["cover_path"] = asset_map.get(payload["story"].get("cover_path") or "", None)
    if payload.get("avatar"):
        av = remap(payload["avatar"], mapping)
        av["portrait_path"] = asset_map.get(payload["avatar"].get("portrait_path") or "", None)
        av["name"] = av["name"] + " (imported)"
        db.add(Avatar(**av))
    elif s.get("active_avatar_id"):
        s["active_avatar_id"] = None
    db.add(Story(**s))
    db.flush()
    for key, model in STORY_TABLES:
        for r in payload.get(key, []):
            d = remap(r, mapping)
            if model is LocalCanon and d.get("world_id") and not local_world:
                d["world_id"] = None
            if model is SlashCommand:
                d["builtin"] = False
            db.add(model(**d))
        db.flush()
    return mapping[payload["story"]["id"]]


# --------------------------------------------------------------------------- full backups
BACKUP_FORMAT = "storycore-full-backup"
# formats written by earlier versions (Lumencia Story Desk, then the first refactor) are still accepted
BACKUP_FORMATS = (BACKUP_FORMAT, "story-full-backup", "lumencia-full-backup")
BACKUP_DB_NAMES = ("story.db", "lumencia.db")  # the database inside the zip: current name first


def _backup_db_name(zf: zipfile.ZipFile) -> str | None:
    names = set(zf.namelist())
    return next((n for n in BACKUP_DB_NAMES if n in names), None)


def full_backup(db_path: Path, uploads_dir: Path, out_path: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp())
    try:
        snap = tmp / "story.db"
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(snap)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        manifest = {"format": BACKUP_FORMAT, "format_version": 1, "app_version": APP_VERSION, "created_at": now_iso(),
                    "never_included": NEVER_EXPORTED}
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snap, "story.db")
            if uploads_dir.is_dir():
                for f in uploads_dir.rglob("*"):
                    if f.is_file():
                        zf.write(f, "uploads/" + f.relative_to(uploads_dir).as_posix())
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        return {"path": str(out_path), "size": out_path.stat().st_size, **manifest}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def verify_backup(path: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(path) as zf:
            member = _backup_db_name(zf)
            if "manifest.json" not in zf.namelist() or member is None:
                raise ValueError("Not a StoryCore full backup.")
            manifest = json.loads(zf.read("manifest.json"))
            if manifest.get("format") not in BACKUP_FORMATS:
                raise ValueError("Not a StoryCore full backup.")
            (tmp / "story.db").write_bytes(zf.read(member))
            uploads = [n for n in zf.namelist() if n.startswith("uploads/")]
        con = sqlite3.connect(tmp / "story.db")
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("stories", "messages", "story_events", "avatars")}
            rev = con.execute("SELECT version_num FROM alembic_version").fetchone()
        finally:
            con.close()
        return {"ok": integrity == "ok", "integrity": integrity, "counts": counts, "schema_revision": rev[0] if rev else None,
                "uploads": len(uploads), "manifest": manifest}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def restore_full(path: Path, db_path: Path, uploads_dir: Path) -> None:
    """Replace the database and uploads with a backup's. The database is copied *into* the live file with SQLite's online
    backup API (normal locking; WAL-safe), never by deleting -wal/-shm or overwriting the file: other connections may be
    open (a page loading), and on Windows that failed with WinError 32 or could corrupt the file. Caller re-opens and
    migrates afterwards (an older backup may need migrations)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(path) as zf:
            member = _backup_db_name(zf)
            if member is None:
                raise ValueError("Not a StoryCore full backup.")
            (tmp / "story.db").write_bytes(zf.read(member))
            src = sqlite3.connect(tmp / "story.db")
            dst = sqlite3.connect(db_path, timeout=30)
            try:
                src.backup(dst)
            finally:
                src.close()
                dst.close()
            uploads_dir.mkdir(parents=True, exist_ok=True)
            root = uploads_dir.resolve()
            wanted: dict[Path, str] = {}
            for n in zf.namelist():
                if n.startswith("uploads/") and not n.endswith("/"):
                    p = (uploads_dir / n[len("uploads/"):]).resolve()
                    if root in p.parents:
                        wanted[p] = n
            for f in [x for x in uploads_dir.rglob("*") if x.is_file() and x.resolve() not in wanted]:
                try:
                    f.unlink()
                except OSError:
                    pass  # an image being served right now; an unreferenced leftover is harmless
            for p, n in wanted.items():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(zf.read(n))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def integrity_check(db: Session) -> dict[str, Any]:
    from sqlalchemy import text

    # On a new connection: a pooled one that read a search index before another connection wrote to it gets a false
    # "malformed inverted index" from SQLite, although its data and searches are correct (reproduced on plain SQLite 3.49.1).
    con = sqlite3.connect(db.get_bind().engine.url.database)
    try:
        res = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    fk = db.execute(text("PRAGMA foreign_key_check")).fetchall()
    # app-level consistency: branch heads and message parents must exist
    dangling_heads = db.execute(text("SELECT count(*) FROM message_branches b WHERE head_message_id IS NOT NULL AND "
                                     "NOT EXISTS (SELECT 1 FROM messages m WHERE m.id = b.head_message_id)")).scalar()
    dangling_parents = db.execute(text("SELECT count(*) FROM messages c WHERE parent_id IS NOT NULL AND "
                                       "NOT EXISTS (SELECT 1 FROM messages p WHERE p.id = c.parent_id)")).scalar()
    return {"ok": res == "ok" and not fk and not dangling_heads and not dangling_parents, "sqlite": res,
            "foreign_key_violations": len(fk), "dangling_branch_heads": dangling_heads, "dangling_message_parents": dangling_parents}
