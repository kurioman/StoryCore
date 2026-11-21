"""Canonical posts and closed groups from imported lore, plus owner-confirmed role assignments (v1.4).

The narrator may invent minor people, but never a second Headmaster, a new god or a replacement head of department when
lore already names one (observed in the owner's story: "Professor Aldric"). This module

* derives a registry from data the lore import already stores — structured fields first (``departments[].head_professor_id``,
  ``academy.governance.headmaster_id``), then short office titles in a character's ``role`` / ``social_status`` only when
  exactly one character holds them (anything else is reported as ambiguous, never locked);
* merges the pack's posts (``pack.json`` → ``posts``), then the owner's in-app corrections (setting
  ``role_assignments``, scoped to a world slug) on top; a pack or owner entry wins over lore and the difference is
  recorded;
* adds the pack's closed groups (``pack.json`` → ``closed_groups``: listed members and/or every character of the
  listed types);
* renders a concise block for every narrator context (critical: never trimmed); and
* checks a finished reply for invented holders of locked posts / unknown authorities — a notice only, the reply text is
  never changed.

Full lore access for the AI is not player knowledge: nothing here touches discoveries (``character_discoveries``).
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LoreEntity, World
from . import settings_service, world_pack
from .entities import EntityIndex, norm

# Pack posts come from pack.json; the owner's in-app corrections live in the setting ``role_assignments`` (default: none).
OFFICE = re.compile(r"\b(president|vice president|headmaster|headmistress|master|commander|captain|chancellor|emperor|"
                    r"empress|princess|prince|pope|archbishop|grand master)\b", re.I)
NOT_OFFICE = re.compile(r"^(member|daughter|son|sister|brother|adopted|representative)\b", re.I)
GROUP_OF = re.compile(r"^one of the (two|three|four|five|six|seven|eight|nine|ten|twelve) (.+)$", re.I)
KNOWN_AS = re.compile(r"\bknown as (the .+)$", re.I)
NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}


def _segments(v: Any) -> list[str]:
    return [p.strip() for p in str(v or "").split(";") if p.strip()]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", norm(s)).strip("_")


def build_registry(db: Session, world_id: str | None, index: EntityIndex) -> dict[str, Any]:
    """{"roles": [...], "groups": [...], "ambiguous": [...], "conflicts": [...]} for one world (empty without a world)."""
    out: dict[str, Any] = {"roles": [], "groups": [], "ambiguous": [], "conflicts": [], "school": False}
    if not world_id:
        return out
    world = db.get(World, world_id)
    rows = list(db.scalars(select(LoreEntity).where(LoreEntity.world_id == world_id)))
    chars = {r.entity_id: r for r in rows if r.category == "character"}
    roles: dict[str, dict[str, Any]] = {}

    def add(role_id: str, title: str, cid: str, source: str, *, aliases=(), subjects=(), locked=True) -> None:
        if cid not in chars or role_id in roles:
            return
        roles[role_id] = {"role_id": role_id, "title": title, "character_id": cid, "character_name": chars[cid].name,
                          "aliases": list(dict.fromkeys(a for a in aliases if a)), "subjects": list(subjects),
                          "locked": locked, "mandatory": False, "source": source, "note": ""}

    for r in rows:  # 1. structured lore fields
        d = r.data_json or {}
        if r.category == "department" and d.get("head_professor_id"):
            short = re.sub(r"\s+department$", "", r.name, flags=re.I)
            add(f"head_professor:{r.entity_id}", f"Head Professor of the {r.name}", d["head_professor_id"],
                f"lore: {r.file} departments[{r.entity_id}].head_professor_id",
                aliases=[f"head of the {r.name}", f"{short} professor", f"{short} classes"], subjects=d.get("focus") or [])
        if r.category == "academy":
            gov = d.get("governance") or {}
            if gov.get("headmaster_id"):
                add("headmaster", f"Headmaster of {r.name}", gov["headmaster_id"], f"lore: {r.file} governance.headmaster_id",
                    aliases=["headmaster", "headmistress"])
            sc = gov.get("student_council") or {}
            members = [m for m in sc.get("known_members") or [] if m in chars]
            if members:
                out["groups"].append({"group_id": "student_council", "title": "Student Council (known members)",
                                      "members": members, "closed": False, "source": f"lore: {r.file} governance.student_council"})
    holders = {rl["character_id"] for rl in roles.values()}
    titles: dict[str, dict[str, Any]] = {}  # normalised title -> {"title": as written, "cids": [...]}
    groups: dict[str, dict[str, Any]] = {}
    for cid, c in chars.items():  # 2. short office titles in prose fields, one holder only
        d = c.data_json or {}
        for seg in _segments(d.get("role")) + _segments(d.get("social_status")):
            g = GROUP_OF.match(seg)
            if g:
                key = _slug(f"{g.group(1)} {g.group(2)}")  # "one of the Four Celestials" -> four_celestials
                groups.setdefault(key, {"group_id": key, "title": f"the {g.group(1).capitalize()} {g.group(2)}",
                                        "size": NUMBERS[g.group(1).lower()], "members": [], "source": "lore: character role"})
                groups[key]["members"].append(cid)
                continue
            k = KNOWN_AS.search(seg)
            title = k.group(1) if k else seg
            if NOT_OFFICE.match(title) or len(title.split()) > 6 or not (k or OFFICE.search(title)):
                continue
            if cid in holders and re.search(r"head professor|headmaster|headmistress", title, re.I):
                continue  # already covered by the structured field
            titles.setdefault(norm(title), {"title": title[0].upper() + title[1:], "cids": []})["cids"].append(cid)
    for t in titles.values():
        if len(t["cids"]) == 1:
            add(f"post:{_slug(t['title'])}", t["title"], t["cids"][0], "lore: character role / social status")
        else:
            out["ambiguous"].append({"title": t["title"], "characters": t["cids"], "reason": "held by more than one character in lore"})
    pack = world_pack.of(db, world_id)
    out["school"] = world_pack.has_module(pack, "school")
    for pg in pack.get("closed_groups") or []:  # the pack's closed groups: listed members + every character of the types
        members = [m for m in pg["members"] if m in chars]
        members += [cid for cid, c in chars.items() if c.entity_type in pg["types"] and cid not in members]
        if members:
            groups[pg["id"]] = {"group_id": pg["id"], "title": pg["title"], "size": None, "members": members,
                                "source": "pack.json closed_groups"}
    for g in groups.values():
        complete = g["size"] is None or len(g["members"]) == g["size"]
        g["closed"] = complete
        if not complete:
            out["ambiguous"].append({"title": g["title"], "characters": g["members"],
                                     "reason": f"lore names {len(g['members'])} of {g['size']} members"})
        out["groups"].append({k: v for k, v in g.items() if k != "size"})
    # 3. the pack's posts, then the owner's in-app corrections, win over lore; differences are recorded, never hidden
    slug = world.slug if world else None
    assignments = [{"role_id": p["id"], "character_id": p["character"], "title": p["title"], "aliases": p["aliases"],
                    "note": p["note"], "mandatory": p["mandatory"], "_by": "pack.json"} for p in pack.get("posts") or []]
    assignments += [a for a in settings_service.get(db, "role_assignments") or []
                    if isinstance(a, dict) and (not a.get("world") or a["world"] == slug)]
    for a in assignments:
        by = a.get("_by") or "owner-confirmed"
        who = "the pack" if by == "pack.json" else "the owner"
        cid, rid = a.get("character_id"), a.get("role_id")
        if not rid or cid not in chars:
            continue
        prev = roles.get(rid)
        note = a.get("note") or ""
        lore_desc = "" if _lore_states_post(chars[cid], a) else _lore_description(chars[cid])
        if prev and prev["character_id"] != cid:
            out["conflicts"].append({"role_id": rid, "lore": prev["character_id"], "owner": cid,
                                     "message": f"{'Lore' if prev['source'].startswith('lore') else 'The pack'} names "
                                                f"{prev['character_name']} for {prev['title']}; {who} assigned {chars[cid].name}."})
        elif not prev and lore_desc and not note:  # phase 2: a note written by the author already explains the post
            note = " ".join(x for x in [note, f"(Lore describes {chars[cid].name} as {lore_desc}; this post is {who}'s assignment.)"] if x)
        roles[rid] = {**(prev or {}), "role_id": rid, "title": a.get("title") or (prev or {}).get("title") or rid,
                      "character_id": cid, "character_name": chars[cid].name,
                      "aliases": list(dict.fromkeys([*((prev or {}).get("aliases") or []), *(a.get("aliases") or [])])),
                      "subjects": (prev or {}).get("subjects") or [], "locked": True, "mandatory": bool(a.get("mandatory")),
                      "source": by + (" + " + prev["source"] if prev and prev["character_id"] == cid else ""),
                      "note": note}
    out["roles"] = sorted(roles.values(), key=lambda r: (not r["mandatory"], r["role_id"] != "headmaster", r["title"]))
    return out


def _lore_states_post(c: LoreEntity, a: dict[str, Any]) -> bool:
    """True when the character's lore type or title already names the post (type "Demon King" for the Demon King post), so a
    note saying the post comes from the pack or the owner would only repeat it."""
    kind = norm(f"{c.entity_type or ''} {(c.data_json or {}).get('title') or ''}".strip())
    names = [a.get("title") or "", *(a.get("aliases") or [])]
    return bool(kind) and any(n and n in kind for n in (re.sub(r"^the ", "", norm(x)) for x in names))


def _lore_description(c: LoreEntity) -> str:
    """'a third-year theology department student' when the character is not faculty in lore (owner assignments of a post
    to such a character are honoured but labelled)."""
    d = c.data_json or {}
    if "faculty" in (c.entity_type or ""):
        return ""
    year = {1: "first", 2: "second", 3: "third", 4: "fourth"}.get(d.get("year"), "")
    dept = str(d.get("department_id") or "").replace("_", " ")
    return " ".join(x for x in ["a", f"{year}-year" if year else "", dept, c.entity_type or "character"] if x)


def render_block(registry: dict[str, Any], index: EntityIndex, present: list[str] | None = None) -> str:
    """Concise narrator block: established posts, closed groups, other named characters, rules (≈ 300-400 tokens)."""
    if not registry["roles"] and not registry["groups"]:
        return ""
    first = registry["roles"][0]["title"] if registry["roles"] else "a listed post"
    example = "the Headmaster" if registry.get("school") else f"the {re.sub(r'^the ', '', first, flags=re.I)}"
    # v0.6 (phase 9): same rules in fewer words (this block is sent with every request)
    lines = [f"Established posts (always held by the character listed, e.g. {example}; the protagonist may not know them "
             "yet: name them once introduced or already met):"]
    for r in registry["roles"]:
        lines.append(f"- {r['title']}: {r['character_name']}" + (f" ({r['note']})" if r["note"] else ""))
    closed = [g for g in registry["groups"] if g["closed"]]
    if closed:
        lines.append("Closed groups (never add members): " + "; ".join(
            f"{g['title']} = {', '.join(index.name(m) for m in g['members'])}" for g in closed))
    posted = {r["character_id"] for r in registry["roles"]} | {m for g in closed for m in g["members"]}
    others = [e.name for e in index.entities.values() if e.category == "character" and not e.local and e.id not in posted]
    if others:
        lines.append("Other established characters (prefer them over new named ones): " + ", ".join(sorted(others)))
    lines.append("Never give a post to anyone else, even when its holder is absent (keep them offscreen or away). Use "
                 "canonical names (aliases are fine). New minor characters "
                 + ("(students, staff, townsfolk)" if registry.get("school") else "(townsfolk, staff, passers-by)")
                 + " are fine if they hold no post and contradict no lore, and never share a name (or first name) with an "
                   "established character. No new gods or celestial beings.")
    return "\n".join(lines)


AUTHORITY = re.compile(r"\b(Headmaster|Headmistress|Professor|Instructor|Dean|Principal|Celestial|Goddess|God)\s+"
                       r"([A-Z][a-zà-ÿ'’]+(?:\s+[A-Z][a-zà-ÿ'’]+)?)")


# v0.6 (test report "30 tours", B4): the narrator invented "Emperor Alaric" twice while the pack's registry names the
# Empress Diana, and nothing was reported. Any "<office title> <Name>" whose office is a locked post of the registry is
# now checked against the post's holder. English and French titles; the feminine form is the same office.
OFFICE_WORDS = {"emperor": "emperor", "empress": "emperor", "empereur": "emperor", "imperatrice": "emperor",
                "king": "king", "queen": "king", "roi": "king", "reine": "king",
                "commander": "commander", "commandant": "commander", "commandante": "commander",
                "chancellor": "chancellor", "chancelier": "chancellor", "chanceliere": "chancellor",
                "pope": "pope", "pape": "pope", "archbishop": "archbishop", "archeveque": "archbishop",
                "chieftain": "chieftain", "chef": "chieftain"}
OFFICE_AUTHORITY = re.compile(
    r"(?i:\b(?:([a-zà-ÿ0-9]+)\s+)?(emperor|empress|empereur|impératrice|imperatrice|king|queen|roi|reine|commander|"
    r"commandant|commandante|chancellor|chancelier|chancelière|pope|pape|archbishop|archevêque|chieftain))\s+"
    r"([A-ZÀ-Ý][a-zà-ÿ'’]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ'’]+)?)")
TITLE_FILLER = {"the", "a", "an", "her", "his", "their", "our", "of", "le", "la", "l", "les", "du", "de", "sa", "son",
                "notre", "votre", "title"}


def _office_entries(registry: dict[str, Any]) -> list[tuple[str, str | None, dict[str, Any]]]:
    """(office, word just before it or None, post) for every office word in a locked post's title and aliases:
    "the Emperor" -> ("emperor", None), "Dragon Emperor" -> ("emperor", "dragon")."""
    out = []
    for r in registry["roles"]:
        if not r.get("locked", True):
            continue
        for phrase in [r["title"], *r["aliases"]]:
            words = re.findall(r"[a-z0-9]+", norm(phrase))
            for i, w in enumerate(words):
                if w in OFFICE_WORDS:
                    before = words[i - 1] if i and words[i - 1] not in TITLE_FILLER else None
                    out.append((OFFICE_WORDS[w], before, r))
    return out


def office_conflicts(text: str, registry: dict[str, Any], index: EntityIndex, ignore: set[str]) -> list[dict[str, Any]]:
    """B4: "<title> <Name>" for a locked office held by someone else (or by several people, none of them that name)."""
    entries = _office_entries(registry)
    out: list[dict[str, Any]] = []
    if not entries:
        return out
    for m in OFFICE_AUTHORITY.finditer(text or ""):
        before = norm(m.group(1) or "")
        office = OFFICE_WORDS[norm(m.group(2))]
        name = re.sub(r"['’]s$", "", m.group(3))
        first = name.split()[0]
        if norm(name) in ignore or norm(first) in ignore or norm(first) in OFFICE_WORDS:
            continue
        cands = [(mod, r) for o, mod, r in entries if o == office]
        exact = [r for mod, r in cands if mod and mod == before]  # "Dragon Emperor Azra": the Dragon Emperor's post
        posts = exact or [r for mod, r in cands if mod is None]
        posts = list({r["role_id"]: r for r in posts}.values())
        if not posts:
            continue
        cid = index.resolve(name) or index.resolve(first)
        if cid in {r["character_id"] for r in posts}:
            continue
        said = m.group(0).strip()
        if m.group(1) and not exact:
            said = said[len(m.group(1)):].strip()
        holders = ", ".join(f"{r['character_name']} ({r['title']})" for r in posts)
        out.append({"kind": "conflict", "text": said, "role_id": posts[0]["role_id"], "holder": posts[0]["character_id"],
                    "message": (f"“{said}” — the {posts[0]['title']} is {posts[0]['character_name']} (lore)."
                                if len(posts) == 1 else f"“{said}” is none of the lore's holders of this title: {holders}.")})
    return out


def detect_conflicts(text: str, registry: dict[str, Any], index: EntityIndex, ignore: set[str] | None = None) -> list[dict[str, Any]]:
    """Title + name pairs in a reply that contradict the registry: a different person in a locked post (``conflict``) or
    an authority nobody established (``unknown_authority``). Deterministic, no model call; notices only."""
    out: list[dict[str, Any]] = []
    if not registry["roles"] and not registry["groups"]:
        return out
    ignore = {norm(x) for x in (ignore or set()) if x}
    by_title = {}
    for r in registry["roles"]:
        for a in [r["title"], *r["aliases"]]:
            for word in ("headmaster", "headmistress", "principal"):
                if word in norm(a):
                    by_title[word] = r
    groups = {g["group_id"]: g for g in registry["groups"] if g["closed"]}
    seen: set[str] = set()
    for m in AUTHORITY.finditer(text or ""):
        title, name = m.group(1), re.sub(r"['’]s$", "", m.group(2))
        first, said = name.split()[0], f"{title} {name}"
        # "Professor Elena Caldwin", "Headmaster Emily" — try the full name, then the first word
        cid = index.resolve(name) or index.resolve(first)
        known = cid is not None or bool(index.candidates(name) or index.candidates(first))  # e.g. the shared "Caldwin"
        key = f"{title}|{name}"
        if key in seen or norm(name) in ignore or norm(first) in ignore:
            continue
        seen.add(key)
        holder = by_title.get(title.lower())
        if holder and cid != holder["character_id"]:
            out.append({"kind": "conflict", "text": said, "role_id": holder["role_id"], "holder": holder["character_id"],
                        "message": f"“{said}” — the {holder['title']} is {holder['character_name']} (lore)."})
        elif title.lower() in ("god", "goddess") and not known and "deities" in groups:
            out.append({"kind": "conflict", "text": said, "role_id": "deities", "holder": None,
                        "message": f"“{said}” is not one of the established deities ({', '.join(index.name(x) for x in groups['deities']['members'])})."})
        elif title.lower() == "celestial" and not known:
            g = next((g for g in groups.values() if "celestial" in g["title"].lower()), None)
            if g:
                out.append({"kind": "conflict", "text": said, "role_id": g["group_id"], "holder": None,
                            "message": f"“{said}” is not one of {g['title']} ({', '.join(index.name(x) for x in g['members'])})."})
        elif not known and title.lower() in ("professor", "instructor", "dean"):
            posts = [r for r in registry["roles"] if r["role_id"].startswith(("head_professor:", "instructor:"))]
            known = ", ".join(f"{r['character_name']} ({r['title']})" for r in posts)
            out.append({"kind": "unknown_authority", "text": said, "role_id": None, "holder": None,
                        "message": f"“{said}” is not an established character" + (f"; lore teachers: {known}." if known else ".")})
    taken = {o["text"] for o in out}
    for c in office_conflicts(text, registry, index, ignore):
        if c["text"] not in taken:
            taken.add(c["text"])
            out.append(c)
    return out[:5]
