"""Common record models of the lore packs (Kurio, 24/11/2026).

Every character of a pack follows the same 12 categories, so the narrator always finds the same things in the same
place. The Lore page shows how much of each record is filled ("9/11") and lists the records still to complete; the
"New" button of the Lore page starts from these templates.

Only characters have a model so far; the other families (places, groups, world and rules, story) get theirs when their
records are reviewed.
"""
from __future__ import annotations

import copy
from typing import Any

# category key -> (label shown in the app, empty value of a new record)
CHARACTER_FIELDS: list[tuple[str, str, Any]] = [
    ("gender", "Gender", ""),
    ("appearance", "Appearance", {"hair": "", "eyes": ""}),
    ("power", "Power", {"system": "", "rank": "", "abilities": []}),
    ("role", "Role", ""),
    ("personality_traits", "Personality traits", []),
    ("motivation", "Motivation", ""),
    ("story_functions", "Story functions", []),
    ("faction_ids", "Factions", []),
    ("notes", "Notes", []),
    ("relationships", "Relationships", []),
    ("hidden", "Secrets", []),
    ("never", "Never", []),
]
# a character may have no secret: "Secrets" is never counted as missing
OPTIONAL = {"hidden"}

MODELS: dict[str, list[tuple[str, str, Any]]] = {"character": CHARACTER_FIELDS}


def _filled(v: Any) -> bool:
    if isinstance(v, dict):
        return any(_filled(x) for x in v.values())
    if isinstance(v, list):
        return any(_filled(x) for x in v)
    return v not in (None, "")


def completeness(category: str, data: dict[str, Any] | None, has_secret: bool = False) -> dict[str, Any] | None:
    """How much of a record follows its model: {"filled", "total", "missing": [labels]}; None without a model.
    Secrets are stripped from the record at import, so whether it has one is passed in."""
    fields = MODELS.get(category)
    if not fields:
        return None
    data = data or {}
    missing = [label for key, label, _ in fields
               if key not in OPTIONAL and not _filled(data.get(key))]
    required = [k for k, _, _ in fields if k not in OPTIONAL]
    return {"filled": len(required) - len(missing), "total": len(required), "missing": missing,
            "has_secret": bool(has_secret)}


def template(category: str, record_id: str, name: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """An empty record of the model, ready to be filled in the pack's file."""
    out: dict[str, Any] = {"id": record_id, "name": name, "aliases": []}
    out.update(extra or {})
    for key, _, empty in MODELS.get(category, []):
        out.setdefault(key, copy.deepcopy(empty))
    return out
