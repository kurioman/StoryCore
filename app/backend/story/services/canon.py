"""Structured canon facts: kinship, family branches and recurring gatherings (classes, councils...), with provenance.

These are facts about who people *are* (aunt, sister, teacher, member), never how they *feel*: kinship does not imply
affection, and nothing here touches the story's emotional relationship scores or the protagonist's discoveries.

Sources, in order:
* the pack's ``facts`` and ``gatherings`` (``pack.json``, see LOREPACK_FORMAT.md);
* the owner's in-app corrections (setting ``canon_facts``, scoped to a world slug), added on top;
* lore: the pack's ``characters/relationships.json`` kinship entries (read-only, via ``relationships.lore_relationships``).

Every name is verified against the imported lore before it is linked to a canonical id. A name that is not in lore but
matches exactly one character (of the same year, when known) by spelling is linked as a *probable spelling variant* and
flagged for confirmation — never added as a resolving alias. Anything else stays unresolved.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LoreEntity, World
from .entities import EntityIndex, norm

KIND_LABEL = {"aunt_of": "aunt of", "sibling_of": "sibling of", "parent_of": "parent of", "spouse_of": "spouse of",
              "family_branch": "family branch", "teaches": "teaches", "class_roster": "class"}
KIN_TEXT = {"aunt_of": "{s} is the aunt of {o}", "sibling_of": "{s} and {o} are siblings",
            "parent_of": "{s} is the parent of {o}", "spouse_of": "{s} and {o} are married"}
YEAR_WORD = {1: "first", 2: "second", 3: "third", 4: "fourth"}


def _lore_chars(db: Session, world_id: str | None) -> dict[str, LoreEntity]:
    if not world_id:
        return {}
    return {e.entity_id: e for e in db.scalars(select(LoreEntity).where(LoreEntity.world_id == world_id,
                                                                        LoreEntity.category == "character"))}


def verify_name(ref: dict[str, Any], chars: dict[str, LoreEntity], index: EntityIndex, *,
                year: int | None = None) -> dict[str, Any]:
    """Link an owner-given name to a canonical id with an explicit status:
    ``verified`` (the name or its expected id resolves in lore), ``probable_variant`` (not in lore; one lore character
    of the same year differs by a small spelling change — needs the owner's confirmation) or ``unresolved``."""
    name, want = str(ref.get("name") or ""), ref.get("id")
    cid = index.resolve(name)
    if cid and cid in chars:
        return {"name": name, "character_id": cid, "canonical_name": chars[cid].name, "status": "verified"}
    if want in chars and norm(chars[want].name).split(" ")[0] == norm(name):
        return {"name": name, "character_id": want, "canonical_name": chars[want].name, "status": "verified"}
    # spelling variant: one character (same year when known) whose first name is one edit-ish away
    pool = [c for c in chars.values() if year is None or (c.data_json or {}).get("year") in (None, year)]
    close = [c for c in pool if difflib.SequenceMatcher(None, norm(name), norm(c.name).split(" ")[0]).ratio() >= 0.75
             and norm(name) != norm(c.name).split(" ")[0]]
    if len(close) == 1 and (want is None or close[0].entity_id == want):
        c = close[0]
        return {"name": name, "character_id": c.entity_id, "canonical_name": c.name, "status": "probable_variant",
                "review": f"“{name}” is not in the lore; the lore has {c.name} (same year/department). Treated as the same "
                          f"person until you confirm or correct it."}
    return {"name": name, "character_id": None, "canonical_name": None, "status": "unresolved",
            "review": f"“{name}” could not be matched to a lore character; it is kept as written and not linked."}


def _ref(cid: Any, chars: dict[str, LoreEntity]) -> dict[str, Any]:
    """A pack character id as the {name, id} reference the verification expects."""
    cid = str(cid or "")
    return {"name": chars[cid].name if cid in chars else cid, "id": cid}


def pack_entries(pack: dict[str, Any], chars: dict[str, LoreEntity]) -> list[dict[str, Any]]:
    """The pack's ``facts`` and ``gatherings`` in the internal fact format (ids turned into verifiable references)."""
    out: list[dict[str, Any]] = []
    for f in pack.get("facts") or []:
        e: dict[str, Any] = {"kind": f["kind"], "subject": _ref(f["subject"], chars), "note": f.get("note") or "",
                             "_by": "pack.json"}
        if f.get("object"):
            e["object"] = _ref(f["object"], chars)
        for k in ("family", "branch", "text"):
            if f.get(k):
                e[k] = f[k]
        out.append(e)
    for g in pack.get("gatherings") or []:
        out.append({"kind": "class_roster", "class_id": g["id"], "subject_name": g["name"], "year": None,
                    "gathering_kind": g["kind"], "keywords": g["keywords"], "note": g["note"], "_by": "pack.json",
                    "teacher": _ref(g["leader"], chars) if g.get("leader") else None,
                    "students": [_ref(m, chars) for m in g["members"]]})
    return out


def facts(db: Session, world_id: str | None, index: EntityIndex) -> dict[str, Any]:
    """Verified canon for one world: {"kinship": [...], "branches": [...], "rosters": [...], "open_questions": [...]}."""
    from . import settings_service, world_pack

    out: dict[str, Any] = {"kinship": [], "branches": [], "rosters": [], "open_questions": []}
    chars = _lore_chars(db, world_id)
    if not chars:
        return out
    world = db.get(World, world_id)
    slug = world.slug if world else None
    seen_q: set[str] = set()

    def ask(v: dict[str, Any]) -> None:
        if v["status"] != "verified" and v["name"] not in seen_q:
            seen_q.add(v["name"])
            out["open_questions"].append({"name": v["name"], "character_id": v["character_id"], "status": v["status"],
                                          "message": v["review"]})

    entries = pack_entries(world_pack.of(db, world_id), chars)
    entries += [f for f in settings_service.get(db, "canon_facts") or []
                if isinstance(f, dict) and (not f.get("world") or f["world"] == slug)]
    for f in entries:
        kind, by = f.get("kind"), f.get("_by") or "owner-confirmed"
        if kind in KIN_TEXT:
            s, o = verify_name(f["subject"], chars, index), verify_name(f["object"], chars, index)
            ask(s), ask(o)
            if s["character_id"] and o["character_id"]:
                text = KIN_TEXT[kind].format(s=s["canonical_name"], o=o["canonical_name"])
                out["kinship"].append({"kind": kind, "subject_id": s["character_id"], "object_id": o["character_id"],
                                       "text": text + (f" ({f['note']})" if f.get("note") else ""),
                                       "source": by, "status": _worst(s, o)})
        elif kind == "other":
            s = verify_name(f["subject"], chars, index)
            o = verify_name(f["object"], chars, index) if f.get("object") else None
            ask(s)
            if o:
                ask(o)
            if s["character_id"]:
                out["kinship"].append({"kind": "other", "subject_id": s["character_id"],
                                       "object_id": o["character_id"] if o else None, "text": f.get("text") or "",
                                       "source": by, "status": _worst(s, *([o] if o else []))})
        elif kind == "family_branch":
            s = verify_name(f["subject"], chars, index)
            ask(s)
            if s["character_id"]:
                out["branches"].append({"character_id": s["character_id"], "family": f.get("family") or "",
                                        "branch": f.get("branch") or "", "note": f.get("note") or "", "source": by,
                                        "status": s["status"]})
        elif kind == "class_roster":
            teacher = verify_name(f["teacher"], chars, index) if f.get("teacher") else None
            if teacher:
                ask(teacher)
            students = []
            for st in f.get("students") or []:
                v = verify_name(st, chars, index, year=f.get("year"))
                ask(v)
                students.append(v)
            out["rosters"].append({"class_id": f.get("class_id"), "subject": f.get("subject_name") or "", "year": f.get("year"),
                                   "kind": f.get("gathering_kind") or "class",
                                   "keywords": list(f.get("keywords") or []), "teacher": teacher, "students": students,
                                   "note": f.get("note") or "", "source": by})
    # lore kinship: sisters and other relatives named in the pack's relationship list (read-only background)
    from .relationships import lore_relationships
    pairs: set[tuple[str, frozenset[str]]] = set()  # the pack states one tie in several places (list + both characters)
    for r in lore_relationships(db, world_id):
        t = r["type"].lower()
        kind = "sibling" if ("sister" in t or "brother" in t or "sibling" in t) else "relative" if "relative" in t else None
        if kind is None or (kind, frozenset((r["source_id"], r["target_id"]))) in pairs:
            continue
        pairs.add((kind, frozenset((r["source_id"], r["target_id"]))))
        if "sister" in t or "brother" in t or "sibling" in t:
            older = "older" in t.split(";")[0].split(" and ")[0] if " and " in t else False
            out["kinship"].append({"kind": "sibling_of", "subject_id": r["source_id"], "object_id": r["target_id"],
                                   "text": f"{r['source_name']} and {r['target_name']} are sisters"
                                           + (f" ({r['source_name']} is the older)" if older else ""),
                                   "source": f"lore: {r['lore_source']}", "status": "verified"})
        elif "relative" in t:
            out["kinship"].append({"kind": "relative_of", "subject_id": r["source_id"], "object_id": r["target_id"],
                                   "text": f"{r['source_name']} and {r['target_name']} are relatives",
                                   "source": f"lore: {r['lore_source']}", "status": "verified"})
    return out


def _worst(*vs: dict[str, Any]) -> str:
    order = ["verified", "probable_variant", "unresolved"]
    return max((v["status"] for v in vs), key=order.index)


def label(r: dict[str, Any]) -> str:
    """A gathering's display name: "first-year Magic" for a roster with a year, otherwise its name."""
    year = YEAR_WORD.get(r.get("year"), "")
    return f"{year}-year {r['subject']}" if year else r["subject"]


def words(r: dict[str, Any]) -> dict[str, str]:
    """Wording for a gathering: a class has a teacher and students; any other gathering a leader and members."""
    if (r.get("kind") or "class") == "class":
        return {"noun": "class", "leader": "teacher", "members": "usual students", "leads": "Teaches", "joins": "Attends",
                "leads_here": "teaches this", "joins_here": "usually attends this"}
    return {"noun": r.get("kind") or "gathering", "leader": "leader", "members": "usual members", "leads": "Leads",
            "joins": "Takes part in", "leads_here": "leads this", "joins_here": "usually takes part in this"}


def siblings(canon: dict[str, Any], cid: str) -> list[str]:
    return [k["object_id"] if k["subject_id"] == cid else k["subject_id"] for k in canon["kinship"]
            if k["kind"] == "sibling_of" and cid in (k["subject_id"], k["object_id"])]


def for_character(canon: dict[str, Any], cid: str, index: EntityIndex) -> list[dict[str, Any]]:
    """Canon lines about one character for the character view (kinship, branch, classes), with provenance."""
    out = [{"type": k["kind"], "text": k["text"], "source": k["source"], "status": k["status"]}
           for k in canon["kinship"] if cid in (k["subject_id"], k["object_id"])]
    for b in canon["branches"]:
        if b["character_id"] == cid:
            out.append({"type": "family_branch", "text": _branch_text(b, index), "source": b["source"], "status": b["status"]})
    for r in canon["rosters"]:
        w = words(r)
        if r["teacher"] and r["teacher"]["character_id"] == cid:
            out.append({"type": "teaches", "text": f"{w['leads']} {label(r)}" + (f" — {r['note']}" if r["note"] else ""),
                        "source": r["source"], "status": r["teacher"]["status"]})
        for st in r["students"]:
            if st["character_id"] == cid:
                out.append({"type": "class_roster", "text": f"{w['joins']} {label(r)}" + (f" (listed as “{st['name']}”)" if st["status"] != "verified" else ""),
                            "source": r["source"], "status": st["status"]})
    return out


def detect_class(text: str, canon: dict[str, Any], present: list[str] | None = None) -> dict[str, Any] | None:
    """The class roster whose subject the scene is clearly about (location/time/recent text), or, in a room with no such
    word ("Room 301"), the class whose teacher is present with one of its students. Otherwise None."""
    t = norm(text)
    best, hits = None, 0
    for r in canon["rosters"]:
        n = sum(1 for k in r["keywords"] if re.search(rf"\b{re.escape(norm(k))}\b", t))
        if n > hits:
            best, hits = r, n
    if hits:
        return best
    here = set(present or [])
    return next((r for r in canon["rosters"] if (r["teacher"] or {}).get("character_id") in here
                 and here & {s["character_id"] for s in r["students"]}), None)


def _branch_text(b: dict[str, Any], index: EntityIndex) -> str:
    text = f"{index.name(b['character_id'])}: {b['family']} family" + (f", {b['branch']}" if b.get("branch") else "")
    return text + (f" ({b['note']})" if b.get("note") else "")


def _people(r: dict[str, Any]) -> str:
    return ", ".join(s["canonical_name"] or s["name"] for s in r["students"] if s["character_id"] or s["name"])


def render_block(canon: dict[str, Any], index: EntityIndex, focus: set[str], active_class: dict[str, Any] | None) -> str:
    """Compact narrator block: kinship of characters in focus, the gathering (class, council...) the scene is
    about, and a one-line summary of the other gatherings. ≈ 60-160 tokens."""
    lines: list[str] = []
    kin = [k for k in canon["kinship"] if k["subject_id"] in focus or k["object_id"] in focus]
    if kin:
        aunts = {}
        for k in kin:
            if k["kind"] == "aunt_of":
                aunts.setdefault(k["subject_id"], []).append(index.name(k["object_id"]))
        for a, nieces in aunts.items():
            lines.append(f"- {index.name(a)} is the aunt of {' and '.join(nieces)} (not their mother).")
        for k in kin:
            if k["kind"] != "aunt_of":
                lines.append(f"- {k['text']}.")
    for b in canon["branches"]:
        if b["character_id"] in focus or any(x["character_id"] in focus for x in canon["branches"]):
            lines.append(f"- {_branch_text(b, index)}.")
    if active_class:
        r, w = active_class, words(active_class)
        t = r["teacher"]["canonical_name"] if r["teacher"] and r["teacher"]["character_id"] else "—"
        lines.append(f"- This scene's {w['noun']} — {label(r)}: {w['leader']} {t}; {w['members']} {_people(r)}."
                     + (f" {r['note']}" if r["note"] else ""))
    others = [r for r in canon["rosters"] if r is not active_class]
    if others:
        noun = "classes" if all((r.get("kind") or "class") == "class" for r in others) else "recurring gatherings"
        lines.append(f"- Other {noun}: " + "; ".join(
            f"{label(r)} ({words(r)['leader']} {r['teacher']['canonical_name'] if r['teacher'] and r['teacher']['character_id'] else '—'}: "
            f"{_people(r)})" for r in others) + ".")
    if not lines:
        return ""
    return ("Kinship never implies affection; the protagonist may not know these people yet.\n"
            + "\n".join(dict.fromkeys(lines)))
