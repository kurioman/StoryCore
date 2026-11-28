"""v0.7.7 "who knows what": a narrator-only secret can say which characters know it.

In a pack, a secret (a line of a record's ``"hidden"`` field) may begin with a list of the characters who know it:

    "(Known by: Beelzebub, Kriemhild) She is bound to the Demon King by a soul-bond."
    "(Connu de : Emily, Artemis) ..."           (French works too)
    "(Known by: nobody) ..."                     (only the record's own character knows it)
    "(Known by: everyone) ..."                   (every character knows it; only the protagonist does not)

or, in JSON, be written as ``{"text": "...", "known_by": ["beelzebub", "kriemhild"]}``. Names are matched with the
pack's characters by name, first name, alias or id. Without a list the older rule stays: a character knows a secret if
it is her own or she would plausibly know it.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_PREFIX = re.compile(
    r"^(?P<label>\s*\[[^\]\n]*\]\s*)?\(\s*(?:known\s+(?:only\s+)?by|connue?s?\s+(?:seulement\s+)?(?:de|par)|qui\s+sait)"
    r"\s*:\s*(?P<who>[^)]*)\)\s*", re.IGNORECASE)
NOBODY = {"nobody", "no one", "noone", "none", "personne", "aucun", "aucune", "elle seule", "lui seul", "herself", "himself"}
EVERYONE = {"everyone", "everybody", "all", "tout le monde", "tous", "toutes"}


def note_from_object(obj: Any) -> str | None:
    """``{"text": ..., "known_by": [...]}`` as one secret line, or None when ``obj`` is not that shape."""
    if not isinstance(obj, dict):
        return None
    text = obj.get("text") or obj.get("secret") or obj.get("note")
    if not isinstance(text, str) or not text.strip():
        return None
    who = obj.get("known_by")
    if who in (None, "", []):
        return text.strip()
    names = who if isinstance(who, list) else [who]
    return f"(Known by: {', '.join(str(n) for n in names)}) {text.strip()}"


def parse(note: str) -> tuple[str, str | None, list[str], str]:
    """(label, mode, names, text): ``mode`` is None (no list), "list", "nobody" or "everyone"."""
    m = _PREFIX.match(note or "")
    if not m:
        return "", None, [], note
    label, text = (m.group("label") or "").strip(), note[m.end():].strip()
    names = [n.strip() for n in re.split(r",|;|/|\bet\b|\band\b", m.group("who")) if n.strip()]
    low = {n.casefold() for n in names}
    if not names or low <= NOBODY:
        return label, "nobody", [], text
    if low & EVERYONE:
        return label, "everyone", [], text
    return label, "list", names, text


def name_lookup(entities: Iterable[Any]) -> dict[str, str]:
    """casefolded name, first name, alias or id -> the character's name (characters only)."""
    out: dict[str, str] = {}
    for e in entities:
        name = str(getattr(e, "name", "") or "").strip()
        if not name:
            continue
        keys = [name, str(getattr(e, "entity_id", "") or ""), *(getattr(e, "aliases_json", None) or [])]
        for k in keys:
            if isinstance(k, str) and k.strip():
                out.setdefault(k.strip().casefold(), name)
                out.setdefault(k.strip().casefold().replace("_", " "), name)
        first = name.split()[0].casefold()
        out.setdefault(first, name)
    return out


def resolve(names: list[str], lookup: dict[str, str]) -> tuple[list[str], list[str]]:
    """(known names as the pack writes them, names that match no character)."""
    found, unknown = [], []
    for n in names:
        hit = lookup.get(n.casefold()) or lookup.get(n.casefold().replace("_", " "))
        if hit:
            if hit not in found:
                found.append(hit)
        else:
            unknown.append(n)
    return found, unknown


def render(subject: str, note: str, lookup: dict[str, str], *, subject_is_character: bool) -> str:
    """One line of the narrator-only secrets section, with who knows it when the pack says so."""
    label, mode, names, text = parse(note)
    body = f"{label} {text}".strip()
    if mode is None:
        return f"- {subject}: {body}"
    if mode == "everyone":
        who = "Known by every character of this world; only the protagonist does not know it yet."
    elif mode == "nobody":
        who = (f"Known ONLY by {subject}: no other character knows it." if subject_is_character
               else "Known by NO character: it is for you, the narrator, alone.")
    else:
        found, unknown = resolve(names, lookup)
        known = found + unknown  # an unknown name is still said as written (Check Lore Packs warns about it)
        if subject_is_character and subject not in known:
            known.append(subject)
        who = (f"Known ONLY by: {', '.join(known)}. Every other character does NOT know it: they never act on it, "
               f"hint at it or react to it, until the story shows them learning it.")
    return f"- {subject}: {body} [{who}]"


def unknown_names(hidden: dict[str, list[str]], lookup: dict[str, str]) -> list[str]:
    """Names in "(Known by: ...)" lists that match no character of the pack (for Check Lore Packs)."""
    out: list[str] = []
    for notes in (hidden or {}).values():
        for n in notes:
            _, mode, names, _ = parse(n)
            if mode == "list":
                for u in resolve(names, lookup)[1]:
                    if u not in out:
                        out.append(u)
    return out
