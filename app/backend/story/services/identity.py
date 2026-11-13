"""Contextual identity resolution (v1.5): canonical ids for people the text refers to by post or kinship.

``EntityIndex`` resolves names and verified aliases. This module adds two narrow, deterministic kinds of reference that
the owner's long story needed and that names alone miss:

* **unique posts** from the role registry — "the Headmaster" is the post's holder inside its own academy (e.g. Lumencia's
  pack), "the head of the Magic Department" is that department's head. Generic or foreign uses are rejected: "a headmaster", "the former headmaster", "the
  headmaster of Duskmoor", "his old headmaster".
* **kinship** from canon facts — "Lucia's sister" is Serena (only when the sibling is unique), "Serena's aunt" Elena.

Results carry the phrase and the paragraph, so callers can treat them as evidence. Ambiguity returns nothing — a wrong
portrait or relationship is worse than none. Pronouns ("her sister") are deliberately not resolved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .entities import EntityIndex, norm

GENERIC_BEFORE = re.compile(r"\b(a|an|any|another|other|former|previous|late|old|ex|new|some|every|their|his|your|my|"
                            r"our|its)\s+$", re.I)
FOREIGN_AFTER = re.compile(r"^\s+of\s+(?:the\s+)?([A-Z][\w'’-]+)")
KIN_WORDS = {"sister": "sibling", "sisters": "sibling", "brother": "sibling", "sibling": "sibling", "aunt": "aunt",
             "niece": "niece", "nieces": "niece"}
POSSESSIVE = re.compile(r"\b([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)?)['’]s\s+(?:(?:younger|older|little|big|elder|twin)\s+)?"
                        r"(sister|brother|sibling|aunt|niece)\b")


@dataclass
class Ref:
    character_id: str
    via: str  # "role" | "kinship"
    phrase: str
    paragraph: int

    def to_dict(self) -> dict[str, Any]:
        return {"character_id": self.character_id, "via": self.via, "phrase": self.phrase, "paragraph": self.paragraph}


def role_phrases(registry: dict[str, Any]) -> dict[str, str]:
    """Phrase (lower case) -> holder id, for posts with one locked holder. Only phrases that name an office ("head",
    "headmaster", "principal", the post title) — never subject words like "magic classes"."""
    out: dict[str, str] = {}
    for r in registry.get("roles") or []:
        if not r.get("locked"):
            continue
        for a in [r["title"], *(r.get("aliases") or [])]:
            a = norm(a)
            if re.search(r"\b(head|headmaster|headmistress|principal|president|commander|master)\b", a) and len(a) >= 5:
                out.setdefault(a, r["character_id"])
    return out


def _institution_names(registry: dict[str, Any]) -> set[str]:
    names = set()
    for r in registry.get("roles") or []:
        m = re.search(r"\bof (?:the )?(.+)$", r["title"])
        if m:
            names.add(norm(m.group(1)).split(" ")[0])
    return names


def contextual_refs(text: str, index: EntityIndex, registry: dict[str, Any] | None, canon: dict[str, Any] | None,
                    in_scene: set[str] | None = None) -> list[Ref]:
    """References in ``text`` (paragraph-indexed) resolved through posts and kinship. ``in_scene``: ids already present
    or named in this turn (kinship is only resolved for someone in it, e.g. Lucia's sister while Lucia is there)."""
    refs: list[Ref] = []
    paras = [p for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    phrases = role_phrases(registry or {})
    ours = _institution_names(registry or {})
    keys = sorted(phrases, key=len, reverse=True)
    pat = re.compile(r"\b(" + "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in keys) + r")\b", re.I) if keys else None
    for i, p in enumerate(paras):
        if pat:
            for m in pat.finditer(p):
                before, after = p[max(0, m.start() - 24):m.start()], p[m.end():m.end() + 40]
                if GENERIC_BEFORE.search(before):
                    continue
                f = FOREIGN_AFTER.match(after)
                if f and norm(f.group(1)).split(" ")[0] not in ours:
                    continue  # "the headmaster of Duskmoor" is somebody else
                cid = phrases[norm(m.group(1))]
                refs.append(Ref(cid, "role", m.group(0), i))
        for m in POSSESSIVE.finditer(p):
            owner = index.resolve(m.group(1)) or index.resolve(m.group(1).split()[0])
            if owner is None or (in_scene is not None and owner not in in_scene):
                continue
            kin = KIN_WORDS[m.group(2).lower()]
            ids = _kin(canon or {}, owner, kin)
            if len(ids) == 1:
                refs.append(Ref(ids[0], "kinship", m.group(0), i))
    return refs


def _kin(canon: dict[str, Any], cid: str, kind: str) -> list[str]:
    out = []
    for k in canon.get("kinship") or []:
        a, b = k["subject_id"], k["object_id"]
        if kind == "sibling" and k["kind"] == "sibling_of" and cid in (a, b):
            out.append(b if a == cid else a)
        elif kind == "aunt" and k["kind"] == "aunt_of" and b == cid:
            out.append(a)
        elif kind == "niece" and k["kind"] == "aunt_of" and a == cid:
            out.append(b)
    return list(dict.fromkeys(out))


def resolver(index: EntityIndex, registry: dict[str, Any] | None, canon: dict[str, Any] | None,
             in_scene: set[str] | None = None):
    """``named(text) -> [ids]``: names/aliases plus contextual references, in order of appearance (for speaker checks)."""
    def named(text: str) -> list[str]:
        ids = index.find_mentions(text, ("character",))
        for r in contextual_refs(text, index, registry, canon, in_scene):
            if r.character_id not in ids:
                ids.append(r.character_id)
        return ids
    return named
