"""World creator (Phase 8): create and edit lore packs from inside the app.

A world made in the app is a real lore pack in ``<project>/Lorepack/<id>_lore_pack`` with the usual files, so it loads,
plays and is shared (one .zip) like any other pack. This module reads such a pack as one editable document and writes it
back in a fixed layout:

    pack.json                       identity, library card and every engine section (LOREPACK_FORMAT.md)
    lore/premise.md                 the world's presentation
    ai/narrative_system_prompt.md   the narrator's rules for this world
    characters/characters.json      {"characters": [...]}
    lore/locations.json             {"locations": [...]}
    factions/factions.json          {"factions": [...]}     (groups: factions, guilds, families, nations...)
    story/glossary.json             {"terms": [{"id", "term", "definition"}]}
    images/                         cover and portraits (<character id>_<1..6>.webp)

Only packs marked as made by the creator (``"_creator"`` in pack.json) can be edited; any other pack (the bundled ones,
or a pack written by hand) is first copied: its records are gathered with the importer's own rules and written in the
layout above, and the files the creator does not manage are kept unchanged ("other lore files").
"""
from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssetRoot, LoreEntity, Story, World
from . import lore_import, pack_manifest

MARKER = "_creator"
CREATOR_VERSION = 1
PACKS_DIR = "Lorepack"
IMAGES = "images"
PREMISE = "lore/premise.md"
NARRATOR = "ai/narrative_system_prompt.md"
LISTS = {  # document key -> (file, key inside the file)
    "characters": ("characters/characters.json", "characters"),
    "locations": ("lore/locations.json", "locations"),
    "groups": ("factions/factions.json", "factions"),
    "glossary": ("story/glossary.json", "terms"),
}
# importer categories gathered into each list when a pack is copied
CATEGORY_LIST = {"character": "characters", "location": "locations", "region": "locations", "faction": "groups",
                 "polity": "groups", "organization": "groups", "department": "groups", "glossary": "glossary"}
SECTIONS = ("stats", "starters", "posts", "closed_groups", "facts", "gatherings", "places", "never_random", "choices",
            "events")  # v0.6: planned events and the player choices they depend on
EXPRESSIONS = range(1, 7)
IMAGE_MAX_SIDE = 1024
COVER_MAX_SIDE = 1280
BACKDROP_MAX_SIDE = 1920
UPLOAD_MAX_BYTES = 25 * 1024 * 1024
RECORD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,119}$")


class EditorError(ValueError):
    """A problem the player can fix (shown as is)."""


# --------------------------------------------------------------------------- helpers
def packs_dir(project_root: Path) -> Path:
    return project_root.resolve() / PACKS_DIR


def slugify(text: str, fallback: str = "world") -> str:
    import unicodedata

    t = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")[:60]  # same rule as makeId() in the creator page
    return s or fallback


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((text or "").rstrip() + "\n" if (text or "").strip() else "", encoding="utf-8")


def _one_text(v: Any, lang: str = "fr") -> Any:
    """A text given per language ({"en": ..., "fr": ...}) becomes one text (the creator edits one language)."""
    if isinstance(v, dict):
        return v.get(lang) or v.get("en") or next(iter(v.values()), "")
    return v


def manifests(project_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    root = packs_dir(project_root)
    out = []
    if root.is_dir():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            raw = _read_json(d / pack_manifest.MANIFEST)
            if isinstance(raw, dict) and isinstance(raw.get("id"), str):
                out.append((d, raw))
    return out


def find(project_root: Path, pid: str) -> tuple[Path, dict[str, Any]]:
    for d, raw in manifests(project_root):
        if raw["id"] == pid:
            return d, raw
    raise LookupError("World not found")


def editable(raw: dict[str, Any]) -> bool:
    return isinstance(raw.get(MARKER), dict)


def _images_dir(folder: Path, raw: dict[str, Any]) -> Path:
    rel = ((raw.get("files") or {}).get("images") or IMAGES) if isinstance(raw.get("files"), dict) else IMAGES
    return folder / rel


def _unique_id(project_root: Path, db: Session, base: str) -> str:
    taken = {raw["id"] for _d, raw in manifests(project_root)} | set(db.scalars(select(World.slug)))
    pid, n = base, 2
    while pid in taken or (packs_dir(project_root) / f"{pid}_lore_pack").exists():
        pid, n = f"{base}_{n}", n + 1
    return pid


# --------------------------------------------------------------------------- listing
def list_packs(project_root: Path, db: Session) -> list[dict[str, Any]]:
    worlds = {w.slug: w for w in db.scalars(select(World))}
    out = []
    for d, raw in manifests(project_root):
        w = worlds.get(raw["id"])
        stories = db.scalar(select(Story.id).where(Story.world_id == w.id).limit(1)) if w else None
        out.append({"id": raw["id"], "name": _one_text(raw.get("name")) or raw["id"], "folder": d.name,
                    "editable": editable(raw), "world_id": w.id if w else None, "has_stories": bool(stories),
                    "summary": _one_text(raw.get("summary")) or raw.get("description") or "",
                    "cover": bool(raw.get("cover")), "updated": (raw.get(MARKER) or {}).get("updated", "")})
    return out


# --------------------------------------------------------------------------- reading
def read(project_root: Path, pid: str) -> dict[str, Any]:
    folder, raw = find(project_root, pid)
    if not editable(raw):
        raise EditorError("This world was not made with the world creator: make a copy to edit it.")
    doc: dict[str, Any] = {
        "id": raw["id"], "name": raw.get("name", ""), "folder": folder.name,
        "description": raw.get("description", ""), "summary": _one_text(raw.get("summary")) or "",
        "tags": _one_text(raw.get("tags")) or [], "canon_note": raw.get("canon_note", ""),
        "modules": raw.get("modules") or [], "codex": raw.get("codex", True) is not False,
        "music": raw.get("music"), "calendar": raw.get("calendar") or {},
        "premise": (folder / PREMISE).read_text(encoding="utf-8") if (folder / PREMISE).is_file() else "",
        "narrator": (folder / NARRATOR).read_text(encoding="utf-8") if (folder / NARRATOR).is_file() else "",
    }
    for sec in SECTIONS:
        doc[sec] = raw.get(sec) or []
    for key, (rel, inner) in LISTS.items():
        data = _read_json(folder / rel, {})
        doc[key] = [r for r in (data.get(inner) if isinstance(data, dict) else data) or [] if isinstance(r, dict)]
    images = _images_dir(folder, raw)
    doc["cover"] = raw.get("cover") or ""
    doc["portraits"] = portraits(images)
    doc["portrait_files"] = portrait_files(folder, images)
    from .backdrops import place_files
    doc["place_files"] = {k: v.relative_to(folder).as_posix() for k, v in place_files(images).items()}
    doc["event_files"] = {k: v.relative_to(folder).as_posix() for k, v in place_files(images, "events").items()}
    managed = {pack_manifest.MANIFEST, PREMISE, NARRATOR, *(rel for rel, _ in LISTS.values())}
    doc["other_files"] = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")
                                if p.is_file() and p.suffix.lower() in (".json", ".md")
                                and p.relative_to(folder).as_posix() not in managed and images not in p.parents)
    doc["updated"] = raw[MARKER].get("updated", "")
    return doc


IMAGE_EXTS = (".webp", ".png", ".jpg", ".jpeg", ".gif")


def _portrait_slots(images: Path) -> list[tuple[str, int, Path]]:
    """(character, expression, file) for every portrait, named as the importer reads them: ``lily_1.webp``,
    ``lily_01.webp`` or ``lily/1.webp``."""
    from .assets import parse_name

    out = []
    if images.is_dir():
        for p in sorted(images.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.parent.name.casefold() not in ("places", "events"):
                slug, num = parse_name(p.relative_to(images).as_posix())
                if slug and num in EXPRESSIONS:
                    out.append((slug, num, p))
    return out


def portraits(images: Path) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for slug, num, _p in _portrait_slots(images):
        out.setdefault(slug, []).append(num)
    return {k: sorted(set(v)) for k, v in out.items()}


def portrait_files(folder: Path, images: Path) -> dict[str, dict[int, str]]:
    """{character id: {expression: path inside the pack}} (for the creator's picture slots)."""
    out: dict[str, dict[int, str]] = {}
    for slug, num, p in _portrait_slots(images):
        out.setdefault(slug, {})[num] = p.relative_to(folder).as_posix()
    return out


# --------------------------------------------------------------------------- writing
def _clean_list(items: Any, label: str, name_key: str = "name") -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise EditorError(f"{label}: a list is expected.")
    out, seen = [], set()
    for it in items:
        if not isinstance(it, dict):
            continue
        rid, name = str(it.get("id") or "").strip(), str(it.get(name_key) or "").strip()
        if not name:
            continue  # an empty card (nothing typed yet) is not saved
        if not RECORD_ID_RE.match(rid):
            rid = slugify(name, "item")
        base, n = rid, 2
        while rid in seen:
            rid, n = f"{base}_{n}", n + 1
        seen.add(rid)
        rec = {"id": rid, **{k: v for k, v in it.items() if k != "id" and v not in (None, "", [], {})}}
        out.append(rec)
    return out


def write(project_root: Path, pid: str, doc: dict[str, Any], now: str) -> dict[str, Any]:
    """Save the keys present in ``doc`` (any subset of what ``read`` returns). Returns the saved document."""
    folder, raw = find(project_root, pid)
    if not editable(raw):
        raise EditorError("This world was not made with the world creator: make a copy to edit it.")
    new = dict(raw)
    if "name" in doc:
        name = str(doc["name"] or "").strip()
        if not name:
            raise EditorError("The world needs a name.")
        new["name"] = name[:200]
    for k in ("description", "summary", "canon_note"):
        if k in doc:
            new[k] = str(doc[k] or "").strip()
    if "summary" in doc and len(new["summary"]) > pack_manifest.SUMMARY_MAX:
        raise EditorError(f"The library summary is too long (at most {pack_manifest.SUMMARY_MAX} characters).")
    if "tags" in doc:
        new["tags"] = [str(t).strip() for t in doc["tags"] or [] if str(t).strip()][:8]
    if "modules" in doc:
        new["modules"] = [str(m).strip() for m in doc["modules"] or [] if str(m).strip()]
    if "codex" in doc:
        new["codex"] = bool(doc["codex"])
    if "music" in doc:
        new["music"] = doc["music"] if doc["music"] is False or isinstance(doc["music"], dict) else None
    if "calendar" in doc:
        new["calendar"] = {k: v for k, v in (doc["calendar"] or {}).items() if v} or None
    for sec in SECTIONS:
        if sec in doc:
            v = doc[sec]
            if not isinstance(v, list):
                raise EditorError(f"{sec}: a list is expected.")
            new[sec] = v
    for key, (rel, inner) in LISTS.items():
        if key in doc:
            _write_json(folder / rel, {inner: _clean_list(doc[key], key, "term" if key == "glossary" else "name")})
    if "premise" in doc:
        _write_text(folder / PREMISE, doc["premise"])
    if "narrator" in doc:
        _write_text(folder / NARRATOR, doc["narrator"])
    # empty sections are left out of pack.json (a missing section = feature off)
    new = {k: v for k, v in new.items() if v not in (None, "", [], {}) or k in ("codex",)}
    new.update({"format_version": 2, "id": raw["id"]})
    new["files"] = {"system_prompt": NARRATOR, "premise": PREMISE, "images": _images_rel(raw)}
    new[MARKER] = {**raw[MARKER], "version": CREATOR_VERSION, "updated": now}
    _write_json(folder / pack_manifest.MANIFEST, _ordered(new))
    return read(project_root, pid)


def _images_rel(raw: dict[str, Any]) -> str:
    files = raw.get("files") if isinstance(raw.get("files"), dict) else {}
    return files.get("images") or IMAGES


def _ordered(m: dict[str, Any]) -> dict[str, Any]:
    order = ["format_version", "id", "name", "description", "summary", "tags", "cover", "canon_note", "modules", "codex",
             "music", "files", "stats", "starters", "posts", "closed_groups", "facts", "gatherings", "places", "calendar",
             "never_random", "choices", "events"]
    return {**{k: m[k] for k in order if k in m}, **{k: v for k, v in m.items() if k not in order}}


# --------------------------------------------------------------------------- creating / copying
def _starter_prompt(name: str) -> str:
    return (f"# Narrator rules: {name}\n\n"
            "- Write in the second person, present tense. Never decide the protagonist's words, feelings or actions.\n"
            "- Keep characters, places and established facts consistent with the lore.\n"
            "- When a detail is unknown, invent it in the spirit of the world and keep it consistent afterwards.\n"
            "- End each reply on a clear opening for the player.\n")


def create(project_root: Path, db: Session, name: str, now: str) -> str:
    name = (name or "").strip()
    if not name:
        raise EditorError("The world needs a name.")
    pid = _unique_id(project_root, db, slugify(name))
    folder = packs_dir(project_root) / f"{pid}_lore_pack"
    folder.mkdir(parents=True)
    (folder / IMAGES).mkdir()
    _write_text(folder / PREMISE, f"# {name}\n")
    _write_text(folder / NARRATOR, _starter_prompt(name))
    for rel, inner in LISTS.values():
        _write_json(folder / rel, {inner: []})
    _write_json(folder / pack_manifest.MANIFEST, _ordered({
        "format_version": 2, "id": pid, "name": name[:200], "codex": True,
        "files": {"system_prompt": NARRATOR, "premise": PREMISE, "images": IMAGES},
        "stats": [{"label": "HP", "type": "current_max", "value": 100, "max": 100}],
        MARKER: {"version": CREATOR_VERSION, "created": now, "updated": now}}))
    return pid


def _gather(folder: Path) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Records of a pack sorted into the creator's lists, with their narrator-only notes, using the importer itself on a
    throw-away database (exactly what the app reads). Also returns the files whose records were all gathered."""
    from ..db import Database

    lists: dict[str, list[dict[str, Any]]] = {k: [] for k in LISTS}
    files: set[str] = set()
    with tempfile.TemporaryDirectory() as td:
        tdb = Database(Path(td) / "copy.db")
        try:
            tdb.migrate()
            with tdb.session() as s:
                lore_import.import_pack(s, folder)
                world = s.scalar(select(World))
                hidden = (world.data_json or {}).get("hidden") or {}
                for r in s.scalars(select(LoreEntity).where(LoreEntity.world_id == world.id)):
                    key = CATEGORY_LIST.get(r.category)
                    if not key:
                        continue
                    files.add(r.file)
                    rec = dict(r.data_json or {})
                    notes = hidden.get(f"{r.category}:{r.entity_id}")
                    if notes:
                        rec["hidden"] = notes
                    if key == "glossary":
                        rec = {"id": r.entity_id, "term": rec.get("term") or r.name,
                               "definition": rec.get("definition") or lore_import.record_text(
                                   {k: v for k, v in rec.items() if k not in ("id", "name", "term")})}
                    elif key == "groups" and r.category != "faction":
                        rec.setdefault("type", r.category.replace("_", " ").title())
                    elif key == "locations" and r.category == "region":
                        rec.setdefault("type", "Region")
                    lists[key].append(rec)
        finally:
            tdb.engine.dispose()  # Windows cannot delete the temporary database while it is open
    return {k: _merge_same_ids(v) for k, v in lists.items()}, sorted(files)


def _merge_same_ids(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One card per id: the importer can read the same id twice in different categories (a faction and a polity)."""
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        rid = str(r.get("id") or "")
        if rid in out:
            for k, v in r.items():
                out[rid].setdefault(k, v)
        else:
            out[rid or f"_{len(out)}"] = dict(r)
    return list(out.values())


def _list_category(key: str, items: list[Any], stem: str) -> str | None:
    """The importer's category for a list found in a lore file (same rules as lore_import.import_pack)."""
    if key == "relationships" or key == "events":
        return None
    if key == "terms":
        return "glossary" if items and isinstance(items[0], dict) and "definition" in items[0] else None
    return lore_import.KEY_CATEGORY.get(key) or lore_import.STEM_CATEGORY.get(stem)


def _strip_gathered(path: Path) -> None:
    """Remove from a copied lore file what was gathered into the creator's lists (no record is read twice). The file
    is deleted when nothing else is left in it."""
    data = _read_json(path)
    if not isinstance(data, dict):
        return
    keep, removed = {}, False
    for k, v in data.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and CATEGORY_LIST.get(_list_category(k, v, path.stem) or ""):
            removed = True
            continue
        keep[k] = v
    if not removed:
        # an object-shaped file read whole by its name (glossary.json {"magic": {...}}): all of it was gathered
        if CATEGORY_LIST.get(lore_import.STEM_CATEGORY.get(path.stem) or "") and not any(
                isinstance(v, list) and v and isinstance(v[0], dict) for v in data.values()):
            path.unlink()
        return
    if any(isinstance(v, (list, dict)) and v for v in keep.values()):
        _write_json(path, keep)
    else:
        path.unlink()


def copy(project_root: Path, db: Session, pid: str, name: str, now: str) -> str:
    """Copy any pack into a new editable world (the original is never changed)."""
    src, raw = find(project_root, pid)
    manifest, _rep = pack_manifest.load(src)
    if manifest is None:
        raise EditorError("This pack cannot be read (its pack.json is broken).")
    name = (name or "").strip() or f"{_one_text(raw.get('name'))} (copy)"
    new_id = _unique_id(project_root, db, slugify(name))
    dest = packs_dir(project_root) / f"{new_id}_lore_pack"
    shutil.copytree(src, dest)
    try:
        lists, gathered = _gather(dest)
        files = manifest["files"]
        # the manifest's own files (sections in pack/*.json) are inlined into pack.json below
        for rel in manifest.get("sources", [])[1:]:
            (dest / rel).unlink(missing_ok=True)
        for rel in gathered:
            if (dest / rel).is_file():
                _strip_gathered(dest / rel)
        (dest / "characters" / "index.json").unlink(missing_ok=True)
        for rel_key, target in (("premise", PREMISE), ("system_prompt", NARRATOR)):
            rel = files.get(rel_key)
            if rel and rel != target and (dest / rel).is_file():
                _write_text(dest / target, (dest / rel).read_text(encoding="utf-8"))
                (dest / rel).unlink()
        for key, (rel, inner) in LISTS.items():
            _write_json(dest / rel, {inner: lists[key]})
        images = files.get("images") or IMAGES
        if not (dest / images).is_dir():
            (dest / IMAGES).mkdir(exist_ok=True)
            images = IMAGES
        lib = manifest.get("library") or {}
        new = {"format_version": 2, "id": new_id, "name": name[:200], "description": manifest.get("description", ""),
               "summary": _one_text(raw.get("summary")) or "", "tags": _one_text(raw.get("tags")) or [],
               "cover": raw.get("cover") if lib.get("cover") else None, "canon_note": manifest.get("canon_note", ""),
               "modules": manifest.get("modules") or [], "codex": manifest.get("codex", True),
               "music": manifest.get("music"),
               "files": {"system_prompt": NARRATOR, "premise": PREMISE, "images": images},
               MARKER: {"version": CREATOR_VERSION, "created": now, "updated": now, "copied_from": pid}}
        for sec in (*SECTIONS, "calendar"):
            if manifest.get(sec):
                new[sec] = manifest[sec]
        for st in new.get("starters") or []:  # one language in the creator
            for k in ("name", "purpose"):
                if k in st:
                    st[k] = _one_text(st[k])
        for ev in new.get("events") or []:
            if "title" in ev:
                ev["title"] = _one_text(ev["title"])
        for c in new.get("choices") or []:
            c["name"] = _one_text(c.get("name"))
            for o in c.get("options") or []:
                o["name"] = _one_text(o.get("name"))
        new = {k: v for k, v in new.items() if v not in (None, "", [], {}) or k == "codex"}
        _write_json(dest / pack_manifest.MANIFEST, _ordered(new))
        _remove_empty_dirs(dest)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return new_id


def _remove_empty_dirs(folder: Path) -> None:
    for d in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if d.name != IMAGES and not any(d.iterdir()):
            d.rmdir()


# --------------------------------------------------------------------------- images
def _to_webp(data: bytes, max_side: int) -> bytes:
    from PIL import Image, ImageOps

    if len(data) > UPLOAD_MAX_BYTES:
        raise EditorError("This image is too large (25 MB at most).")
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
    except Exception:
        raise EditorError("This file is not an image the app can read (use PNG, JPG or WebP).")
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "WEBP", quality=86, method=4)
    return out.getvalue()


def _editable_folder(project_root: Path, pid: str) -> tuple[Path, dict[str, Any]]:
    folder, raw = find(project_root, pid)
    if not editable(raw):
        raise EditorError("This world was not made with the world creator: make a copy to edit it.")
    return folder, raw


def set_portrait(project_root: Path, pid: str, char_id: str, n: int, data: bytes) -> None:
    if not RECORD_ID_RE.match(char_id) or n not in EXPRESSIONS:
        raise EditorError("Unknown character or expression.")
    folder, raw = _editable_folder(project_root, pid)
    images = _images_dir(folder, raw)
    images.mkdir(parents=True, exist_ok=True)
    webp = _to_webp(data, IMAGE_MAX_SIDE)
    for slug, num, old in _portrait_slots(images):
        if slug == char_id and num == n:
            old.unlink()
    (images / f"{char_id}_{n}.webp").write_bytes(webp)


def remove_portraits(project_root: Path, pid: str, char_id: str, n: int | None = None) -> None:
    if not RECORD_ID_RE.match(char_id):
        raise EditorError("Unknown character.")
    folder, raw = _editable_folder(project_root, pid)
    images = _images_dir(folder, raw)
    for slug, num, p in _portrait_slots(images):
        if slug == char_id and (n is None or num == n):
            p.unlink()


def set_cover(project_root: Path, pid: str, data: bytes | None, now: str) -> None:
    folder, raw = _editable_folder(project_root, pid)
    for old in folder.glob("cover.*"):
        old.unlink()
    raw = dict(raw)
    if data is None:
        raw.pop("cover", None)
    else:
        (folder / "cover.webp").write_bytes(_to_webp(data, COVER_MAX_SIDE))
        raw["cover"] = "cover.webp"
    raw[MARKER] = {**raw[MARKER], "updated": now}
    _write_json(folder / pack_manifest.MANIFEST, _ordered(raw))


def set_place_image(project_root: Path, pid: str, place_id: str, data: bytes | None, kind: str = "places") -> None:
    """v0.6.2: the background picture of a place (images/places/<place id>.webp) or the gallery picture of a planned
    event (images/events/<event id>.webp); ``None`` removes it."""
    if not RECORD_ID_RE.match(place_id) or kind not in ("places", "events"):
        raise EditorError("Unknown place or event.")
    folder, raw = _editable_folder(project_root, pid)
    places = _images_dir(folder, raw) / kind
    for old in places.glob(f"{place_id}.*") if places.is_dir() else []:
        old.unlink()
    if data is not None:
        places.mkdir(parents=True, exist_ok=True)
        (places / f"{place_id}.webp").write_bytes(_to_webp(data, BACKDROP_MAX_SIDE))


def image_path(project_root: Path, pid: str, rel: str) -> Path:
    folder, raw = find(project_root, pid)
    p = (folder / rel).resolve()
    images = _images_dir(folder, raw).resolve()
    if not p.is_file() or not (images in p.parents or p.parent == folder.resolve() and p.stem == "cover"):
        raise LookupError("Image not found")
    return p


# --------------------------------------------------------------------------- deleting, sharing
def delete(project_root: Path, db: Session, pid: str) -> None:
    folder, raw = _editable_folder(project_root, pid)
    world = db.scalar(select(World).where(World.slug == pid))
    if world is not None:
        if db.scalar(select(Story.id).where(Story.world_id == world.id).limit(1)):
            raise EditorError("Stories are played in this world: delete them first.")
        images = str(_images_dir(folder, raw).resolve())
        for root in db.scalars(select(AssetRoot).where(AssetRoot.world_id == world.id)):
            db.delete(root)
        for root in db.scalars(select(AssetRoot).where(AssetRoot.path == images)):
            db.delete(root)
        db.delete(world)
        db.flush()
    shutil.rmtree(folder)


def export_zip(project_root: Path, pid: str) -> tuple[bytes, str]:
    folder, raw = find(project_root, pid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                zf.write(p, f"{folder.name}/{p.relative_to(folder).as_posix()}")
    return buf.getvalue(), f"{slugify(_one_text(raw.get('name')) or pid)}.zip"


def import_zip(project_root: Path, db: Session, data: bytes, filename: str) -> str:
    """A shared world (.zip) becomes a pack folder in Lorepack. A world whose id is already used gets a new id (both
    are kept). Returns the id."""
    with tempfile.TemporaryDirectory() as td:
        zp = Path(td) / "pack.zip"
        zp.write_bytes(data)
        try:
            pack = lore_import.extract_zip(zp, Path(td) / "x")
        except zipfile.BadZipFile:
            raise EditorError("This file is not a valid .zip archive.")
        raw = _read_json(pack / pack_manifest.MANIFEST)
        if not isinstance(raw, dict):
            raise EditorError("This archive does not contain a world (no pack.json found).")
        manifest, rep = pack_manifest.load(pack)
        if manifest is None:
            raise EditorError("This world cannot be read: " + "; ".join(rep["errors"]))
        pid = manifest["id"]
        if pid in {r["id"] for _d, r in manifests(project_root)} or db.scalar(select(World.id).where(World.slug == pid)):
            pid = _unique_id(project_root, db, pid)
            raw["id"] = pid
            _write_json(pack / pack_manifest.MANIFEST, raw)
        dest = packs_dir(project_root) / f"{pid}_lore_pack"
        if dest.exists():
            dest = packs_dir(project_root) / f"{_unique_id(project_root, db, pid)}_lore_pack"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pack, dest)
    return pid
