"""Entity/alias resolution across imported lore and story-local NPCs.

Matching is accent- and case-insensitive. A first-name token becomes an alias only when it is unique
(e.g. "Serena" → serena_caldwin, but the shared surname "Caldwin" is ambiguous and never resolves).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LoreEntity

ENTITY_CATEGORIES = ("character", "faction", "location")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[\s_\-]+", " ", s.casefold()).strip()


@dataclass
class Entity:
    id: str
    name: str
    category: str
    type: str = ""
    aliases: list[str] = field(default_factory=list)
    local: bool = False


class EntityIndex:
    def __init__(self, entities: Iterable[Entity]):
        self.entities: dict[str, Entity] = {}
        self.alias_map: dict[str, set[str]] = {}
        token_owners: dict[str, set[str]] = {}
        for e in entities:
            self.entities[e.id] = e
            for a in {e.id, e.id.replace("_", " "), e.name, *e.aliases}:
                if a:
                    self.alias_map.setdefault(norm(a), set()).add(e.id)
            if e.category == "character":
                for i, tok in enumerate(norm(e.name).split(" ")):
                    if len(tok) >= 3:
                        token_owners.setdefault(tok, set()).add(e.id)
                for tok in norm(e.id).split(" ")[:1]:
                    if len(tok) >= 3:
                        token_owners.setdefault(tok, set()).add(e.id)
        for tok, owners in token_owners.items():
            if len(owners) == 1 and tok not in self.alias_map:
                self.alias_map[tok] = set(owners)
            elif len(owners) > 1:
                self.alias_map.setdefault(tok, set()).update(owners)
        self._regex = None

    def resolve(self, text: str) -> str | None:
        ids = self.alias_map.get(norm(text))
        return next(iter(ids)) if ids and len(ids) == 1 else None

    def candidates(self, text: str) -> list[str]:
        return sorted(self.alias_map.get(norm(text), set()))

    def _pattern(self) -> re.Pattern[str] | None:
        if self._regex is None:
            keys = sorted((k for k, v in self.alias_map.items() if len(v) == 1 and len(k) >= 3), key=len, reverse=True)
            self._regex = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b") if keys else False
        return self._regex or None

    def find_mentions(self, text: str, categories: tuple[str, ...] = ENTITY_CATEGORIES) -> list[str]:
        pat = self._pattern()
        if not pat:
            return []
        out: list[str] = []
        for m in pat.finditer(norm(text)):
            eid = next(iter(self.alias_map[m.group(1)]))
            if eid not in out and self.entities[eid].category in categories:
                out.append(eid)
        return out

    def name(self, eid: str) -> str:
        e = self.entities.get(eid)
        return e.name if e else eid


def build_index(db: Session, world_id: str | None, state: dict[str, Any] | None = None) -> EntityIndex:
    ents: list[Entity] = []
    if world_id:
        for le in db.scalars(select(LoreEntity).where(LoreEntity.world_id == world_id,
                                                      LoreEntity.category.in_(ENTITY_CATEGORIES))):
            ents.append(Entity(le.entity_id, le.name, le.category, le.entity_type, list(le.aliases_json or [])))
    for npc in (state or {}).get("npcs", []) or []:
        if npc.get("id") and npc.get("name"):
            ents.append(Entity(npc["id"], npc["name"], "character", "local_npc", list(npc.get("aliases") or []), local=True))
    return EntityIndex(ents)
