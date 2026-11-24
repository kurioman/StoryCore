"""Edit a lore pack from the Lore page, on the computer or a paired phone (Kurio, 24/11/2026).

* Every field of a record can be changed in place ("Modify"), and a record can be added at the end of a list
  ("Add"): a character starts from the 12-category model (services/lore_templates.py), any other record from the
  fields of the records already in its category.
* A pack is never changed in place the first time: the owner names a new pack ("Lumencia Academy V2"), the whole
  folder is copied under that name (portraits included) and the change goes into the copy. The original stays as it
  was: it is the backup, and the stories played in it keep it. Later changes go straight into the copy, which is
  marked in its pack.json (``"_edited_copy_of": "<original id>"``).
* Changes are written into the pack's own JSON files; the pack is then re-imported (lore and portraits) by the same
  code that loads packs at start-up (bundled._sync_pack), so the app and the files always agree.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LoreEntity, World
from . import lore_import, lore_templates

PACKS_DIR = "Lorepack"
MARKER = "_edited_copy_of"
DEFAULT_FILE = {"character": "characters/characters.json"}
NOT_EDITABLE = {"id", "_index_type"}


class NeedsName(Exception):
    """First change to an original pack: a name for the new pack is needed."""


def _pack_dir(world: World) -> Path:
    p = Path(world.source_path or "")
    if not world.source_path or not (p / "pack.json").is_file():
        raise ValueError("This world has no pack folder with a pack.json: it cannot be changed from here.")
    return p


def _manifest(pdir: Path) -> dict[str, Any]:
    return json.loads((pdir / "pack.json").read_text(encoding="utf-8"))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "record"


def status(db: Session, world: World) -> dict[str, Any]:
    """What the Lore page needs before a change: can this pack be changed, is it already a copy, and where new
    characters can go (the files that already hold some, with their most common type)."""
    try:
        pdir = _pack_dir(world)
    except ValueError as e:
        return {"editable": False, "reason": str(e)}
    manifest = _manifest(pdir)
    types: dict[str, dict[str, int]] = {}
    for e in db.scalars(select(LoreEntity).where(LoreEntity.world_id == world.id, LoreEntity.category == "character")):
        if e.file:
            t = types.setdefault(e.file, {})
            t[e.entity_type or ""] = t.get(e.entity_type or "", 0) + 1
    files = [{"file": f, "type": max(t, key=t.get) if t else ""} for f, t in sorted(types.items())] \
        or [{"file": DEFAULT_FILE["character"], "type": ""}]
    name = manifest.get("name") or world.name
    return {"editable": True, "name": name, "is_copy": bool(manifest.get(MARKER)), "copy_of": manifest.get(MARKER),
            "suggested_name": f"{name} V2", "character_files": files, "models": sorted(lore_templates.MODELS)}


def _set_top(text: str, key: str, value: str) -> str:
    """Change the first top-level ``"key": "..."`` of pack.json, keeping its layout."""
    return re.sub(rf'("{key}"\s*:\s*)"(?:[^"\\]|\\.)*"', lambda m: m.group(1) + json.dumps(value, ensure_ascii=False),
                  text, count=1)


def ensure_copy(world: World, project_root: Path, new_name: str | None) -> Path:
    """The folder to write into: the pack itself when it is already an in-app copy, otherwise a new copy named
    ``new_name`` (NeedsName when none is given)."""
    pdir = _pack_dir(world)
    manifest = _manifest(pdir)
    if manifest.get(MARKER):
        return pdir
    new_name = (new_name or "").strip()
    if not new_name:
        raise NeedsName()
    new_id = slug(new_name)
    packs = project_root / PACKS_DIR
    for other in packs.iterdir() if packs.is_dir() else []:
        if (other / "pack.json").is_file():
            try:
                if _manifest(other).get("id") == new_id:
                    raise ValueError(f"A pack already uses the name \"{new_name}\": choose another one.")
            except (ValueError, json.JSONDecodeError) as e:
                if isinstance(e, json.JSONDecodeError):
                    continue
                raise
    dest = packs / f"{new_id}_lore_pack"
    if dest.exists():
        raise ValueError(f"The folder {dest.name} already exists: choose another name.")
    shutil.copytree(pdir, dest)
    text = (dest / "pack.json").read_text(encoding="utf-8")
    text = _set_top(_set_top(text, "id", new_id), "name", new_name)
    text = text.replace("{", "{\n  " + json.dumps(MARKER) + ": " + json.dumps(manifest.get("id") or "") + ",", 1)
    data = json.loads(text)  # must still be valid, with the new id and name
    if data.get("id") != new_id or data.get("name") != new_name:
        data.update({"id": new_id, "name": new_name})
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    (dest / "pack.json").write_text(text, encoding="utf-8", newline="\n")
    return dest


# --------------------------------------------------------------------------- records in the pack's files
def _find(node: Any, rid: str, parent: list | None = None) -> tuple[dict | None, list | None]:
    """The dict whose "id" is ``rid`` anywhere in a JSON document, and the list holding it (None for the root)."""
    if isinstance(node, dict):
        if node.get("id") == rid:
            return node, parent
        for v in node.values():
            hit = _find(v, rid, None)
            if hit[0] is not None:
                return hit
    elif isinstance(node, list):
        for v in node:
            hit = _find(v, rid, node)
            if hit[0] is not None:
                return hit
    return None, None


def _record_file(db: Session, world: World, category: str, rid: str) -> str:
    e = db.scalar(select(LoreEntity).where(LoreEntity.world_id == world.id, LoreEntity.category == category,
                                          LoreEntity.entity_id == rid))
    if e is None or not e.file:
        raise LookupError("Lore record not found")
    return e.file


def _safe(pdir: Path, rel: str) -> Path:
    p = (pdir / rel).resolve()
    if p.suffix.lower() != ".json" or pdir.resolve() not in p.parents:
        raise ValueError(f"Not a JSON file of this pack: {rel}")
    return p


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _save(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def raw(db: Session, world: World, category: str, rid: str) -> dict[str, Any]:
    """The record as written in the pack, secrets ("hidden") included: what the editor shows and changes."""
    rel = _record_file(db, world, category, rid)
    rec, _ = _find(_load(_safe(_pack_dir(world), rel)), rid)
    if rec is None:
        raise LookupError("Lore record not found in its file")
    return {"record": rec, "file": rel}


def _index_entry(pdir: Path, rid: str, fn) -> None:
    index = pdir / "characters" / "index.json"
    if index.is_file():
        idx = _load(index)
        if isinstance(idx.get("entities"), list):
            fn(idx["entities"])
            _save(index, idx)


def update(db: Session, world: World, project_root: Path, category: str, rid: str, field: str, value: Any,
           new_name: str | None = None) -> Path:
    """Set one top-level field of a record; returns the pack folder written (the new copy the first time)."""
    if not field or field in NOT_EDITABLE:
        raise ValueError(f"The field \"{field}\" cannot be changed here.")
    if field == "name" and not str(value or "").strip():
        raise ValueError("A name is needed.")
    rel = _record_file(db, world, category, rid)
    pdir = ensure_copy(world, project_root, new_name)
    path = _safe(pdir, rel)
    data = _load(path)
    rec, _ = _find(data, rid)
    if rec is None:
        raise LookupError("Lore record not found in its file")
    if field == "name" and "name" not in rec and "term" in rec:
        field = "term"  # glossary entries are named by their term
    rec[field] = value
    _save(path, data)
    if field == "name" and category == "character":
        def rename(ents):
            for e in ents:
                if e.get("id") == rid:
                    e["name"] = value
        _index_entry(pdir, rid, rename)
    return pdir


def _emptied(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _emptied(x) for k, x in v.items() if k not in ("source_ids", "confidence", "canon_status")}
    if isinstance(v, list):
        return []
    if isinstance(v, str):
        return ""
    return None


def create(db: Session, world: World, project_root: Path, category: str, name: str, file: str = "",
           record_type: str = "", new_name: str | None = None) -> tuple[Path, str]:
    """Add an empty record at the end of its category; returns (pack folder written, new record id)."""
    name = name.strip()
    if not name:
        raise ValueError("A name is needed.")
    taken = {e.entity_id for e in db.scalars(select(LoreEntity).where(LoreEntity.world_id == world.id))}
    rid, n = slug(name), 2
    while rid in taken:
        rid, n = f"{slug(name)}_{n}", n + 1

    if category in lore_templates.MODELS:
        rel = (file or DEFAULT_FILE[category]).replace("\\", "/")
        pdir = ensure_copy(world, project_root, new_name)
        path = _safe(pdir, rel)
        data = _load(path) if path.is_file() else {"characters": []}
        key = next((k for k, v in data.items() if isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0]),
                   None) or next((k for k, v in data.items() if isinstance(v, list)), "characters")
        data.setdefault(key, []).append(
            lore_templates.template(category, rid, name, {"type": record_type} if record_type else None))
        _save(path, data)
        if category == "character":
            def add(ents):
                group = next((e.get("group") for e in ents if e.get("file") == rel and e.get("group")), "")
                ents.append({k: v for k, v in {"id": rid, "name": name, "gender": "", "type": record_type,
                                              "group": group, "file": rel}.items() if v != "" or k == "gender"})
            _index_entry(pdir, rid, add)
        return pdir, rid

    # no model: the same fields as a record already in this category, emptied
    sibling = db.scalar(select(LoreEntity).where(LoreEntity.world_id == world.id, LoreEntity.category == category,
                                                 LoreEntity.file.is_not(None)).order_by(LoreEntity.name))
    if sibling is None:
        raise ValueError(f"No \"{category}\" record yet in this pack to take its fields from.")
    rel = sibling.file
    pdir = ensure_copy(world, project_root, new_name)
    path = _safe(pdir, rel)
    data = _load(path)
    rec, parent = _find(data, sibling.entity_id)
    if rec is None or parent is None:
        raise ValueError(f"\"{category}\" records are not kept in a list in {rel}: add this one by hand.")
    new = _emptied(copy.deepcopy(rec))
    new["id"] = rid
    if "name" in rec or not ({"term", "title"} & set(rec)):
        new["name"] = name
    if "term" in rec:
        new["term"] = name
    if "title" in rec and "name" not in rec:
        new["title"] = name
    parent.append({"id": rid, **{k: v for k, v in new.items() if k != "id"}})
    _save(path, data)
    return pdir, rid
