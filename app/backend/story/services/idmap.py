"""Deep ID remapping used by savepoint restore and story import (UUIDs are unique, so exact-string replacement is safe)."""
from __future__ import annotations

from typing import Any


def remap(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [remap(v, mapping) for v in value]
    if isinstance(value, dict):
        return {mapping.get(k, k) if isinstance(k, str) else k: remap(v, mapping) for k, v in value.items()}
    return value


def unresolved(value: Any, known: set[str], id_like) -> set[str]:
    """Collect id-like strings that are not in ``known``."""
    out: set[str] = set()
    if isinstance(value, str):
        if id_like(value) and value not in known:
            out.add(value)
    elif isinstance(value, list):
        for v in value:
            out |= unresolved(v, known, id_like)
    elif isinstance(value, dict):
        for v in value.values():
            out |= unresolved(v, known, id_like)
    return out
