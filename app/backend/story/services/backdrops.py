"""Place backgrounds (v0.6.2): the picture behind the story text changes with the place of the scene.

A pack gives one picture per place in ``<images folder>/places/<place id>.webp`` (png and jpg too); the world creator
writes them there. The scene's place (kept by the app, no model call) is matched to a lore place: the place itself, or
the most precise lore place named in it ("the dormitory of the academy" -> the dormitory, if it has a picture).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

EXTS = (".webp", ".png", ".jpg", ".jpeg")


def images_dir(world: Any) -> Path | None:
    """The pack's images folder (pack.json files.images, else the one folder named images or *_images)."""
    if world is None or not getattr(world, "source_path", None):
        return None
    base = Path(world.source_path)
    if not base.is_dir():
        return None
    try:
        raw = json.loads((base / "pack.json").read_text(encoding="utf-8")) if (base / "pack.json").is_file() else {}
    except (OSError, ValueError):
        raw = {}
    rel = (raw.get("files") or {}).get("images") if isinstance(raw.get("files"), dict) else None
    if rel:
        p = (base / rel).resolve()
        return p if p.is_dir() and base.resolve() in p.parents else None
    hits = sorted(d for d in base.iterdir() if d.is_dir() and (d.name == "images" or d.name.endswith("_images")))
    return hits[0] if len(hits) == 1 else None


def place_files(images: Path | None) -> dict[str, Path]:
    """{place id: picture file}."""
    folder = images / "places" if images else None
    out: dict[str, Path] = {}
    if folder and folder.is_dir():
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in EXTS:
                out.setdefault(p.stem, p)
    return out


def for_story(db: Session, story: Any, branch_id: str | None = None) -> dict[str, Any]:
    """The background of the story's current scene: {"place_id", "name", "world_id"} or {"place_id": None}."""
    from ..models import World
    from . import state_service, story_tree
    from .entities import EntityIndex, build_index

    world = db.get(World, story.world_id) if story.world_id else None
    files = place_files(images_dir(world))
    if not files:
        return {"place_id": None}
    branch = story_tree.get_branch(db, story, branch_id)
    st = state_service.current(db, branch.id)
    state = state_service.normalize(st.state_json if st else {})
    loc = str((state.get("scene") or {}).get("location") or "").strip()
    if not loc:
        return {"place_id": None}
    index = build_index(db, story.world_id, state)
    places = EntityIndex([e for e in index.entities.values() if e.category == "location"])
    found = [places.resolve(loc)] if places.resolve(loc) else []
    # the most precise place first: the longest name ("academy dormitory" before "academy")
    found += sorted(places.find_mentions(loc, ("location",)), key=lambda pid: -len(places.name(pid)))
    for pid in found:
        if pid in files:
            return {"place_id": pid, "name": places.name(pid), "world_id": world.id}
    return {"place_id": None}
