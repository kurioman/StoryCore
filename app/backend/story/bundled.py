"""Lore packs found next to the application: every folder in ``<project>/Lorepack`` with a ``pack.json``.

At every start, before the app serves its pages (in a worker thread; a broken pack never stops the app):

1. stored lore and portrait folders that no longer exist are found again by folder name under ``Lorepack`` (moving or
   renaming the project folder loses nothing);
2. each pack is imported when its world does not exist yet, and re-imported when its lore files changed since the last
   import (edit a pack, restart the app). Base lore is a read-only snapshot, so a re-import never touches stories, the
   player's corrections or anything else the player made;
3. each pack's portrait folder (``pack.json`` → ``files.images``) is registered and scanned when it is new or its images
   changed.

Packs without a ``pack.json`` are left alone (they can still be imported by hand from Home). Nothing is created for the
player: no story, avatar or key.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy import select

from .models import AssetRoot, World
from .services import assets as assets_svc
from .services import lore_import, pack_manifest
from .services.runtime import AppContext

log = logging.getLogger("story")
PACKS_DIR = "Lorepack"  # every lore pack lives in <project>/Lorepack/<pack folder>
LORE_SUFFIXES = (".json", ".md")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
# Raise when the lore importer changes what it reads, so every pack is re-imported once with the new rules.
IMPORTER_VERSION = "6"  # 3: narrator-only "hidden" fields; 4: starters[].scene; 5: library card (pack.json format 2);
# 6: compact lore records, no AI instructions or openings retrieved as lore (phase 9)


def _fingerprint(folder: Path, suffixes: tuple[str, ...], skip: Path | None = None) -> str:
    """Changes when a file of these types is added, removed, renamed or modified (by size or time)."""
    h = hashlib.sha1()
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in suffixes or (skip and skip in p.parents):
            continue
        st = p.stat()
        h.update(f"{p.relative_to(folder).as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def _relocated(stored: str | None, packs: Path, depth: int) -> Path | None:
    """A stored folder that no longer exists, found again by its own name inside the packs folder (``depth`` 1 = a pack
    folder, 2 = a folder inside a pack). None when the stored folder still exists or there is not exactly one match."""
    if not stored or Path(stored).is_dir() or not packs.is_dir():
        return None
    name = stored.replace("\\", "/").rstrip("/").split("/")[-1].lower()
    level = [packs]
    for _ in range(depth):
        level = [c for d in level for c in d.iterdir() if c.is_dir()]
    hits = [c for c in level if c.name.lower() == name]
    return hits[0] if len(hits) == 1 else None


def _repoint(ctx: AppContext, packs: Path) -> int:
    """Lore and portrait folders are stored as absolute paths; after the project folder is moved, renamed or
    reorganised they are found again by folder name under ``Lorepack``."""
    moved = 0
    with ctx.db.session() as db:
        for world in db.scalars(select(World)):
            new = _relocated(world.source_path, packs, 1)
            if new:
                world.source_path = str(new)
                moved += 1
        for root in db.scalars(select(AssetRoot)):
            if root.kind != "folder":
                continue
            new = _relocated(root.path, packs, 2) or _relocated(root.path, packs, 1)
            if new:
                root.path = str(new)
                moved += 1
    return moved


def _sync_pack(ctx: AppContext, folder: Path, seen: dict[str, Path]) -> str:
    """Import / re-import one pack and its portraits as needed; returns what was done (for the log)."""

    manifest, report = pack_manifest.load(folder)
    if manifest is None:
        return f"skipped ({'; '.join(report['errors']) or 'no usable pack.json'})"
    pid = manifest["id"]
    if pid in seen:
        return f"skipped: id \"{pid}\" is already used by {seen[pid].name}"
    seen[pid] = folder
    images = folder / manifest["files"]["images"] if manifest["files"].get("images") else None
    lore_fp = IMPORTER_VERSION + ":" + _fingerprint(folder, LORE_SUFFIXES, skip=images)
    done = []
    reimported = False
    with ctx.db.session() as db:
        world = db.scalar(select(World).where(World.slug == pid))
        stored = (world.data_json or {}).get("pack_fingerprint") if world else None
        if world is None or stored != lore_fp or Path(world.source_path or "") != folder:
            kept = {k: v for k, v in ((world.data_json or {}) if world else {}).items() if k == "images_fingerprint"}
            result = lore_import.import_pack(db, folder)
            world = db.scalar(select(World).where(World.slug == pid))
            world.data_json = {**(world.data_json or {}), **kept, "pack_fingerprint": lore_fp}
            done.append(f"{'re-imported' if stored else 'imported'} ({result['report'].get('entity_total', 0)} lore records)")
            reimported = True
    if images and images.is_dir():
        img_fp = _fingerprint(images, IMAGE_SUFFIXES)
        with ctx.db.session() as db:
            world = db.scalar(select(World).where(World.slug == pid))
            root = db.scalar(select(AssetRoot).where(AssetRoot.path == str(images)))
            # rescan when the images changed, or the lore did (new characters can claim existing portraits)
            # (v0.5) and when the folder is not yet tied to its world: portraits are matched within one world only
            if (root is None or reimported or root.world_id != world.id
                    or (world.data_json or {}).get("images_fingerprint") != img_fp):
                if root is None:
                    root = AssetRoot(path=str(images), kind="folder", label=images.name)
                    db.add(root)
                root.world_id = world.id
                db.flush()
                scan = assets_svc.scan_root(db, root, assets_svc.index_for_root(db, root))
                world.data_json = {**(world.data_json or {}), "images_fingerprint": img_fp}
                done.append(f"portraits scanned ({scan.get('by_status', {})})")
    return ", ".join(done) or "up to date"


def sync_lore_packs(ctx: AppContext) -> None:
    """Never stops the app: if this fails, Home still offers the manual "Import lore" and "Scan portraits" buttons."""
    try:
        _sync_lore_packs(ctx)
    finally:
        try:  # v0.5: an older copy of a pack's image folder belongs to that pack's world, never to every world
            with ctx.db.session() as db:
                tied = assets_svc.adopt_pack_duplicates(db)
            if tied:
                log.info("portrait folders tied to their world: %s", ", ".join(tied))
        except Exception:
            log.exception("portrait folders could not be tied to their world")


def _sync_lore_packs(ctx: AppContext) -> None:
    packs = ctx.settings.project_root.resolve() / PACKS_DIR
    try:
        moved = _repoint(ctx, packs)
        if moved:
            log.info("lore packs: %d stored location(s) updated after the folder moved", moved)
    except Exception:
        log.exception("lore packs: stored locations could not be updated")
    if not packs.is_dir():
        return
    seen: dict[str, Path] = {}
    for folder in sorted(p for p in packs.iterdir() if p.is_dir()):
        if not pack_manifest.has_manifest(folder):
            continue
        try:
            log.info("lore pack %s: %s", folder.name, _sync_pack(ctx, folder.resolve(), seen))
        except Exception:
            log.exception("lore pack %s could not be loaded", folder.name)


sync_bundled_resources = sync_lore_packs  # name used by older code
