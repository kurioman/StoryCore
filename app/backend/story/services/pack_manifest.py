"""Lore pack manifest: ``pack.json`` at the root of a lore pack (format reference: LOREPACK_FORMAT.md).

The manifest tells the engine what the lore files themselves do not say: the story's identity, its files, the player's
stats, the opening scenarios, unique posts, closed groups, fixed facts, recurring gatherings, places, the calendar and
the genre modules it uses. Lore files (characters, factions, locations...) are still imported as before.

Rules
* Only ``format_version``, ``id`` and ``name`` are required. Every other section is optional; a feature whose section
  is missing is simply off for that world.
* Any section may be given as a path (relative to the pack folder) to a JSON file holding that section, so long sections
  can live in their own file while ``pack.json`` stays the single entry point.
* A broken section is skipped and reported; it never blocks the rest of the pack. A missing or invalid identity is an
  error: the pack is then imported the old way (name guessed from the folder) and the report says why.
* The pack provides defaults only. Corrections the player makes inside the app are stored separately per world and
  applied on top (that layering is wired up in the engine, not here).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MANIFEST = "pack.json"
FORMAT_VERSION = 2  # 2 (v1.8): summary, tags, cover for the story library. Format 1 packs still load unchanged.
SUPPORTED_FORMATS = (1, 2)
COVER_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".avif"}
SUMMARY_MAX = 600
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,79}$")
KNOWN_MODULES = {"school"}  # genre modules the engine has behaviour for; other names are accepted and kept
STAT_TYPES = {"current_max", "number", "text"}
FACT_KINDS = {"aunt_of", "sibling_of", "parent_of", "spouse_of", "family_branch", "other"}
DEFAULT_FILES = {"system_prompt": "ai/narrative_system_prompt.md", "premise": "lore/premise.md", "images": None}
SECTIONS = ("stats", "starters", "posts", "closed_groups", "facts", "gatherings", "places", "calendar", "never_random")
LIBRARY_KEYS = ("summary", "tags", "cover")
TOP_KEYS = {"format_version", "id", "name", "description", "canon_note", "modules", "files", *LIBRARY_KEYS, *SECTIONS}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December"]


class _Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def to_dict(self) -> dict[str, list[str]]:
        return {"errors": self.errors, "warnings": self.warnings}


def has_manifest(pack_dir: Path) -> bool:
    return (pack_dir / MANIFEST).is_file()


def load(pack_dir: Path) -> tuple[dict[str, Any] | None, dict[str, list[str]]]:
    """(manifest, report). ``manifest`` is None when there is no pack.json or its identity is unusable; otherwise it is
    the normalised manifest with every valid section (invalid ones are left out and reported)."""
    rep = _Report()
    path = pack_dir / MANIFEST
    if not path.is_file():
        rep.warnings.append(f"No {MANIFEST} in this pack: the world name is guessed from the folder and every optional "
                            "feature is off. See LOREPACK_FORMAT.md.")
        return None, rep.to_dict()
    raw = _read_json(path, rep, MANIFEST)
    if not isinstance(raw, dict):
        if raw is not None:
            rep.errors.append(f"{MANIFEST} must contain a JSON object {{...}}.")
        return None, rep.to_dict()

    fv = raw.get("format_version")
    if fv not in SUPPORTED_FORMATS:
        rep.errors.append(f"{MANIFEST}: format_version must be one of {', '.join(map(str, SUPPORTED_FORMATS))} "
                          f"(found {fv!r}).")
    pid, name = raw.get("id"), raw.get("name")
    if not isinstance(pid, str) or not ID_RE.match(pid):
        rep.errors.append(f"{MANIFEST}: id must be lowercase letters, digits and underscores, starting with a letter or "
                          f"digit, e.g. \"my_story\" (found {pid!r}).")
    if not isinstance(name, str) or not name.strip():
        rep.errors.append(f"{MANIFEST}: name is required (the title shown in the app).")
    if rep.errors:
        return None, rep.to_dict()

    for k in raw:
        if k not in TOP_KEYS and not k.startswith("_"):
            rep.warnings.append(f"{MANIFEST}: unknown section \"{k}\" ignored (check the spelling).")

    out: dict[str, Any] = {"format_version": fv, "id": pid, "name": name.strip(),
                           "description": _str(raw.get("description")), "canon_note": _str(raw.get("canon_note"))}
    out["sources"] = [MANIFEST]  # files read for the manifest (the lore import skips them)
    out["modules"] = _modules(raw.get("modules"), rep)
    out["files"] = _files(pack_dir, raw.get("files"), rep)
    if fv == 1 and any(k in raw for k in LIBRARY_KEYS):
        rep.warnings.append(f"{MANIFEST}: summary, tags and cover need format_version 2; they are read anyway.")
    out["library"] = _library(pack_dir, raw, rep)
    for sec in SECTIONS:
        if sec not in raw:
            continue
        value = _resolve(pack_dir, sec, raw[sec], rep)
        if isinstance(raw[sec], str):
            out["sources"].append(raw[sec].strip().replace("\\", "/"))
        if value is None:
            continue
        clean = VALIDATORS[sec](value, rep)
        if clean is not None:
            out[sec] = clean
    return out, rep.to_dict()


def check_references(manifest: dict[str, Any], character_ids: set[str]) -> list[str]:
    """Warnings for character ids the manifest names that the imported lore does not contain (checked after import)."""
    warnings: list[str] = []

    def chk(where: str, cid: Any) -> None:
        if isinstance(cid, str) and cid and cid not in character_ids:
            warnings.append(f"{where}: unknown character id \"{cid}\" (not found in the lore files).")

    for p in manifest.get("posts") or []:
        chk(f"posts[{p['id']}].character", p["character"])
    for g in manifest.get("closed_groups") or []:
        for m in g.get("members") or []:
            chk(f"closed_groups[{g['id']}].members", m)
    for i, f in enumerate(manifest.get("facts") or []):
        chk(f"facts[{i}].subject", f.get("subject"))
        chk(f"facts[{i}].object", f.get("object"))
    for g in manifest.get("gatherings") or []:
        chk(f"gatherings[{g['id']}].leader", g.get("leader"))
        for m in g.get("members") or []:
            chk(f"gatherings[{g['id']}].members", m)
    for p in manifest.get("places") or []:
        for m in p.get("regulars") or []:
            chk(f"places[{p['id']}].regulars", m)
    return warnings


# --------------------------------------------------------------------------- helpers
def _read_json(path: Path, rep: _Report, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as e:
        rep.errors.append(f"{label}: cannot be read ({e}).")
    except ValueError as e:
        rep.errors.append(f"{label}: not valid JSON ({e}).")
    return None


def _inside(pack_dir: Path, rel: str) -> Path | None:
    p = (pack_dir / rel).resolve()
    return p if p == pack_dir.resolve() or pack_dir.resolve() in p.parents else None


def _resolve(pack_dir: Path, sec: str, value: Any, rep: _Report) -> Any:
    """A section given as "path/to/file.json" is read from that file. The file may hold the section itself or an
    object with the section's name as its key."""
    if not isinstance(value, str):
        return value
    p = _inside(pack_dir, value)
    if p is None or not p.is_file():
        rep.errors.append(f"{sec}: file \"{value}\" not found in the pack; section skipped.")
        return None
    data = _read_json(p, rep, value)
    if isinstance(data, dict) and sec in data and sec != "calendar":
        return data[sec]
    if sec == "calendar" and isinstance(data, dict) and isinstance(data.get("calendar"), dict):
        return data["calendar"]
    return data


def _str(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _strs(v: Any) -> list[str]:
    return [x.strip() for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def _id_ok(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _list_of_objects(sec: str, value: Any, rep: _Report) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        rep.errors.append(f"{sec}: must be a list [...]; section skipped.")
        return None
    items = []
    for i, x in enumerate(value):
        if isinstance(x, dict):
            items.append(x)
        else:
            rep.warnings.append(f"{sec}[{i}]: not an object {{...}}; entry skipped.")
    return items


def _need_ids(sec: str, items: list[dict[str, Any]], rep: _Report) -> list[dict[str, Any]]:
    out, seen = [], set()
    for i, x in enumerate(items):
        if not _id_ok(x.get("id")):
            rep.warnings.append(f"{sec}[{i}]: \"id\" is required; entry skipped.")
        elif x["id"] in seen:
            rep.warnings.append(f"{sec}: id \"{x['id']}\" is used twice; the second entry is skipped.")
        else:
            seen.add(x["id"])
            out.append(x)
    return out


# --------------------------------------------------------------------------- section validators
def _modules(v: Any, rep: _Report) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        rep.errors.append("modules: must be a list of genre names, e.g. [\"school\"]; ignored.")
        return []
    mods = [m.strip().lower() for m in v if isinstance(m, str) and m.strip()]
    for m in mods:
        if m not in KNOWN_MODULES:
            rep.warnings.append(f"modules: \"{m}\" is kept, but the engine has no behaviour for it yet.")
    return list(dict.fromkeys(mods))


def _localized(v: Any) -> Any:
    """A text or list given once ("...") or per interface language ({"en": "...", "fr": "..."})."""
    return {k.strip().lower(): x for k, x in v.items() if isinstance(k, str) and k.strip()} if isinstance(v, dict) else v


def _library(pack_dir: Path, raw: dict[str, Any], rep: _Report) -> dict[str, Any]:
    """Story library card (format 2): short summary, tags, cover image. Texts may be per language."""
    out: dict[str, Any] = {}
    summary = _localized(raw.get("summary"))
    if isinstance(summary, str) and summary.strip():
        out["summary"] = {"default": summary.strip()}
    elif isinstance(summary, dict):
        out["summary"] = {k: v.strip() for k, v in summary.items() if isinstance(v, str) and v.strip()}
    elif summary is not None:
        rep.warnings.append("summary: must be a text, or texts per language {\"en\": \"...\", \"fr\": \"...\"}; ignored.")
    for lang, text in (out.get("summary") or {}).items():
        if len(text) > SUMMARY_MAX:
            rep.warnings.append(f"summary ({lang}): {len(text)} characters; keep it under {SUMMARY_MAX} so it fits on "
                                "the library card.")
    tags = _localized(raw.get("tags"))
    if isinstance(tags, list):
        out["tags"] = {"default": _strs(tags)}
    elif isinstance(tags, dict):
        out["tags"] = {k: _strs(v) for k, v in tags.items() if isinstance(v, list)}
    elif tags is not None:
        rep.warnings.append("tags: must be a list [\"Fantasy\", ...], or lists per language; ignored.")
    cover = raw.get("cover")
    if isinstance(cover, str) and cover.strip():
        rel = cover.strip().replace("\\", "/")
        f = (pack_dir / rel).resolve()
        if pack_dir.resolve() not in f.parents:
            rep.warnings.append("cover: must be a path inside the pack; ignored.")
        elif f.suffix.lower() not in COVER_EXTS:
            rep.warnings.append(f"cover: use a {', '.join(sorted(COVER_EXTS))} image; ignored.")
        else:
            out["cover"] = rel
            if not f.is_file():
                rep.warnings.append(f"cover: file \"{rel}\" not found yet; the library shows a plain card until it exists.")
    elif cover not in (None, ""):
        rep.warnings.append("cover: must be a path inside the pack, e.g. \"cover.webp\"; ignored.")
    return out


def _files(pack_dir: Path, v: Any, rep: _Report) -> dict[str, str | None]:
    files = dict(DEFAULT_FILES)
    if v is not None and not isinstance(v, dict):
        rep.errors.append("files: must be an object {...}; default file locations used.")
        v = None
    for k, rel in (v or {}).items():
        if k not in DEFAULT_FILES:
            rep.warnings.append(f"files: unknown entry \"{k}\" ignored.")
            continue
        if not isinstance(rel, str) or not rel.strip():
            rep.warnings.append(f"files.{k}: must be a path inside the pack; default used.")
            continue
        files[k] = rel.strip().replace("\\", "/")
    if files["images"] is None:  # convention: the one sub-folder named "images" or ending in "_images"
        hits = sorted(d.name for d in pack_dir.iterdir() if d.is_dir() and (d.name == "images" or d.name.endswith("_images")))
        files["images"] = hits[0] if len(hits) == 1 else None
    for k, rel in files.items():
        if rel is None:
            continue
        p = _inside(pack_dir, rel)
        exists = p is not None and (p.is_dir() if k == "images" else p.is_file())
        if not exists:
            explicit = isinstance(v, dict) and k in v
            if explicit or k != "premise":
                rep.warnings.append(f"files.{k}: \"{rel}\" not found in the pack.")
            files[k] = None
    return files


def _stats(v: Any, rep: _Report) -> list[dict[str, Any]] | None:
    items = _list_of_objects("stats", v, rep)
    if items is None:
        return None
    out = []
    for i, s in enumerate(items):
        label, typ = _str(s.get("label")), s.get("type", "number")
        if not label:
            rep.warnings.append(f"stats[{i}]: \"label\" is required; stat skipped.")
            continue
        if typ not in STAT_TYPES:
            rep.warnings.append(f"stats[{label}]: type must be one of {sorted(STAT_TYPES)}; stat skipped.")
            continue
        st: dict[str, Any] = {"label": label, "type": typ, "value": s.get("value", "" if typ == "text" else 0)}
        if typ == "current_max":
            st["max"] = s.get("max", st["value"])
        if s.get("unit"):
            st["unit"] = str(s["unit"])
        out.append(st)
    return out


def _starters(v: Any, rep: _Report) -> list[dict[str, Any]] | None:
    items = _list_of_objects("starters", v, rep)
    if items is None:
        return None
    out = []
    for s in _need_ids("starters", items, rep):
        if not _str(s.get("blueprint")):
            rep.warnings.append(f"starters[{s['id']}]: \"blueprint\" (the opening instructions) is required; skipped.")
            continue
        item = {"id": s["id"], "name": _str(s.get("name")) or s["id"], "blueprint": _str(s["blueprint"]),
                "purpose": _str(s.get("purpose"))}
        if "scene" in s:  # optional starting scene (place, time, date, who is present); checked when a story starts
            if isinstance(s["scene"], dict):
                item["scene"] = s["scene"]
            else:
                rep.warnings.append(f"starters[{s['id']}]: \"scene\" must be an object; ignored.")
        out.append(item)
    return out


def _posts(v: Any, rep: _Report) -> list[dict[str, Any]] | None:
    items = _list_of_objects("posts", v, rep)
    if items is None:
        return None
    out = []
    for p in _need_ids("posts", items, rep):
        if not _str(p.get("title")) or not _id_ok(p.get("character")):
            rep.warnings.append(f"posts[{p['id']}]: \"title\" and \"character\" are required; skipped.")
            continue
        out.append({"id": p["id"], "title": _str(p["title"]), "character": p["character"].strip(),
                    "aliases": _strs(p.get("aliases")), "note": _str(p.get("note")), "mandatory": bool(p.get("mandatory"))})
    return out


def _closed_groups(v: Any, rep: _Report) -> list[dict[str, Any]] | None:
    items = _list_of_objects("closed_groups", v, rep)
    if items is None:
        return None
    out = []
    for g in _need_ids("closed_groups", items, rep):
        members, types = _strs(g.get("members")), _strs(g.get("types"))
        if not members and not types:
            rep.warnings.append(f"closed_groups[{g['id']}]: needs \"members\" (character ids) or \"types\" (character "
                                "types); skipped.")
            continue
        out.append({"id": g["id"], "title": _str(g.get("title")) or g["id"], "members": members, "types": types})
    return out


def _facts(v: Any, rep: _Report) -> list[dict[str, Any]] | None:
    items = _list_of_objects("facts", v, rep)
    if items is None:
        return None
    out = []
    for i, f in enumerate(items):
        kind, subject = f.get("kind"), f.get("subject")
        if kind not in FACT_KINDS:
            rep.warnings.append(f"facts[{i}]: kind must be one of {sorted(FACT_KINDS)} (found {kind!r}); skipped.")
            continue
        if not _id_ok(subject):
            rep.warnings.append(f"facts[{i}]: \"subject\" (a character id) is required; skipped.")
            continue
        fact: dict[str, Any] = {"kind": kind, "subject": subject.strip(), "note": _str(f.get("note"))}
        if kind == "family_branch":
            if not _str(f.get("family")):
                rep.warnings.append(f"facts[{i}]: a family_branch fact needs \"family\"; skipped.")
                continue
            fact.update(family=_str(f["family"]), branch=_str(f.get("branch")))
        elif kind == "other":
            if not _str(f.get("text")):
                rep.warnings.append(f"facts[{i}]: an \"other\" fact needs \"text\"; skipped.")
                continue
            fact["text"] = _str(f["text"])
            if _id_ok(f.get("object")):
                fact["object"] = f["object"].strip()
        else:
            if not _id_ok(f.get("object")):
                rep.warnings.append(f"facts[{i}]: a {kind} fact needs \"object\" (a character id); skipped.")
                continue
            fact["object"] = f["object"].strip()
        out.append(fact)
    return out


def _gatherings(v: Any, rep: _Report) -> list[dict[str, Any]] | None:
    items = _list_of_objects("gatherings", v, rep)
    if items is None:
        return None
    out = []
    for g in _need_ids("gatherings", items, rep):
        keywords = _strs(g.get("keywords"))
        if not keywords:
            rep.warnings.append(f"gatherings[{g['id']}]: \"keywords\" are required (how the engine recognises it); skipped.")
            continue
        out.append({"id": g["id"], "name": _str(g.get("name")) or g["id"], "kind": _str(g.get("kind")) or "gathering",
                    "leader": _str(g.get("leader")) or None, "members": _strs(g.get("members")), "keywords": keywords,
                    "note": _str(g.get("note"))})
    return out


def _places(v: Any, rep: _Report) -> list[dict[str, Any]] | None:
    items = _list_of_objects("places", v, rep)
    if items is None:
        return None
    out = []
    for p in _need_ids("places", items, rep):
        keywords = _strs(p.get("keywords"))
        if not keywords:
            rep.warnings.append(f"places[{p['id']}]: \"keywords\" are required; skipped.")
            continue
        likely = p.get("likely") if isinstance(p.get("likely"), dict) else {}
        out.append({"id": p["id"], "keywords": keywords, "regulars": _strs(p.get("regulars")),
                    "likely": {"affiliations": _strs(likely.get("affiliations")), "traits": _strs(likely.get("traits"))}})
    return out


def _calendar(v: Any, rep: _Report) -> dict[str, Any] | None:
    if not isinstance(v, dict):
        rep.errors.append("calendar: must be an object {...}; section skipped.")
        return None
    start = _str(v.get("year_start")) or "January"
    month = next((m for m in MONTHS if m.casefold() == start.casefold()), None)
    if month is None:
        rep.warnings.append(f"calendar.year_start: \"{start}\" is not a month name; January used.")
        month = "January"
    return {"year_label": _str(v.get("year_label")) or "Year", "year_start": month}


def _never_random(v: Any, rep: _Report) -> list[str] | None:
    if not isinstance(v, list):
        rep.errors.append("never_random: must be a list of character types; section skipped.")
        return None
    return _strs(v)


VALIDATORS = {"stats": _stats, "starters": _starters, "posts": _posts, "closed_groups": _closed_groups, "facts": _facts,
              "gatherings": _gatherings, "places": _places, "calendar": _calendar, "never_random": _never_random}
