"""Lore pack discovery, validation and import.

Baseline lore is read-only inside the app: it is stored as a versioned snapshot (``import_version``) and
re-importing never touches local canon. Malformed files are reported and skipped, never "fixed" silently.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import ImportRun, LoreChunk, LoreDocument, LoreEntity, Story, World, now_iso
from . import pack_manifest

KEY_CATEGORY = {
    "characters": "character", "members": "character", "deities": "character",
    "factions": "faction", "polities": "polity", "locations": "location",
    "power_systems": "power_system", "hooks": "plot_hook", "scenarios": "scenario",
    "sources": "source", "departments": "department", "organizations": "organization",
}
FILE_RECORD_CATEGORY = {"academy": "academy", "world": "world"}
# Other common names for the same lists (packs written in another style than the reference pack).
KEY_CATEGORY.update({"starting_points": "scenario", "starting_scenarios": "scenario", "regions": "location",
                     "places": "location", "cities": "location", "terms": "glossary"})
# When a list's key is not recognised, the file's name decides (factions.json: "empires", "nations" -> factions).
STEM_CATEGORY = {**KEY_CATEGORY, "glossary": "glossary", "starting_scenarios": "scenario", "world": "world",
                 "antagonists": "character", "npcs": "character"}


NOT_LORE_DIRS = ("ai/", "scenarios/")  # Markdown there is written for the AI or the openings, not about the world
NOT_LORE_CATEGORIES = {"scenario", "source"}
HIDDEN_KEY = "hidden"  # narrator-only notes: never shown to the player (see LOREPACK_FORMAT.md)
# Kurio (27/11): an author writes "none" (or "null") to mark a section as deliberately empty; it is never sent to the
# narrator nor stored as a secret
EMPTY_MARKS = {"none", "null", "n/a"}


def is_empty_mark(v: Any) -> bool:
    """Whether ``v`` is a deliberate "nothing here" mark: "none", ["none"], "null"..."""
    if isinstance(v, str):
        return v.strip().lower() in EMPTY_MARKS
    if isinstance(v, list):
        return bool(v) and all(is_empty_mark(i) for i in v)
    return False


def strip_hidden(obj: Any, notes: list[str] | None = None, _depth: int = 0) -> tuple[Any, list[str]]:
    """``obj`` without any ``"hidden"`` field (at any depth), and the hidden notes found. A record's own notes are kept
    as written; notes of a nested entry are prefixed with its name (e.g. "[4th Legion (Unknown)] ...")."""
    notes = [] if notes is None else notes
    if isinstance(obj, dict):
        h = obj.get(HIDDEN_KEY)
        if h:
            name = str(obj.get("name") or obj.get("id") or "")
            for n in (h if isinstance(h, list) else [h]):
                if is_empty_mark(n):
                    continue
                from .secret_knowledge import note_from_object  # v0.7.7: {"text": ..., "known_by": [...]}
                text = n if isinstance(n, str) else (note_from_object(n) or json.dumps(n, ensure_ascii=False))
                notes.append(f"[{name}] {text}" if _depth and name else text)
        return {k: strip_hidden(v, notes, _depth + 1)[0] for k, v in obj.items() if k != HIDDEN_KEY}, notes
    if isinstance(obj, list):
        return [strip_hidden(v, notes, _depth + 1)[0] for v in obj], notes
    return obj, notes


def _has_hidden(obj: Any) -> bool:
    if isinstance(obj, dict):
        return HIDDEN_KEY in obj or any(_has_hidden(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_hidden(v) for v in obj)
    return False


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:80]
REF_FIELDS_SINGLE = ("location_id", "parent_location_id", "polity_id", "headquarters_location_id", "department_id",
                     "deity_id", "capital_location_id", "target_id", "from", "to", "faction_id")
REF_FIELDS_LIST = ("faction_ids", "involved_ids", "key_members", "leaders_or_members", "rivals", "worshipped_by", "members")
# v0.6 (test report "30 tours", B15): build and scratch folders (_work\release\stage held a copy of the packs) and the
# developer folder are never offered as lore packs
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "data", "app", "_work", "_release", "DEVONLY"}


# --------------------------------------------------------------------------- discovery
def looks_like_pack(p: Path) -> bool:
    if pack_manifest.has_manifest(p):
        return True
    return (p / "characters" / "index.json").is_file() or ((p / "README.md").is_file() and any(p.glob("*/*.json")))


def discover(project_root: Path, max_depth: int = 4) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(d: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(d.iterdir())
        except OSError:
            return
        for e in entries:
            if e.name in SKIP_DIRS or e.name.startswith("."):
                continue
            if e.is_dir():
                if looks_like_pack(e):
                    found.append({"kind": "folder", "path": str(e), "name": e.name})
                else:
                    walk(e, depth + 1)
            elif e.suffix.lower() == ".zip" and "lore" in e.name.lower():
                found.append({"kind": "zip", "path": str(e), "name": e.name})

    walk(project_root, 0)
    return found


def extract_zip(zip_path: Path, dest_root: Path) -> Path:
    dest = dest_root / re.sub(r"[^A-Za-z0-9_\-]", "_", zip_path.stem)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise ValueError(f"Unsafe path in archive: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
    # the pack may be nested one level down
    if looks_like_pack(dest):
        return dest
    for sub in dest.rglob("*"):
        if sub.is_dir() and looks_like_pack(sub):
            return sub
    return dest


# --------------------------------------------------------------------------- rendering
INLINE_MAX = 160  # v0.6: a small block of plain values is written on one line ("appearance: hair: blue; eyes: gold")


def _inline(d: dict[str, Any]) -> str | None:
    items = [(k, x) for k, x in d.items() if x not in (None, "", [], {}) and k not in ("source_ids", "schema_version")]
    if not items or any(isinstance(x, (dict, list)) for _k, x in items):
        return None
    text = "; ".join(f"{k}: {x}" for k, x in items)
    return text if len(text) <= INLINE_MAX else None


def render_value(v: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if isinstance(v, dict):
        lines = []
        for k, x in v.items():
            if k in ("source_ids", "schema_version") or is_empty_mark(x):
                continue
            if isinstance(x, dict) and x and _inline(x):
                lines.append(f"{pad}{k}: {_inline(x)}")
            elif isinstance(x, (dict, list)) and x:
                sub = render_value(x, indent + 1)
                if isinstance(x, list) and all(not isinstance(i, (dict, list)) for i in x):
                    lines.append(f"{pad}{k}: " + "; ".join(str(i) for i in x))
                else:
                    lines.append(f"{pad}{k}:")
                    lines.extend(sub)
            elif x not in (None, "", [], {}):
                lines.append(f"{pad}{k}: {x}")
        return lines
    if isinstance(v, list):
        lines = []
        for i in v:
            if isinstance(i, dict) and _inline(i):
                lines.append(f"{pad}- {_inline(i)}")
            elif isinstance(i, dict):
                sub = render_value(i, indent)
                if sub:
                    lines.append(f"{pad}- " + sub[0].strip())
                    lines.extend(sub[1:])
            else:
                lines.append(f"{pad}- {i}")
        return lines
    return [f"{pad}{v}"]


# v0.6 (phase 9): top-level keys the narrator does not need in a lore record: the chunk title already gives the name,
# the id and the import bookkeeping are noise (fewer tokens for the same information)
RECORD_SKIP = {"id", "name", "confidence", "canon_status", "_index_type", "source_ids", "schema_version"}
# Kurio (24/11): a character's record says it all in words ("role": "1st-year Knight student; ..."); the app's own
# fields (department, year, type) stay in the data for rosters and encounters but are not sent to the narrator
CHARACTER_SKIP = {"department_id", "year", "type", "group", "file"}
SURE = {None, "", "high", "canon", "confirmed"}


def record_text(rec: dict[str, Any], category: str = "") -> str:
    """A lore record as the narrator reads it. Its reliability is only stated when it is not certain."""
    head = []
    if rec.get("confidence") not in SURE:
        status = f" | status: {rec['canon_status']}" if rec.get("canon_status") else ""
        head.append(f"[confidence: {rec.get('confidence')}{status}]")
    skip = RECORD_SKIP | (CHARACTER_SKIP if category == "character" else set())
    return "\n".join(head + render_value({k: v for k, v in rec.items() if k not in skip}))


def summary_of(rec: dict[str, Any]) -> str:
    for k in ("summary", "description", "premise", "definition", "purpose", "motivation", "narrative_role", "public_image", "notes"):
        if isinstance(rec.get(k), str) and rec[k]:
            return rec[k][:400]
    traits = rec.get("personality_traits")
    if traits:
        return ", ".join(traits)[:400]
    return ""


def split_markdown(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    title, buf = "", []
    for line in text.splitlines():
        if re.match(r"^#{1,3} ", line):
            if buf and "".join(buf).strip():
                parts.append((title, "\n".join(buf).strip()))
            title, buf = line.lstrip("#").strip(), []
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        parts.append((title, "\n".join(buf).strip()))
    return parts


# --------------------------------------------------------------------------- import
def link_pending_stories(db: Session, world: World) -> None:
    """Stories imported from a package before their world existed here get that world now (matched by id or slug)."""
    for s in db.scalars(select(Story).where(Story.world_id.is_(None))):
        ref = (s.settings_json or {}).get("pending_world")
        if ref and (ref.get("id") == world.id or ref.get("slug") == world.slug):
            s.world_id = world.id
            s.settings_json = {k: v for k, v in s.settings_json.items() if k != "pending_world"}


def import_pack(db: Session, pack_dir: Path, world_slug: str | None = None) -> dict[str, Any]:
    pack_dir = pack_dir.resolve()
    run = ImportRun(kind="lore", status="running")
    db.add(run)
    db.flush()
    report: dict[str, Any] = {"pack_path": str(pack_dir), "files_loaded": [], "parse_errors": [], "entities_by_category": {},
                              "duplicate_ids": [], "missing_ids": [], "unresolved_references": [], "source_references": {},
                              "warnings": [], "generated_ids": []}
    manifest, manifest_report = pack_manifest.load(pack_dir)
    report["pack"] = manifest_report
    readme = pack_dir / "README.md"
    world_name = pack_dir.name.replace("_", " ").title()
    if manifest:
        world_name = manifest["name"]
    elif readme.is_file():
        m = re.search(r"^#\s+(.+)$", readme.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            world_name = re.split(r"\s+[—–-]\s+", m.group(1))[0].strip()
    
    if world_slug:
        slug = world_slug
    elif manifest:
        slug = manifest["id"]
    else:
        slug = re.sub(r"[^a-z0-9]+", "_", world_name.lower()).strip("_") or "world"

    world = db.scalar(select(World).where(World.slug == slug))
    if world is None:
        world = World(slug=slug, name=world_name)
        db.add(world)
        db.flush()
    else:
        if manifest:
            world.name = world_name
        db.execute(delete(LoreChunk).where(LoreChunk.world_id == world.id))
        db.execute(delete(LoreEntity).where(LoreEntity.world_id == world.id))
        db.execute(delete(LoreDocument).where(LoreDocument.world_id == world.id))
    world.import_version = (world.import_version or 0) + 1
    world.source_path = str(pack_dir)
    world.imported_at = now_iso()
    run.world_id = world.id
    link_pending_stories(db, world)

    entities: dict[tuple[str, str], dict[str, Any]] = {}
    entity_meta: dict[tuple[str, str], str] = {}
    all_records: list[tuple[str, dict[str, Any]]] = []
    index_entities: list[dict[str, Any]] = []
    md_docs: dict[str, str] = {}

    files = sorted(p for p in pack_dir.rglob("*") if p.is_file() and p.suffix.lower() in (".json", ".md"))
    manifest_files = set((manifest or {}).get("sources") or [])
    for f in files:
        rel = f.relative_to(pack_dir).as_posix()
        if rel in manifest_files:  # pack.json and the files it points to are engine settings, not lore
            continue
        if rel.startswith("schemas/"):
            report["files_loaded"].append(rel)
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if f.suffix.lower() == ".md":
            db.add(LoreDocument(world_id=world.id, rel_path=rel, kind="md", title=f.stem, content=text,
                                import_version=world.import_version))
            md_docs[rel] = text
            report["files_loaded"].append(rel)
            continue
        try:
            data = json.loads(text)
        except ValueError as e:
            report["parse_errors"].append({"file": rel, "error": str(e)})
            db.add(LoreDocument(world_id=world.id, rel_path=rel, kind="json", title=f.stem, content="", parse_ok=False,
                                error=str(e), import_version=world.import_version))
            continue
        report["files_loaded"].append(rel)
        shown = json.dumps(strip_hidden(data)[0], indent=2, ensure_ascii=False) if _has_hidden(data) else text
        db.add(LoreDocument(world_id=world.id, rel_path=rel, kind="json", title=f.stem, content=shown,
                            import_version=world.import_version))
        if rel == "characters/index.json":
            index_entities = data.get("entities", [])
            continue
        if not isinstance(data, dict):
            continue
        before = len(entities)
        file_cat = FILE_RECORD_CATEGORY.get(f.stem)
        if file_cat and data.get("id"):
            top = {k: v for k, v in data.items() if not (isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0])}
            _collect(entities, entity_meta, report, file_cat, top, rel)
        for key, val in data.items():
            if isinstance(val, dict) and val.get("id") and key in ("continent",):
                _collect(entities, entity_meta, report, "region", val, rel)
            if not (isinstance(val, list) and val and isinstance(val[0], dict)):
                continue
            if key == "terms":
                cat = "glossary" if "definition" in val[0] else "calendar"
            elif key == "relationships":
                val = strip_hidden(val)[0]
                for r in val:
                    all_records.append((rel, r))
                db.add(LoreChunk(world_id=world.id, category="relationship", title=f"Relationships ({rel})",
                                 content="\n".join(f"{r.get('from')} → {r.get('to')}: {r.get('type')}"
                                                   + (f" — {r['description']}" if r.get("description") else "")
                                                   + f" [confidence: {r.get('confidence', '?')}]" for r in val)))
                continue
            elif key == "events" and "calendar" in rel:
                cat = "calendar"
            else:
                cat = KEY_CATEGORY.get(key) or STEM_CATEGORY.get(f.stem)
            if not cat:
                continue
            for item in val:
                if isinstance(item, dict) and not item.get("id") and item.get("name"):
                    # an entry with a name but no id: the id is made from the name (reported, never silent)
                    item = {"id": _slug(item["name"]), **item}
                    item.setdefault("group", key.replace("_", " "))
                    report["generated_ids"].append({"file": rel, "id": item["id"], "name": item["name"], "from": "name"})
                if isinstance(item, dict) and item.get("id"):
                    _collect(entities, entity_meta, report, cat, item, rel)
        stem_cat = STEM_CATEGORY.get(f.stem)
        if len(entities) == before and stem_cat and rel != "characters/index.json":
            # nothing recognised: an object-shaped file ({"martial_realm": {...}, "magic_realm": {...}}) becomes one
            # record per entry, or, for a flat overview (world.json), one record for the whole file
            entries = {k: v for k, v in data.items() if isinstance(v, dict)}
            if entries and len(entries) == len([v for v in data.values() if not isinstance(v, (str, int, float, bool))]):
                for k, v in entries.items():
                    item = {"id": _slug(k), "name": str(v.get("name") or k.replace("_", " ").title()), **v}
                    report["generated_ids"].append({"file": rel, "id": item["id"], "name": item["name"], "from": "key"})
                    _collect(entities, entity_meta, report, stem_cat, item, rel)
            else:
                item = {"id": _slug(f.stem), "name": f"{world_name} — {f.stem.replace('_', ' ')}", **data}
                report["generated_ids"].append({"file": rel, "id": item["id"], "name": item["name"], "from": "file"})
                _collect(entities, entity_meta, report, stem_cat, item, rel)
        if "calendar" in rel:
            cal = strip_hidden(data)[0]
            db.add(LoreChunk(world_id=world.id, category="calendar", title=data.get("title", "Calendar"),
                             content=record_text({k: v for k, v in cal.items() if k not in ("events", "terms")}),
                             confidence=data.get("confidence"), canon_status=data.get("canon_status")))

    known_ids = {eid for (_cat, eid) in entities}
    source_ids = {eid for (cat, eid) in entities if cat == "source"}

    # characters listed in index.json but without a full record
    char_ids = {eid for (cat, eid) in entities if cat == "character"}
    for ie in index_entities:
        if ie.get("id") not in char_ids:
            report["missing_ids"].append({"id": ie.get("id"), "listed_in": "characters/index.json", "expected_file": ie.get("file")})
    # index metadata fills gaps (e.g. type) without overriding full records
    for ie in index_entities:
        key = ("character", ie.get("id"))
        if key in entities:
            entities[key].setdefault("_index_type", ie.get("type"))

    for (cat, eid), rec in entities.items():
        all_records.append((entity_meta[(cat, eid)], rec))
    for rel, rec in all_records:
        for fld in REF_FIELDS_SINGLE:
            v = rec.get(fld)
            if isinstance(v, str) and v and v not in known_ids:
                report["unresolved_references"].append({"file": rel, "record": rec.get("id") or f"{rec.get('from')}→{rec.get('to')}", "field": fld, "value": v})
        for fld in REF_FIELDS_LIST:
            for v in rec.get(fld) or []:
                if isinstance(v, str) and v not in known_ids:
                    report["unresolved_references"].append({"file": rel, "record": rec.get("id"), "field": fld, "value": v})
        for note in rec.get("relationship_notes") or rec.get("relationships") or []:
            if isinstance(note, dict) and note.get("target_id") and note["target_id"] not in known_ids:
                report["unresolved_references"].append({"file": rel, "record": rec.get("id"), "field": "relationship target", "value": note["target_id"]})
        for sid in rec.get("source_ids") or []:
            report["source_references"][sid] = report["source_references"].get(sid, 0) + 1
            if source_ids and sid not in source_ids:
                report["unresolved_references"].append({"file": rel, "record": rec.get("id"), "field": "source_ids", "value": sid})

    for (cat, eid), rec in entities.items():
        rel = entity_meta[(cat, eid)]
        name = rec.get("name") or rec.get("term") or rec.get("title") or eid
        le = LoreEntity(world_id=world.id, entity_id=eid, category=cat,
                        entity_type=str(rec.get("type") or rec.get("_index_type") or rec.get("category") or cat),
                        name=name, aliases_json=list(rec.get("aliases") or []), summary=summary_of(rec),
                        data_json={k: v for k, v in rec.items() if k != "_index_type"},
                        confidence=rec.get("confidence"), canon_status=rec.get("canon_status"),
                        source_ids_json=list(rec.get("source_ids") or []), file=rel)
        db.add(le)
        db.flush()
        if cat in NOT_LORE_CATEGORIES:
            continue  # kept as a record (the wizard's openings), never retrieved as lore in a story
        db.add(LoreChunk(world_id=world.id, entity_row_id=le.id, entity_id=eid, category=cat, title=name,
                         content=record_text(rec, cat), confidence=rec.get("confidence"), canon_status=rec.get("canon_status")))
        report["entities_by_category"][cat] = report["entities_by_category"].get(cat, 0) + 1

    pack_files = (manifest or {}).get("files") or pack_manifest.DEFAULT_FILES
    for rel, text in md_docs.items():
        # v0.6 (phase 9): instructions for the AI and opening scenarios are not world lore: the narrator gets its rules
        # whole in the system prompt and the openings when a story starts; retrieved again they only cost tokens
        if rel == pack_files.get("system_prompt") or rel.startswith(NOT_LORE_DIRS) or rel.lower() == "readme.md":
            continue
        for title, body in split_markdown(text):
            db.add(LoreChunk(world_id=world.id, category="document", title=f"{Path(rel).stem}: {title}" if title else Path(rel).stem,
                             content=body))

    # world-level data used by the new-story wizard and context builder
    sys_prompt = md_docs.get(pack_files.get("system_prompt") or "", "")
    world.system_prompt = sys_prompt
    starters = _starters(entities, md_docs.get("scenarios/intro_blueprints.md", ""))
    if manifest and manifest.get("starters"):  # pack.json starters come first and replace lore ones with the same id
        own = [{**s, "confidence": None, "canon_status": None} for s in manifest["starters"]]
        starters = own + [s for s in starters if s["id"] not in {o["id"] for o in own}]
    premise = md_docs.get(pack_files.get("premise") or "", "")
    first = split_markdown(premise) if premise else []  # a premise with only a title has no section
    world.description = (manifest or {}).get("description") or (first[0][1][:1200] if first else "")
    world.data_json = {
        "starters": starters,
        "locations": [{"id": eid, "name": r.get("name", eid)} for (c, eid), r in entities.items() if c == "location"],
        "characters": [{"id": eid, "name": r.get("name", eid), "type": r.get("type") or r.get("_index_type")}
                       for (c, eid), r in entities.items() if c == "character"],
        # the banner shown when choosing the world: the pack's own canon_note (packs without pack.json keep the old note)
        # story library card (pack.json format 2): {"summary": {lang: text}, "tags": {lang: [...]}, "cover": path}
        "library": (manifest or {}).get("library") or {},
        "canon_note": (manifest or {}).get("canon_note", "") if manifest else
                      "Imported from a research-based reference pack. Records carry confidence and canon_status; "
                      "community reconstructions are not guaranteed official canon.",
        # the pack's engine settings (pack.json); read by the engine from Phase 2 of the multi-story work
        "pack": manifest,
    }
    if manifest:
        char_ids = {eid for (c, eid) in entities if c == "character"}
        report["pack"]["warnings"] = report["pack"]["warnings"] + pack_manifest.check_references(manifest, char_ids)
    report["entity_total"] = sum(report["entities_by_category"].values())
    report["world"] = {"id": world.id, "name": world.name, "import_version": world.import_version}
    secrets = report.pop("_hidden", {})
    world.data_json = {**(world.data_json or {}), "hidden": secrets}
    report["hidden_notes"] = sum(len(v) for v in secrets.values())  # a count only: the notes themselves stay hidden
    run.report_json = report
    run.status = "succeeded_with_warnings" if (report["parse_errors"] or report["unresolved_references"] or report["missing_ids"]
                                               or report["pack"]["errors"] or report["pack"]["warnings"]) else "succeeded"
    run.finished_at = now_iso()
    db.flush()
    return {"run_id": run.id, "status": run.status, "report": report}


def _collect(entities, meta, report, cat: str, item: dict[str, Any], rel: str) -> None:
    key = (cat, item["id"])
    if key in entities:
        report["duplicate_ids"].append({"id": item["id"], "category": cat, "files": [meta[key], rel]})
        return
    clean, notes = strip_hidden(item)
    if notes:  # kept apart from everything the player can see; the narrator gets them (context_builder)
        report.setdefault("_hidden", {})[f"{cat}:{item['id']}"] = notes
    entities[key] = clean
    meta[key] = rel


def _blueprint_from(rec: dict[str, Any]) -> str:
    """An opening built from a scenario that has only a description (and maybe a location)."""
    desc = str(rec.get("description") or rec.get("purpose") or "").strip()
    if not desc:
        return ""
    where = f" Location: {rec['location']}." if rec.get("location") and str(rec["location"]).lower() != "multiple" else ""
    return (f"Opening premise: {rec.get('name', '')} — {desc}{where} Begin in a concrete place and moment, present one "
            "immediate situation, and end on a clear opening for the player. Do not decide the protagonist's dialogue, "
            "feelings or actions.")


def _starters(entities: dict[tuple[str, str], dict[str, Any]], blueprints_md: str) -> list[dict[str, Any]]:
    blue = {}
    for title, body in split_markdown(blueprints_md):
        name = re.split(r"\s+[—–-]\s+", title)[0].strip().lower()
        blue[name] = re.sub(r"^>\s?", "", body, flags=re.M).strip()
    out = []
    for (cat, eid), rec in entities.items():
        if cat != "scenario":
            continue
        out.append({"id": eid, "name": rec.get("name", eid), "purpose": rec.get("purpose", ""),
                    "blueprint": blue.get(str(rec.get("name", "")).lower()) or rec.get("ai_initialization", "")
                    or _blueprint_from(rec),
                    "confidence": rec.get("confidence"), "canon_status": rec.get("canon_status")})
    return out
