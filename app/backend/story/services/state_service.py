"""Versioned per-branch story state (stats, relationships, inventory, quests, scene, expressions...).

Every change creates a new ``story_states`` row (source + summary + optional message id). Undo restores
the previous version as a new version, so history is never rewritten.
"""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Message, MessageBranch, StoryState, now_iso

LIST_KEYS = ("clues", "promises", "mysteries", "goals")

# Built-in templates. A world's own stat sheet comes from its pack (pack.json → stats, see routers/stories.py).
STAT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "fantasy": [
        {"label": "HP", "type": "current_max", "value": 100, "max": 100},
        {"label": "Stamina", "type": "current_max", "value": 100, "max": 100},
        {"label": "Mana", "type": "current_max", "value": 50, "max": 50},
        {"label": "Level", "type": "number", "value": 1},
        {"label": "Experience", "type": "current_max", "value": 0, "max": 100, "unit": "XP"},
        {"label": "Gold", "type": "number", "value": 10, "unit": "g"},
    ],
    "minimal": [{"label": "Condition", "type": "text", "value": "Healthy"}],
    "none": [],
}


def _id() -> str:
    return uuid.uuid4().hex[:12]


def stats_from(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stat entries for a new story from a stat sheet (a template or a pack's stats)."""
    return [dict(s, id=_id(), hidden=False) for s in stats]


def default_state(template: str = "fantasy") -> dict[str, Any]:
    return {
        "scene": {"location": "", "location_id": None, "date": "", "time": "", "weather": "", "mood": "", "status": "",
                  "present": [], "chapter": "", "scene_id": "",
                  # v1.4 structured in-story clock (services/world_state.py); story_day None = D1
                  "weekday": "", "day": None, "month": "", "year": None, "story_day": None, "established": {},
                  "world_history": []},
        "player": {"name": "", "title": "", "condition": "", "location": ""},
        "stats": stats_from(STAT_TEMPLATES.get(template, STAT_TEMPLATES["fantasy"])),
        "conditions": [],
        "inventory": [],
        "quests": [],
        "relationships": [],
        "relationship_axes": ["trust", "affection", "respect", "familiarity", "rivalry", "fear"],
        "npcs": [],
        "expressions": {},
        "clues": [], "promises": [], "mysteries": [], "goals": [],
    }


def normalize(state: dict[str, Any]) -> dict[str, Any]:
    """Fill missing keys and IDs so older/partial states stay usable."""
    base = default_state("none")
    out = copy.deepcopy(state or {})
    for k, v in base.items():
        out.setdefault(k, copy.deepcopy(v))
    for k, v in base["scene"].items():
        out["scene"].setdefault(k, v)
    for k in ("stats", "conditions", "inventory", "quests", "relationships", "npcs", *LIST_KEYS):
        out[k] = [dict(x, id=x.get("id") or _id()) if isinstance(x, dict) else {"id": _id(), "text": str(x)} for x in out.get(k) or []]
    return out


def current(db: Session, branch_id: str) -> StoryState | None:
    return db.scalar(select(StoryState).where(StoryState.branch_id == branch_id).order_by(StoryState.state_version.desc()).limit(1))


def history(db: Session, branch_id: str, limit: int = 100) -> list[StoryState]:
    return list(db.scalars(select(StoryState).where(StoryState.branch_id == branch_id)
                           .order_by(StoryState.state_version.desc()).limit(limit)))


def save(db: Session, story_id: str, branch_id: str, state: dict[str, Any], *, source: str, summary: str,
         message_id: str | None = None) -> StoryState:
    cur = current(db, branch_id)
    row = StoryState(story_id=story_id, branch_id=branch_id, state_version=(cur.state_version + 1) if cur else 1,
                     state_json=normalize(state), source=source, summary=summary[:2000], message_id=message_id)
    db.add(row)
    db.flush()
    return row


def undo_last(db: Session, story_id: str, branch_id: str) -> StoryState:
    rows = history(db, branch_id, 2)
    if len(rows) < 2:
        raise ValueError("Nothing to undo: this is the first state version.")
    latest, prev = rows
    return save(db, story_id, branch_id, prev.state_json, source="undo",
                summary=f"Undid v{latest.state_version}: {latest.summary}")


def fork(db: Session, story_id: str, from_branch: MessageBranch, new_branch: MessageBranch, fork_message: Message | None) -> StoryState | None:
    q = select(StoryState).where(StoryState.branch_id == from_branch.id)
    if fork_message is not None:
        q = q.where(StoryState.created_at <= fork_message.created_at)
    src = db.scalar(q.order_by(StoryState.state_version.desc()).limit(1)) or current(db, from_branch.id)
    if src is None:
        return None
    return save(db, story_id, new_branch.id, src.state_json, source="branch_fork",
                summary=f"Forked from branch '{from_branch.label}' (state v{src.state_version})")


# --------------------------------------------------------------------------- change application
def _find(items: list[dict[str, Any]], key: str, needle: str | None) -> dict[str, Any] | None:
    if not needle:
        return None
    n = str(needle).strip().casefold()
    for it in items:
        if it.get("id") == needle or str(it.get(key, "")).strip().casefold() == n:
            return it
    return None


def _name_key(s: Any) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or ""))
    return " ".join("".join(ch for ch in s if not unicodedata.combining(ch)).casefold().replace("_", " ").split())


def find_relationship(pool: list[dict[str, Any]], target_id: str | None, name: str | None) -> dict[str, Any] | None:
    """The record for one canonical target within one direction (v1.5 uniqueness key: source + canonical target).
    Order: same id; same name; an id-less legacy record whose name is the target's full name or its unique first name
    ("Serena" for "Serena Caldwin"). Never matches a record that already has a *different* id."""
    if target_id:
        hit = next((r for r in pool if r.get("target_id") == target_id), None)
        if hit:
            return hit
    n = _name_key(name)
    if not n:
        return None
    same = [r for r in pool if _name_key(r.get("target_name")) == n and (not target_id or not r.get("target_id")
                                                                          or r.get("target_id") == target_id)]
    if same:
        return same[0]
    first = n.split(" ")[0]
    loose = [r for r in pool if not r.get("target_id") and len(first) >= 3
             and (_name_key(r.get("target_name")) == first or _name_key(r.get("target_name")).split(" ")[0] == first)]
    return loose[0] if len(loose) == 1 and target_id else None


def _num(v: Any) -> float | int:
    f = float(v)
    return int(f) if f.is_integer() else f


def strip_day_token(time_text: Any) -> str:
    """A scene's time without a day counter: "late morning, D2" -> "late morning". The day has its own field; capture
    proposals sometimes put it here too, and the header would then show it twice (v1.6)."""
    return re.sub(r"[\s,;:–—-]*\bD\d{1,4}\b[\s,;:–—-]*", " ", str(time_text or "")).strip()


def apply_change(state: dict[str, Any], kind: str, p: dict[str, Any], *, at: str | None = None,
                 source: str = "manual", message_id: str | None = None) -> tuple[dict[str, Any], str]:
    """Apply one structured change. Returns (new_state, human summary). Raises ValueError if not applicable."""
    s = normalize(state)
    at = at or now_iso()
    if kind == "stat":
        st = _find(s["stats"], "label", p.get("stat") or p.get("label") or p.get("id"))
        if st is None:
            if p.get("create"):
                st = {"id": _id(), "label": p.get("stat") or p.get("label"), "type": "number", "value": 0, "hidden": False}
                s["stats"].append(st)
            else:
                raise ValueError(f"Unknown stat '{p.get('stat') or p.get('label')}'. Create it first or edit the proposal.")
        old = st.get("value")
        if p.get("delta") is not None:
            st["value"] = _num(float(old or 0) + float(p["delta"]))
        elif "value" in p:
            st["value"] = p["value"]
        if p.get("max") is not None:
            st["max"] = p["max"]
        if st.get("type") == "current_max" and st.get("max") is not None and isinstance(st["value"], (int, float)):
            st["value"] = max(min(st["value"], st["max"]), 0) if p.get("clamp", True) else st["value"]
        return s, f"{st['label']}: {old} → {st['value']}"
    if kind == "relationship":
        # Directional: a record without ``source_id`` is the target character's view of the protagonist (the meaning of
        # every record created before v1.3); with ``source_id`` it is that character's view of the target
        # ("protagonist" as source is the player's own, manually set view). Never mirrored automatically.
        name = p.get("target_name") or p.get("target") or p.get("target_id")
        src = p.get("source_id") or None
        pool = [r for r in s["relationships"] if (r.get("source_id") or None) == src]
        rel = find_relationship(pool, p.get("target_id"), name)
        if rel is not None and p.get("target_id") and not rel.get("target_id"):
            rel["target_id"] = p["target_id"]  # v1.5: a legacy name-only record learns its canonical id (no second card)
        if rel is None:
            rel = {"id": _id(), "target_id": p.get("target_id"), "target_name": name or "Unknown", "label": "Acquaintance",
                   "axes": {a: 0 for a in s["relationship_axes"]}, "note": "", "history": []}
            if src:
                rel["source_id"], rel["source_name"] = src, p.get("source_name") or src
            s["relationships"].append(rel)
        parts = []
        axis = p.get("axis")
        detail: dict[str, Any] = {}
        if axis:
            rel["axes"].setdefault(axis, 0)
            if axis not in s["relationship_axes"]:
                s["relationship_axes"].append(axis)  # e.g. v1.5 rivalry in an older story: additive, values untouched
            old = rel["axes"][axis]
            if p.get("delta") is not None:
                rel["axes"][axis] = max(-100, min(100, _num(float(old) + float(p["delta"]))))
            elif p.get("value") is not None:
                rel["axes"][axis] = max(-100, min(100, _num(p["value"])))
            parts.append(f"{axis} {old}→{rel['axes'][axis]}")
            detail = {"axis": axis, "previous": old, "new": rel["axes"][axis], "delta": _num(rel["axes"][axis] - old)}
        if p.get("label"):
            parts.append(f"label '{rel.get('label')}'→'{p['label']}'")
            rel["label"] = p["label"]
        if p.get("note"):
            rel["note"] = p["note"]
            parts.append("note updated")
        who = f"{rel.get('source_name') or rel['source_id']} → {rel['target_name']}" if rel.get("source_id") else rel["target_name"]
        summary = f"{who}: " + (", ".join(parts) or "added")
        entry = {"at": at, "change": summary, "source": source, "message_id": message_id, "reason": p.get("reason", ""), **detail}
        for k in ("evidence", "auto", "impact", "analysis_id", "reverts", "proposed_delta", "difficulty"):
            if p.get(k) is not None:
                entry[k] = p[k]
        rel.setdefault("history", []).append(entry)
        rel["history"] = rel["history"][-50:]
        return s, summary
    if kind == "inventory_add":
        it = _find(s["inventory"], "name", p.get("name"))
        qty = int(p.get("qty") or 1)
        if it:
            it["qty"] = int(it.get("qty") or 0) + qty
        else:
            s["inventory"].append({"id": _id(), "name": p["name"], "qty": qty, "equipped": False, "note": p.get("note", "")})
        return s, f"Gained {qty}× {p['name']}"
    if kind == "inventory_remove":
        it = _find(s["inventory"], "name", p.get("name"))
        if it is None:
            raise ValueError(f"Item '{p.get('name')}' is not in the inventory.")
        qty = int(p.get("qty") or 1)
        it["qty"] = int(it.get("qty") or 1) - qty
        if it["qty"] <= 0:
            s["inventory"].remove(it)
        return s, f"Lost {qty}× {p['name']}"
    if kind == "condition_add":
        s["conditions"].append({"id": _id(), "label": p["label"], "severity": p.get("severity", "moderate"), "note": p.get("note", "")})
        return s, f"Condition added: {p['label']}"
    if kind == "condition_remove":
        c = _find(s["conditions"], "label", p.get("label"))
        if c is None:
            raise ValueError(f"Condition '{p.get('label')}' is not active.")
        s["conditions"].remove(c)
        return s, f"Condition removed: {p['label']}"
    if kind == "quest":
        q = _find(s["quests"], "title", p.get("title"))
        if q is None:
            q = {"id": _id(), "title": p["title"], "status": "active", "objectives": [], "note": ""}
            s["quests"].append(q)
            summary = f"Quest added: {p['title']}"
        else:
            summary = f"Quest updated: {p['title']}"
        if p.get("status"):
            q["status"] = p["status"]
            summary += f" ({p['status']})"
        if p.get("objective"):
            ob = _find(q["objectives"], "text", p["objective"])
            if ob is None:
                ob = {"id": _id(), "text": p["objective"], "done": False}
                q["objectives"].append(ob)
            if p.get("objective_done") is not None:
                ob["done"] = bool(p["objective_done"])
        if p.get("note"):
            q["note"] = p["note"]
        return s, summary
    if kind == "scene":
        sc = s["scene"]
        changed = []
        for k in ("location", "location_id", "date", "time", "weather", "mood", "status", "chapter", "scene_id",
                  "weekday", "day", "month", "year", "story_day"):
            if p.get(k) not in (None, ""):
                sc[k] = strip_day_token(p[k]) if k == "time" else p[k]
                changed.append(f"{k}={sc[k]}")
        for cid in p.get("present_add") or []:
            if cid not in sc["present"]:
                sc["present"].append(cid)
                changed.append(f"+{cid}")
        for cid in p.get("present_remove") or []:
            if cid in sc["present"]:
                sc["present"].remove(cid)
                changed.append(f"-{cid}")
        if "present" in p and isinstance(p["present"], list):
            sc["present"] = list(dict.fromkeys(p["present"]))
            changed.append("cast set")
        return s, "Scene: " + (", ".join(changed) or "no change")
    if kind == "player":
        for k in ("condition", "title", "location", "name"):
            if p.get(k) not in (None, ""):
                s["player"][k] = p[k]
        return s, "Player: " + ", ".join(f"{k}={v}" for k, v in p.items() if k in s["player"])
    if kind in ("list_add", "list_resolve"):
        lst = p.get("list")
        if lst not in LIST_KEYS:
            raise ValueError(f"Unknown list '{lst}'.")
        if kind == "list_add":
            s[lst].append({"id": _id(), "text": p["text"], "resolved": False, "note": p.get("note", "")})
            return s, f"{lst[:-1].capitalize()} added: {p['text']}"
        it = _find(s[lst], "text", p.get("text"))
        if it is None:
            raise ValueError(f"No matching entry in {lst}.")
        it["resolved"] = True
        return s, f"{lst[:-1].capitalize()} resolved: {it['text']}"
    if kind == "expression":
        cid = p["character_id"]
        cur = s["expressions"].get(cid) or {}
        if cur.get("locked") and not p.get("force"):
            raise ValueError(f"Expression for {cid} is locked.")
        s["expressions"][cid] = {"slot": int(p["slot"]), "locked": bool(p.get("locked", cur.get("locked", False))),
                                 "source": p.get("source", source), "updated_at": at}
        return s, f"{cid} expression → {p['slot']}"
    raise ValueError(f"Unknown change kind '{kind}'.")
