"""Lore pack checker: everything the app would complain about when it loads a pack, in one readable report.

It runs the real lore import and portrait scan against a throw-away database, so what it reports is exactly what the
app will do with the pack (nothing in the player's data folder is read or written). On top of the importer's own
report it checks what a pack author usually gets wrong:

* pack.json: identity, sections, files it points to, character ids it names;
* lore files: invalid JSON (with line and column), duplicate ids, references to ids that do not exist;
* openings (starters): portrait tags such as ``[Lily:1]`` that name no known character;
* portraits: files that match no character, missing expressions (1 to 6), unreadable images, the same picture used for
  every expression, very large files.

Use it from the command line (``Check Lore Packs.bat``, or ``python -m story.pack_check [folder ...]``) or the API
(``GET /api/lore/packs/check``).
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..db import Database
from ..models import AssetRoot, World
from . import assets as assets_svc
from . import lore_import, pack_manifest
from .entities import Entity, EntityIndex
from .portrait_tags import TAG

LARGE_IMAGE_BYTES = 600 * 1024  # above this, a portrait is worth recompressing (the app shows them at most ~900 px wide)
EXPRESSION_NAMES = {1: "neutral", 2: "happy", 3: "sad", 4: "angry", 5: "disdain", 6: "love/shy"}


class Report:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []
        self.stats: dict[str, Any] = {}

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"folder": str(self.folder), "name": self.folder.name, "ok": self.ok, "errors": self.errors,
                "warnings": self.warnings, "info": self.info, "stats": self.stats}


def check_pack(pack_dir: Path) -> dict[str, Any]:
    """Check one pack folder. Never raises for a broken pack: problems are in the report."""
    pack_dir = Path(pack_dir).resolve()
    rep = Report(pack_dir)
    if not pack_dir.is_dir():
        rep.errors.append(f"Folder not found: {pack_dir}")
        return rep.to_dict()

    _check_json_syntax(pack_dir, rep)
    manifest, mrep = pack_manifest.load(pack_dir)
    rep.errors += [f"pack.json: {e}" if not e.startswith("pack.json") else e for e in mrep["errors"]]
    if manifest is None and not mrep["errors"]:
        rep.errors += mrep["warnings"]  # no pack.json at all: the app skips this folder
        return rep.to_dict()

    with tempfile.TemporaryDirectory(prefix="storycore_check_") as tmp:
        db = Database(Path(tmp) / "check.db")
        try:
            db.migrate()
            with db.session() as s:
                result = lore_import.import_pack(s, pack_dir)
                _from_import_report(result["report"], rep)
                world = s.scalar(select(World).where(World.slug == (manifest or {}).get("id", "")))
                index = _character_index(s)
                rep.stats["character_ids"] = {cid: index.name(cid) for cid in sorted(index.entities)}
                if world is not None:
                    _check_starters(world, index, rep)
                _check_gender(s, rep)
                lib = (manifest or {}).get("library") or {}
                if manifest and not lib.get("summary"):
                    rep.info.append("No summary (pack.json \"summary\", format 2): the story library card has no text.")
                if manifest and not lib.get("cover"):
                    rep.info.append("No cover image (pack.json \"cover\", format 2): the story library shows a plain card.")
                if manifest and manifest["files"].get("images"):
                    _check_portraits(s, pack_dir / manifest["files"]["images"], index, rep)
                elif manifest:
                    rep.info.append("No portrait folder (pack.json files.images, or a folder named images / *_images): "
                                    "characters are shown without pictures.")
        finally:
            db.engine.dispose()  # Windows cannot delete the temporary database while it is open
    return rep.to_dict()


def check_all(packs_dir: Path) -> list[dict[str, Any]]:
    """Every folder with a pack.json inside ``packs_dir`` (the app's Lorepack folder)."""
    if not packs_dir.is_dir():
        return []
    return cross_pack_notes([check_pack(p) for p in sorted(packs_dir.iterdir())
                             if p.is_dir() and pack_manifest.has_manifest(p)])


def cross_pack_notes(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Characters with the same id in several packs. Fine since v0.5 (portraits and lore are kept per world), but
    worth knowing: a player who sees "Lily" in two stories meets two different characters."""
    owners: dict[str, list[tuple[str, str]]] = {}
    for r in reports:
        for cid, name in ((r.get("stats") or {}).get("character_ids") or {}).items():
            owners.setdefault(cid, []).append((r["name"], name))
    for r in reports:
        mine = (r.get("stats") or {}).get("character_ids") or {}
        for cid in sorted(mine):
            others = [f"{name} in {pack}" for pack, name in owners[cid] if pack != r["name"]]
            if others:
                r["info"].append(f"Character id \"{cid}\" ({mine[cid]}) also exists in another pack ({', '.join(others)}). "
                                 "Each world keeps its own portraits and lore, so this is fine; they are two characters.")
    return reports


# --------------------------------------------------------------------------- parts
def _check_json_syntax(pack_dir: Path, rep: Report) -> None:
    """Exact position of JSON errors (the importer only says the file was skipped)."""
    for f in sorted(pack_dir.rglob("*.json")):
        rel = f.relative_to(pack_dir).as_posix()
        try:
            json.loads(f.read_text(encoding="utf-8-sig"))
        except UnicodeDecodeError:
            rep.errors.append(f"{rel}: not UTF-8 text. Save it as UTF-8.")
        except json.JSONDecodeError as e:
            rep.errors.append(f"{rel}: invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}. "
                              "The app skips this file.")


def _from_import_report(r: dict[str, Any], rep: Report) -> None:
    pack = r.get("pack") or {}
    known = set(rep.errors)
    rep.warnings += [w for w in pack.get("warnings", []) if w not in known]
    for d in r.get("duplicate_ids", []):
        rep.warnings.append(f"Duplicate id \"{d['id']}\" ({d['category']}) in {' and '.join(d['files'])}: "
                            "only the first one is kept.")
    for m in r.get("missing_ids", []):
        rep.warnings.append(f"characters/index.json lists \"{m['id']}\" but no character record has that id"
                            + (f" (expected in {m['expected_file']})" if m.get("expected_file") else "") + ".")
    for u in r.get("unresolved_references", []):
        rep.warnings.append(f"{u['file']}: record \"{u['record']}\", field {u['field']}: \"{u['value']}\" does not "
                            "match any id in the pack.")
    # only ids made from a display name are fragile (renaming the record changes its id); ids taken from an object key
    # or a file name stay put
    gen = [g for g in r.get("generated_ids", []) if g.get("from", "name") == "name"]
    if gen:
        rep.info.append(f"{len(gen)} record(s) had no \"id\"; one was made from the name "
                        f"(e.g. {gen[0]['file']}: \"{gen[0]['id']}\"). Give them an explicit id to keep links stable.")
    rep.stats["lore_records"] = r.get("entity_total", 0)
    rep.stats["by_category"] = r.get("entities_by_category", {})
    rep.stats["files_loaded"] = len(r.get("files_loaded", []))
    if r.get("hidden_notes"):
        rep.stats["narrator_only_notes"] = r["hidden_notes"]


def _character_index(s) -> EntityIndex:
    from ..models import LoreEntity
    ents = [Entity(le.entity_id, le.name, "character", le.entity_type, list(le.aliases_json or []))
            for le in s.scalars(select(LoreEntity).where(LoreEntity.category == "character"))]
    return EntityIndex(ents)


def _check_gender(s, rep: Report) -> None:
    """Phase 2 (step 3): without a gender the narrator guessed it (Laris and Elena written as men in the test of 19/11)."""
    from ..models import LoreEntity
    missing = sorted(e.name for e in s.scalars(select(LoreEntity).where(LoreEntity.category == "character"))
                     if not str((e.data_json or {}).get("gender") or "").strip())
    if missing:
        rep.warnings.append(f"No \"gender\" for {len(missing)} character(s): {', '.join(missing[:12])}"
                            + (" ..." if len(missing) > 12 else "") + ". The narrator may guess it wrong (add \"gender\": "
                            "\"female\" / \"male\" / another word, and \"pronouns\" if useful).")


def _check_starters(world: World, index: EntityIndex, rep: Report) -> None:
    starters = (world.data_json or {}).get("starters") or []
    rep.stats["openings"] = len(starters)
    rep.stats["characters"] = len((world.data_json or {}).get("characters") or [])
    if not starters:
        rep.warnings.append("No opening (pack.json \"starters\"): the narrator has to improvise the first scene.")
    for st in starters:
        text = " ".join(str(st.get(k) or "") for k in ("blueprint", "purpose", "opening_text"))
        for name, _slot in TAG.findall(text):
            if not index.resolve(name.strip()):
                rep.warnings.append(f"Opening \"{st.get('name') or st.get('id')}\": portrait tag [{name.strip()}:…] "
                                    "names no known character, so no portrait will show for it.")


def _check_portraits(s, folder: Path, index: EntityIndex, rep: Report) -> None:
    if not folder.is_dir():
        rep.errors.append(f"Portrait folder not found: {folder.name}")
        return
    root = AssetRoot(path=str(folder), kind="folder", label=folder.name)
    s.add(root)
    s.flush()
    scan = assets_svc.scan_root(s, root, index)
    rep.stats["portrait_files"] = scan["files"]
    rep.stats["characters_with_portraits"] = scan["characters_matched"]
    from ..models import AssetManifestEntry
    entries = list(s.scalars(select(AssetManifestEntry).where(AssetManifestEntry.root_id == root.id)))
    for e in sorted(entries, key=lambda x: x.rel_path):
        if e.status == "invalid":
            rep.errors.append(f"Portrait {e.rel_path}: {e.match_reason}.")
        elif e.status in ("unmatched", "ambiguous", "duplicate"):
            rep.warnings.append(f"Portrait {e.rel_path}: {e.match_reason}.")
    for cid, gaps in sorted(scan.get("missing_slots", {}).items()):
        names = ", ".join(f"{g} ({EXPRESSION_NAMES[g]})" for g in gaps)
        rep.warnings.append(f"{index.name(cid)}: no image for expression {names}; image 1 is shown instead.")
    without = sorted(index.name(c) for c in index.entities if c not in {e.character_id for e in entries})
    if without:
        rep.info.append(f"{len(without)} character(s) without portraits: {', '.join(without[:12])}"
                        + ("…" if len(without) > 12 else "") + ".")

    # the same picture for every expression: the portrait never changes on screen
    by_char: dict[str, list[str]] = {}
    for e in entries:
        if e.status in ("matched", "override") and e.character_id:
            by_char.setdefault(e.character_id, []).append(e.rel_path)
    for cid, files in sorted(by_char.items()):
        if len(files) < 2:
            continue
        slot_of = {e.rel_path: e.slot for e in entries if e.character_id == cid and e.status in ("matched", "override")}
        groups: dict[str, list[int]] = {}
        for f in files:
            groups.setdefault(hashlib.sha1((folder / f).read_bytes()).hexdigest(), []).append(slot_of.get(f) or 0)
        if len(groups) == 1:
            rep.warnings.append(f"{index.name(cid)}: all {len(files)} expression images are the same picture, so the "
                                "portrait never changes with the mood. Placeholder?")
        else:
            for slots in groups.values():
                if len(slots) > 1:
                    rep.warnings.append(f"{index.name(cid)}: expressions {', '.join(str(x) for x in sorted(slots))} "
                                        "use the same picture.")
    large = [e for e in entries if (e.file_size or 0) > LARGE_IMAGE_BYTES]
    if large:
        total = sum(e.file_size or 0 for e in large) / 2**20
        rep.info.append(f"{len(large)} portrait(s) above {LARGE_IMAGE_BYTES // 1024} KB ({total:.0f} MB in all). "
                        "Recompressing them (WebP quality 90) keeps the look and makes the download much lighter.")


# --------------------------------------------------------------------------- text output
def format_report(r: dict[str, Any]) -> str:
    lines = [f"=== {r['name']} ===", r["folder"]]
    st = r.get("stats") or {}
    facts = []
    if "lore_records" in st:
        facts.append(f"{st['lore_records']} lore records")
    if "characters" in st:
        facts.append(f"{st['characters']} characters")
    if "openings" in st:
        facts.append(f"{st['openings']} opening(s)")
    if "portrait_files" in st:
        facts.append(f"{st['portrait_files']} portrait files for {st.get('characters_with_portraits', 0)} characters")
    if facts:
        lines.append(", ".join(facts))
    lines.append("")
    for title, key in (("ERRORS (must fix)", "errors"), ("WARNINGS (should fix)", "warnings"), ("NOTES", "info")):
        if r[key]:
            lines.append(f"{title}: {len(r[key])}")
            lines += [f"  - {x}" for x in r[key]]
            lines.append("")
    if not r["errors"] and not r["warnings"]:
        lines.append("No problems found.")
        lines.append("")
    lines.append("RESULT: " + ("OK" if r["ok"] else "ERRORS FOUND") + (f", {len(r['warnings'])} warning(s)" if r["warnings"] else ""))
    return "\n".join(lines)


_SAFE = re.compile(r"[^\x20-\x7e\n]")


def ascii_safe(text: str) -> str:
    """The Windows console can be in an old code page: keep the report readable there."""
    return _SAFE.sub(lambda m: {"…": "...", "—": "-", "–": "-", "→": "->", "“": '"', "”": '"', "’": "'"}.get(m.group(), "?"), text)
