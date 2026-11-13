"""Portrait asset scanning, character/slot matching, overrides, thumbnails and expression fallback.

Original files are never modified; thumbnails are derivative files under ``data/cache``.
Files are only served through manifest IDs whose resolved path lies inside a registered root.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssetManifestEntry, AssetOverride, AssetRoot, SlugOverride, now_iso
from .entities import EntityIndex, norm

IMAGE_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".avif"}
EXPRESSIONS = [
    {"slot": 1, "key": "neutral", "name": "Base / Neutral", "hint": "default descriptive portrait"},
    {"slot": 2, "key": "happy", "name": "Happy / Smiling", "hint": "happy, smiling, pleased"},
    {"slot": 3, "key": "sad", "name": "Sad / Sobbing", "hint": "sad, sobbing, hurt, grieving"},
    {"slot": 4, "key": "angry", "name": "Angry / Aggressive", "hint": "angry, aggressive, furious, ready to fight"},
    {"slot": 5, "key": "disdain", "name": "Disdain / Disgust", "hint": "disdainful, disgusted, contemptuous, scornful"},
    {"slot": 6, "key": "love", "name": "Love / Shy", "hint": "in love, shy, blushing, tender, embarrassed"},
]
FALLBACK_ORDER = {1: [1], 2: [2, 1], 3: [3, 1], 4: [4, 1], 5: [5, 4, 1], 6: [6, 2, 1]}
NAME_RE = re.compile(r"^(?P<slug>.*?)[\s_\-.]*\(?0*(?P<num>\d{1,2})\)?$")
VARIANTS = {"thumb": (160, 160), "card": (360, 480)}
LINKS_FILES = ("story-liens-trouves.csv", "story-liens-trouves.txt")


def safe_join(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    r = root.resolve()
    if p != r and r not in p.parents:
        raise ValueError("Path escapes the asset root")
    return p


def parse_name(rel_path: str) -> tuple[str | None, int | None]:
    p = Path(rel_path)
    m = NAME_RE.match(p.stem)
    if m and m.group("slug"):
        return m.group("slug"), int(m.group("num"))
    if m and not m.group("slug") and len(p.parts) > 1:  # e.g. lilia/1.webp
        return p.parent.name, int(m.group("num"))
    if len(p.parts) > 1:  # e.g. lilia/happy.webp -> slug from folder, slot unknown
        return p.parent.name, None
    return p.stem, None


def read_links_file(root: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"files": [], "rows": 0, "urls": 0}
    for cand in [root / n for n in LINKS_FILES] + [root.parent / n for n in LINKS_FILES]:
        if not cand.is_file():
            continue
        info["files"].append(str(cand.name))
        text = cand.read_text(encoding="utf-8", errors="replace")
        rows = list(csv.reader(text.splitlines())) if cand.suffix == ".csv" else [[ln] for ln in text.splitlines()]
        info["rows"] += len(rows)
        info["urls"] += sum(1 for r in rows for c in r if c.strip().startswith("http"))
    return info


def scan_root(db: Session, root: AssetRoot, index: EntityIndex) -> dict[str, Any]:
    base = Path(root.path)
    if not base.is_dir():
        raise ValueError(f"Folder not found: {root.path}")
    overrides = {o.rel_path: o for o in db.scalars(select(AssetOverride).where(AssetOverride.root_id == root.id))}
    slug_over = {s.slug: s.character_id for s in db.scalars(select(SlugOverride))}
    existing = {e.rel_path: e for e in db.scalars(select(AssetManifestEntry).where(AssetManifestEntry.root_id == root.id))}
    counts: dict[str, int] = {}
    entries: list[AssetManifestEntry] = []
    present: set[str] = set()
    for f in sorted(base.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTS:
            continue
        rel = f.relative_to(base).as_posix()
        present.add(rel)
        e = existing.get(rel) or AssetManifestEntry(root_id=root.id, rel_path=rel)
        e.ext, e.file_size, e.scanned_at = f.suffix.lower().lstrip("."), f.stat().st_size, now_iso()
        e.character_id, e.slot, e.status, e.confidence, e.match_reason, e.candidates_json = None, None, "unmatched", 0.0, "", []
        e.width = e.height = None
        try:  # validate actual readability, not just the extension
            with Image.open(f) as im:
                im.verify()
            with Image.open(f) as im:
                e.width, e.height = im.size
            e.readable = True
        except Exception as ex:  # corrupt or unsupported image
            e.readable, e.status, e.match_reason = False, "invalid", f"Unreadable image: {type(ex).__name__}"
        slug, num = parse_name(rel)
        e.slug = slug
        e.slot = num if num and 1 <= num <= 6 else None
        if e.readable:
            key = norm(slug or "")
            if key in slug_over:
                e.character_id, e.status, e.confidence, e.match_reason = slug_over[key], "matched", 1.0, "user slug mapping"
            else:
                rid = index.resolve(slug or "")
                cands = index.candidates(slug or "")
                if rid:
                    exact = norm(slug or "") in {norm(rid), norm(index.name(rid))} or norm(slug or "") in {norm(a) for a in index.entities[rid].aliases}
                    e.character_id, e.status = rid, "matched"
                    e.confidence = 0.95 if exact else 0.8
                    e.match_reason = f"'{slug}' matches {'ID/name/alias' if exact else 'unique first name'} of {index.name(rid)}"
                elif len(cands) > 1:
                    e.status, e.candidates_json = "ambiguous", cands
                    e.match_reason = f"'{slug}' matches several characters"
                else:
                    e.status, e.match_reason = "unmatched", f"No character matches '{slug}'"
            if e.status == "matched" and e.slot is None:
                e.status, e.match_reason = "ambiguous", e.match_reason + "; expression number (1–6) not found in filename"
        o = overrides.get(rel)
        if o is not None:
            if o.ignored:
                e.status, e.match_reason = "ignored", "ignored by user"
            else:
                e.character_id = o.character_id or e.character_id
                e.slot = o.slot or e.slot
                e.status, e.confidence, e.match_reason = "override", 1.0, "manual mapping"
        entries.append(e)
    # duplicates: more than one file for the same character+slot
    seen: dict[tuple[str, int], AssetManifestEntry] = {}
    for e in sorted(entries, key=lambda x: (x.status != "override", -x.confidence, x.rel_path)):
        if e.status in ("matched", "override") and e.character_id and e.slot:
            k = (e.character_id, e.slot)
            if k in seen:
                e.status, e.match_reason = "duplicate", f"Another file already provides slot {e.slot}: {seen[k].rel_path}"
            else:
                seen[k] = e
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
        db.add(e)
    for rel, e in existing.items():
        if rel not in present:
            db.delete(e)
    root.last_scan_at = now_iso()
    root.links_file_info_json = read_links_file(base)
    db.flush()
    chars = {e.character_id for e in entries if e.status in ("matched", "override")}
    missing = {}
    for cid in chars:
        have = {e.slot for e in entries if e.character_id == cid and e.status in ("matched", "override")}
        gaps = [s for s in range(1, 7) if s not in have]
        if gaps:
            missing[cid] = gaps
    return {"root_id": root.id, "files": len(entries), "by_status": counts, "characters_matched": len(chars),
            "missing_slots": missing, "links_file": root.links_file_info_json}


def portrait_map(db: Session) -> dict[str, dict[int, str]]:
    """character_id -> {slot: asset_id} for usable assets."""
    out: dict[str, dict[int, str]] = {}
    for e in db.scalars(select(AssetManifestEntry).where(AssetManifestEntry.status.in_(("matched", "override")))):
        if e.character_id and e.slot:
            out.setdefault(e.character_id, {}).setdefault(e.slot, e.id)
    return out


def resolve_expression(slots: dict[int, str], wanted: int) -> tuple[str | None, int | None, bool]:
    """Return (asset_id, slot_used, is_fallback)."""
    for s in FALLBACK_ORDER.get(wanted, [wanted, 1]):
        if s in slots:
            return slots[s], s, s != wanted
    if slots:
        s = min(slots)
        return slots[s], s, True
    return None, None, True


def file_for(db: Session, asset_id: str) -> Path:
    e = db.get(AssetManifestEntry, asset_id)
    if e is None or not e.readable:
        raise FileNotFoundError(asset_id)
    root = db.get(AssetRoot, e.root_id)
    if root is None:
        raise FileNotFoundError(asset_id)
    p = safe_join(Path(root.path), e.rel_path)
    if not p.is_file():
        raise FileNotFoundError(asset_id)
    return p


def derivative(src: Path, cache_dir: Path, key: str, variant: str) -> Path:
    w, h = VARIANTS[variant]
    out = cache_dir / "thumbs" / f"{key}_{variant}_{int(src.stat().st_mtime)}.webp"
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        W, H = im.size
        if variant == "thumb":  # face-biased square crop from the upper-centre of the image
            side = int(min(W, H) * 0.62)
            cx, top = int(W * 0.46), int(H * 0.02)
            box = (max(0, cx - side // 2), top, min(W, cx - side // 2 + side), min(H, top + side))
        else:  # 3:4 portrait crop centred slightly left of middle
            cw = min(W, int(H * w / h))
            cx = int(W * 0.46)
            left = max(0, min(W - cw, cx - cw // 2))
            box = (left, 0, left + cw, H)
        im.crop(box).resize((w, h), Image.LANCZOS).save(out, "WEBP", quality=82)
    return out


def discover_image_folders(project_root: Path) -> list[dict[str, Any]]:
    found = []
    for d in [project_root, *[p for p in project_root.iterdir() if p.is_dir()]]:
        if d.name in ("data", "app", ".venv", "node_modules") or d.name.startswith("."):
            continue
        n = sum(1 for f in d.rglob("*") if f.suffix.lower() in IMAGE_EXTS) if d != project_root else \
            sum(1 for f in d.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        if n >= 6:
            found.append({"path": str(d), "name": d.name, "image_count": n})
    return found
