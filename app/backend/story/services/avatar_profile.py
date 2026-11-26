"""The simple avatar (test report of 26 Nov 2026): name, appearance, abilities and a free "player note".

The older avatar had ~20 fields (age, pronouns, backstory, personality, goals...). They are folded once into the new
shape, nothing is lost:
- appearance.structured (hair, eyes...)        -> appended to appearance.description
- skills, powers                               -> abilities
- every other written field                    -> user_note, one "Label: value" line each
- stats, inventory, portrait_fit, tags         -> kept as they are (advanced options of the editor)

``simplify`` is idempotent (profiles carry ``"format": 2``) and is applied at every start (main.seed_defaults), on
import and on save, so old avatars, imported files and older clients all end up in the simple shape.
"""
from __future__ import annotations

from typing import Any

FORMAT = 2

# (key, label) folded into the player note, in this order
NOTE_FIELDS = [
    ("called_name", "Called by NPCs"), ("pronunciation", "Pronunciation"), ("age", "Age"), ("pronouns", "Pronouns"),
    ("gender", "Gender"), ("title", "Title"), ("occupation", "Occupation"), ("social_status", "Social status"),
    ("affiliations", "Affiliations"), ("backstory", "Backstory"), ("personality", "Personality"), ("goals", "Goals"),
    ("motivations", "Motivations"), ("fears", "Fears"), ("values", "Values"), ("weaknesses", "Weaknesses"),
    ("secrets", "Secrets"), ("speech_style", "Speech style"), ("additional_info", "Additional info"), ("notes", "Notes"),
]
ABILITY_FIELDS = [("skills", "Skills"), ("powers", "Powers")]


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_text(x) for x in v if _text(x))
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_text(x)}" for k, x in v.items() if _text(x))
    return str(v).strip()


def is_simple(profile: dict[str, Any] | None) -> bool:
    return isinstance(profile, dict) and profile.get("format") == FORMAT


def simplify(profile: dict[str, Any] | None, name: str = "") -> tuple[dict[str, Any], str]:
    """Returns (profile in the simple shape, avatar name). Already simple profiles come back unchanged."""
    p = dict(profile or {})
    if is_simple(p):
        return p, name
    out: dict[str, Any] = {"format": FORMAT}

    # name: the in-story name wins (it is what the narrator used)
    display = _text(p.get("display_name"))
    new_name = display or name

    ap = p.get("appearance")
    if isinstance(ap, dict):
        desc = _text(ap.get("description"))
        struct = ap.get("structured") if isinstance(ap.get("structured"), dict) else {}
        details = ", ".join(f"{k}: {_text(v)}" for k, v in struct.items() if _text(v))
        desc = " ".join(x for x in (desc, f"({details})" if details else "") if x)
    else:
        desc = _text(ap)
    out["appearance"] = {"description": desc}

    abilities = [_text(p.get("abilities"))] if _text(p.get("abilities")) else []
    many = sum(1 for k, _ in ABILITY_FIELDS if _text(p.get(k))) > 1
    for k, label in ABILITY_FIELDS:
        if _text(p.get(k)):
            abilities.append(f"{label}: {_text(p[k])}" if many else _text(p[k]))
    out["abilities"] = "\n".join(abilities)

    note = [_text(p.get("user_note"))] if _text(p.get("user_note")) else []
    for k, label in NOTE_FIELDS:
        if _text(p.get(k)):
            note.append(f"{label}: {_text(p[k])}")
    out["user_note"] = "\n".join(note)

    for k in ("stats", "inventory", "portrait_fit"):  # kept for the advanced options
        if p.get(k) is not None:
            out[k] = p[k]
    return out, new_name


def migrate_all(db) -> int:
    """Folds every older avatar into the simple shape. Returns how many changed."""
    from sqlalchemy import select

    from ..models import Avatar

    n = 0
    for a in db.scalars(select(Avatar)):
        if is_simple(a.profile_json):
            continue
        a.profile_json, a.name = simplify(a.profile_json, a.name)
        n += 1
    return n
