"""A world's lore pack settings (its ``pack.json``, stored at import in ``World.data_json["pack"]``).

The single place the engine reads pack data from. Every accessor returns an empty value when the world has no pack (or
no such section), so a feature whose section is missing is simply off for that world. Corrections made inside the app
are stored separately (settings scoped to the world's slug) and layered on top by each feature.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import World


def of(db: Session, world_id: str | None) -> dict[str, Any]:
    if not world_id:
        return {}
    world = db.get(World, world_id)
    return ((world.data_json or {}).get("pack") or {}) if world else {}


def section(db: Session, world_id: str | None, name: str, default: Any = None) -> Any:
    value = of(db, world_id).get(name)
    return value if value is not None else default


def has_module(pack: dict[str, Any], module: str) -> bool:
    return module in (pack.get("modules") or [])
