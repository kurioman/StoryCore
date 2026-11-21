"""Lightweight encounter director (v1.5): a short, ranked list of established characters who could plausibly be nearby.

The narrator used anonymous or invented students ("an ideal first-year") because it had nothing tying lore characters to
places and lessons. This picks at most three canonical characters from the current place/activity, the gatherings
(``canon``), the pack's places (``pack.json`` → ``places``: regulars, likely affiliations and traits), years in lore, earlier meetings and recent appearances, and hands them to the narrator as an
*optional* hint — never a script. Deterministic (no model call), cheap, and silent when it would hurt the scene:

* nothing when the scene is already crowded (≥ 3 other characters present) or the player seeks solitude;
* character types the pack lists in ``never_random`` (gods, demon lords...) are never suggested;
* characters already present, who just left, or who appeared in the last few replies are not suggested again;
* a small stable rotation (by in-story day/time/place) keeps the same top name from being offered every turn;
* v1.6: during a story's first two replies, a populated start with nobody met yet also offers established characters
  (first-year students in a world with the ``school`` module), as a chance to notice someone. It is a soft preference: solitary, private and dream or flashback openings get nothing.

Narrator knowledge only: nothing here records a discovery or marks anyone as known to the protagonist.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LoreEntity, Message, TurnAnalysis
from . import world_pack
from .entities import EntityIndex, norm

AVOID = re.compile(r"\b(alone|avoid|avoiding|hide|hiding|nobody|no one|in private|privately|slip away|sneak|unseen|"
                   r"by myself|on my own|without being seen|leave me)\b", re.I)
# populated openings, and what overrides them (the setup text comes from the location, the starter and the opening)
POPULATED = re.compile(r"\b(gate|plaza|square|market|tavern|inn|street|courtyard|hall|corridor|hallway|refectory|dining|library|"
                       r"ceremony|entrance|grounds|arrival|crowd|harbou?r|station|guild)\b", re.I)
# with the school module, academy openings are populated too
POPULATED_SCHOOL = re.compile(r"\b(dormitory|orientation|admissions|academy|campus|classroom|lecture|class|enrol\w*)\b", re.I)
PRIVATE = re.compile(r"\b(alone|solitary|flashback|dream|private|in secret|cell|carriage|off[- ]campus|far from|at home|"
                     r"bedroom|nightmare|memory of)\b", re.I)
EARLY_REPLIES = 2
COOLDOWN_REPLIES = 3
MAX_HINTS = 3


def place_of(text: str, places: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The first of the pack's places whose keywords appear in ``text``."""
    t = norm(text)
    for place in places:
        if any(re.search(rf"\b{re.escape(norm(w))}\b", t) for w in place["keywords"]):
            return place
    return None


def _affiliations(d: dict[str, Any]) -> set[str]:
    """Department / faction / affiliation ids a lore character carries (any of the usual field names)."""
    out: set[str] = set()
    for k in ("department_id", "faction_id", "affiliation", "faction_ids", "affiliations", "department_ids"):
        v = d.get(k)
        out.update(str(x) for x in (v if isinstance(v, list) else [v]) if x)
    return out


def recent_activity(db: Session, path: list[Message]) -> dict[str, Any]:
    """From the last replies' analyses: ``seen`` and ``active`` (character id -> how many replies ago they were last
    present, or last spoke or visibly reacted; 0 = the latest reply) and ``left`` (who left and has not been back)."""
    replies = [m for m in path if m.role == "assistant"][-12:]
    out: dict[str, Any] = {"seen": {}, "active": {}, "left": set()}
    if not replies:
        return out
    rows = {r.message_id: r for r in db.scalars(select(TurnAnalysis).where(TurnAnalysis.message_id.in_([m.id for m in replies])))}
    for age, m in enumerate(reversed(replies)):
        r = rows.get(m.id)
        for b in (r.beats_json or []) if r else []:
            if not isinstance(b, dict):
                continue
            cid, beat = b.get("character_id"), b.get("beat")
            if beat == "left" and cid not in out["seen"]:
                out["left"].add(cid)
            if beat in ("speaking", "reacting", "present"):
                out["seen"].setdefault(cid, age)
            if beat in ("speaking", "reacting"):
                out["active"].setdefault(cid, age)
    return out


def candidates(db: Session, world_id: str | None, index: EntityIndex, state: dict[str, Any], path: list[Message],
               canon: dict[str, Any], known: set[str], *, player_turn: str = "", setup: str = "") -> dict[str, Any]:
    """{"hints": [{character_id, name, reasons}], "suppressed": reason | None, "place": ..., "class_id": ...}."""
    from .canon import detect_class, label, words

    sc = state.get("scene") or {}
    present = [c for c in sc.get("present") or [] if c in index.entities]
    out: dict[str, Any] = {"hints": [], "suppressed": None, "place": None, "class_id": None, "early": False}
    if not world_id:
        out["suppressed"] = "no world"
        return out
    if len(present) >= 3:
        out["suppressed"] = "the scene already has several characters"
        return out
    if AVOID.search(player_turn or ""):
        out["suppressed"] = "the player seeks solitude or avoids company"
        return out
    recent = " ".join(m.content for m in path[-2:])
    where = f"{sc.get('location') or ''} {sc.get('time') or ''}"
    active = detect_class(f"{where} {recent}", canon)
    pack = world_pack.of(db, world_id)
    places, never = pack.get("places") or [], pack.get("never_random") or []
    school = out["school"] = world_pack.has_module(pack, "school")
    place = place_of(where, places) or place_of(recent, places)
    out["place"], out["class_id"] = place["id"] if place else None, active["class_id"] if active else None
    seen = recent_activity(db, path)["seen"]
    opening = f"{where} {setup} {recent}"
    narrated = sum(1 for m in path if m.role == "assistant" and (m.content or "").strip())
    out["early"] = early = (narrated < EARLY_REPLIES and not present and not known and not seen
                            and bool(POPULATED.search(opening) or (school and POPULATED_SCHOOL.search(opening)))
                            and not PRIVATE.search(opening))
    rows = list(db.scalars(select(LoreEntity).where(LoreEntity.world_id == world_id, LoreEntity.category == "character")))
    stamp = f"{sc.get('story_day')}|{sc.get('time')}|{sc.get('location')}"
    scored: list[tuple[float, str, list[str]]] = []
    for e in rows:
        cid, d = e.entity_id, e.data_json or {}
        if cid in present or any(t in (e.entity_type or "") for t in never):
            continue
        score, why = 0.0, []
        if active:
            w = words(active)
            if active["teacher"] and active["teacher"]["character_id"] == cid:
                score += 6
                why.append(f"{w['leads_here']} {label(active)} {w['noun']}")
            elif any(s["character_id"] == cid for s in active["students"]):
                score += 5
                why.append(f"{w['joins_here']} {label(active)} {w['noun']}")
        if place:
            if cid in place["regulars"]:
                score += 6
                why.append(f"usually found at the {place['id'].replace('_', ' ')}")
            affs = set(place["likely"]["affiliations"]) & _affiliations(d)
            if affs:
                score += 1.5
                why.append(f"{sorted(affs)[0].replace('_', ' ')} at the {place['id'].replace('_', ' ')}")
            traits = {x.lower() for x in place["likely"]["traits"]}
            if traits & {str(t).lower() for t in d.get("personality_traits") or []}:
                score += 1
        if early and not active and (d.get("year") == 1 if school else True):  # a lesson already says who is around
            score += 2
            why.append("a first-year who could plausibly be nearby" if school else "could plausibly be nearby")
        if score <= 0:
            continue
        if school and d.get("year") == 1:
            score += 0.5
        if cid in known:
            score += 1
            why.append("met before")
        age = seen.get(cid)
        if age is not None and age < COOLDOWN_REPLIES:
            score -= 4  # just seen: give someone else a turn (unless their class/office demands them)
        score += int(hashlib.sha1(f"{stamp}|{cid}".encode()).hexdigest()[:2], 16) / 255  # stable rotation, < 1 point
        scored.append((score, cid, why))
    scored.sort(reverse=True)
    from .context_builder import looks_of
    data = {e.entity_id: e.data_json for e in rows}
    out["hints"] = [{"character_id": cid, "name": index.name(cid), "reasons": why, "looks": looks_of(data.get(cid))}
                    for s, cid, why in scored[:MAX_HINTS] if s > 1]
    return out


def render(result: dict[str, Any], index: EntityIndex) -> str:
    if not result["hints"]:
        return ""
    lines = [f"- {h['name']}" + (f" ({h['looks']})" if h.get("looks") else "") + f" — {'; '.join(h['reasons']) or 'plausibly nearby'}"
             for h in result["hints"]]
    school = result.get("school", True)
    # v0.6 (phase 9): same rules in fewer words
    opening = ("Story start: where the place is busy, let the protagonist notice or cross paths with one of them in the "
               f"first reply or two (seen across a room, a passing remark), rather than an invented "
               f"{'student' if school else 'person'}. An opportunity, not a conversation: the player decides.\n"
               if result.get("early") else "")
    usual = ("In a lesson the teacher and usual students are present; prefer them over invented classmates."
             if school else "At a recurring gathering its leader and usual members are present; prefer them over invented "
             "ones.")
    return (opening + f"At most one, only if it fits; never force a meeting. {usual}\n" + "\n".join(lines))
