"""Relationship evolution from scene analysis (v1.3): evaluated after every reply, changed only with evidence.

Policy (``relationship_mode`` setting):
- ``auto_conservative`` (default): small (|delta| <= 3), minor-impact, confident (>= 0.7) changes whose evidence quote is
  found in the reply are applied at once and recorded as automatic; anything larger, major or less certain goes to the
  existing review queue (state proposals); below 0.5 confidence it is dropped.
- ``review``: everything goes to the review queue. ``off``: nothing is evaluated or applied, and what exists is left alone.
Changes are directional (``source`` feels differently about ``target``) and never mirrored; the protagonist's own feelings
are never set by the model. Automatic changes are tied to their source message: re-analysing the reply first reverts them,
and when the reply leaves the story (deleted, regenerated, edited, alternative switched) they are reverted, with the
audit trail kept. Changes the player approved stay applied and are only flagged (see narrative character detail).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MessageBranch, StateProposal, Story, now_iso
from . import state_service, story_tree
from .entities import EntityIndex

MODES = ("auto_conservative", "review", "off")
AUTO_MAX_DELTA = 3
MAJOR_MAX_DELTA = 10
AUTO_MIN_CONFIDENCE = 0.7
DROP_BELOW_CONFIDENCE = 0.5
PROTAGONIST = "protagonist"
# words an extractor uses for the player character; never a relationship *target name* of an NPC record
PROTAGONIST_WORDS = {"player", "protagonist", "you", "the player", "the protagonist", "mc", "main character"}

# v1.5 dimensions offered to the analysis (a story's own extra axes are kept too). Rivalry is new and additive.
CORE_AXES = ["trust", "affection", "respect", "familiarity", "rivalry", "fear"]

# v1.5 story-level progression difficulty (story setting ``relationship_difficulty``; default "normal"). One table, no
# hidden constants: multipliers apply to the analysis' proposed delta *after* validation; a major negative event is
# never softened (serious consequences stay possible in every mode); tier thresholds scale with ``tier_scale``.
DIFFICULTY: dict[str, dict[str, float]] = {
    "relaxed": {"positive": 1.5, "minor_negative": 0.5, "major_negative": 1.0, "tier_scale": 0.75},
    "normal": {"positive": 1.0, "minor_negative": 1.0, "major_negative": 1.0, "tier_scale": 1.0},
    "strict": {"positive": 0.6, "minor_negative": 1.0, "major_negative": 1.0, "tier_scale": 1.35},
}
DEFAULT_DIFFICULTY = "normal"
# derived stage from the bond score = trust + affection + (respect + familiarity) / 2, thresholds × tier_scale
TIERS = [(70, "Deep bond"), (40, "Close / trusted"), (20, "Friendly"), (8, "Familiar"), (float("-inf"), "Acquaintance")]


def difficulty_of(story_settings: dict[str, Any] | None) -> str:
    d = (story_settings or {}).get("relationship_difficulty")
    return d if d in DIFFICULTY else DEFAULT_DIFFICULTY


def scale_delta(delta: int, impact: str, difficulty: str) -> int:
    """Proposed delta -> applied delta for a difficulty. Positive: × multiplier, rounded half up, never below 1 (a real
    positive moment always counts a little). Minor negative: × multiplier, rounded toward zero (Relaxed may absorb a
    -1 entirely). Major negative: unchanged."""
    import math

    d = DIFFICULTY.get(difficulty, DIFFICULTY[DEFAULT_DIFFICULTY])
    if delta > 0:
        return max(1, math.floor(delta * d["positive"] + 0.5))
    if impact == "major":
        return int(delta * d["major_negative"])
    return int(delta * d["minor_negative"])  # int() truncates toward zero


def tier(axes: dict[str, Any], difficulty: str = DEFAULT_DIFFICULTY) -> dict[str, Any]:
    """Deterministic stage of one directional record (never an LLM label). Distinct labels for fear/rivalry/conflicted
    trajectories; a rival can also be respected."""
    a = {k: float(v or 0) for k, v in (axes or {}).items()}
    s = DIFFICULTY.get(difficulty, DIFFICULTY[DEFAULT_DIFFICULTY])["tier_scale"]
    trust, aff, resp, fam = a.get("trust", 0), a.get("affection", 0), a.get("respect", 0), a.get("familiarity", 0)
    riv, fear = a.get("rivalry", 0), a.get("fear", 0)
    bond = trust + aff + (resp + fam) / 2
    why = f"bond {bond:g} = trust {trust:g} + affection {aff:g} + (respect {resp:g} + familiarity {fam:g}) / 2"
    if fear >= 30 * s:
        return {"tier": "Afraid", "kind": "fear", "score": bond, "reason": f"fear {fear:g} ≥ {30 * s:g}"}
    if riv >= 30 * s:
        label = "Respected rival" if resp >= 20 * s else "Rival"
        return {"tier": label, "kind": "rival", "score": bond, "reason": f"rivalry {riv:g} ≥ {30 * s:g}"}
    if aff >= 25 * s and trust <= -15 * s:
        return {"tier": "Torn — cares, but distrusts", "kind": "conflicted", "score": bond,
                "reason": f"affection {aff:g} ≥ {25 * s:g} while trust {trust:g} ≤ {-15 * s:g}"}
    if trust <= -25 * s or aff <= -25 * s:
        return {"tier": "Hostile", "kind": "negative", "score": bond, "reason": f"trust {trust:g} / affection {aff:g} ≤ {-25 * s:g}"}
    if trust <= -10 * s:
        return {"tier": "Wary", "kind": "negative", "score": bond, "reason": f"trust {trust:g} ≤ {-10 * s:g}"}
    for th, label in TIERS:
        if bond >= th * s:
            if label == "Deep bond" and (trust < 40 * s or aff < 40 * s):
                continue  # a deep bond needs both trust and warmth, not respect alone
            return {"tier": label, "kind": "positive", "score": bond,
                    "reason": why + (f" ≥ {th * s:g}" if th != float("-inf") else "")}
    return {"tier": "Acquaintance", "kind": "positive", "score": bond, "reason": why}


def tiers_for(state: dict[str, Any], difficulty: str) -> dict[str, dict[str, Any]]:
    return {r["id"]: tier(r.get("axes") or {}, difficulty) for r in state.get("relationships") or [] if r.get("id")}


def find_duplicates(state: dict[str, Any], index: EntityIndex | None = None) -> list[dict[str, Any]]:
    """Groups of records that describe the same direction and the same canonical person (read-only detection). A record
    without an id counts as that person when its name resolves to the id. Different directions are never grouped."""
    groups: dict[tuple[Any, str], list[dict[str, Any]]] = {}
    named_ids = {((r.get("source_id") or None), state_service._name_key(r.get("target_name"))): r["target_id"]
                 for r in state.get("relationships") or [] if r.get("target_id")}
    for r in state.get("relationships") or []:
        tid = r.get("target_id") or (index.resolve(r.get("target_name") or "") if index else None) \
            or named_ids.get(((r.get("source_id") or None), state_service._name_key(r.get("target_name"))))
        key_t = tid or state_service._name_key(r.get("target_name"))
        if not key_t:
            continue
        groups.setdefault((r.get("source_id") or None, key_t), []).append(r)
    out = []
    for (src, tgt), recs in groups.items():
        if len(recs) > 1:
            out.append({"source_id": src, "target": tgt, "records": [
                {"id": r["id"], "target_id": r.get("target_id"), "target_name": r.get("target_name"), "axes": r.get("axes"),
                 "label": r.get("label"), "history_count": len(r.get("history") or []),
                 "last_change": (r.get("history") or [{}])[-1].get("at")} for r in recs]})
    return out


def merge_records(state: dict[str, Any], keep_id: str, drop_ids: list[str]) -> tuple[dict[str, Any], str]:
    """Explicit, owner-confirmed merge (never automatic): ``keep_id`` keeps its values; the others' histories are merged
    chronologically with provenance and their values recorded in a history note (never summed). Saved as a new state
    version, so Undo restores the previous state exactly."""
    s = state_service.normalize(json.loads(json.dumps(state)))
    keep = next((r for r in s["relationships"] if r.get("id") == keep_id), None)
    drops = [r for r in s["relationships"] if r.get("id") in set(drop_ids) and r.get("id") != keep_id]
    if keep is None or not drops:
        raise ValueError("Choose the record to keep and at least one other record.")
    for d in drops:
        if (d.get("source_id") or None) != (keep.get("source_id") or None):
            raise ValueError("Records with different directions are different relationships and cannot be merged.")
        if d.get("target_id") and keep.get("target_id") and d["target_id"] != keep["target_id"]:
            raise ValueError("These records are about different characters.")
    hist = list(keep.get("history") or [])
    for d in drops:
        hist += [{**h, "merged_from": d["id"]} for h in d.get("history") or []]
        vals = ", ".join(f"{k} {v}" for k, v in (d.get("axes") or {}).items())
        hist.append({"at": now_iso(), "source": "merge", "change": f"Merged duplicate record “{d.get('target_name')}” "
                     f"(its values were: {vals or 'none'}; label “{d.get('label') or ''}”) — values kept from the chosen record",
                     "merged_from": d["id"], "merged_values": d.get("axes"), "merged_note": d.get("note") or ""})
        if not keep.get("target_id") and d.get("target_id"):
            keep["target_id"] = d["target_id"]
    keep["history"] = sorted(hist, key=lambda h: str(h.get("at") or ""))[-80:]
    s["relationships"] = [r for r in s["relationships"] if r not in drops]
    return s, f"Merged {len(drops)} duplicate relationship record(s) into “{keep.get('target_name')}”"


def lore_relationships(db: Session, world_id: str | None, character_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Initial (lore) relationships between canonical character ids — read-only background, never numbers: the pack's
    ``characters/relationships.json`` (stored verbatim at import) plus each character's ``relationship_notes``. Story
    events change relationships only through the directional story-state records (``source_id`` -> ``target_id``)."""
    from ..models import LoreDocument, LoreEntity

    if not world_id:
        return []
    chars = {e.entity_id: e for e in db.scalars(select(LoreEntity).where(LoreEntity.world_id == world_id,
                                                                         LoreEntity.category == "character"))}
    out: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(src: Any, tgt: Any, kind: Any, conf: Any, where: str) -> None:
        if src in chars and tgt in chars and src != tgt and kind:
            key = (src, tgt, str(kind))
            out.setdefault(key, {"source_id": src, "source_name": chars[src].name, "target_id": tgt,
                                 "target_name": chars[tgt].name, "type": str(kind).replace("_", " "),
                                 "confidence": conf or "unknown", "origin": "lore", "lore_source": where})

    doc = db.scalar(select(LoreDocument).where(LoreDocument.world_id == world_id,
                                               LoreDocument.rel_path == "characters/relationships.json"))
    if doc and doc.content:
        try:
            for r in (json.loads(doc.content).get("relationships") or []):
                if isinstance(r, dict):
                    add(r.get("from"), r.get("to"), r.get("type"), r.get("confidence"), doc.rel_path)
        except ValueError:
            pass  # the import report already lists unreadable files
    for cid, e in chars.items():
        for n in (e.data_json or {}).get("relationship_notes") or []:
            if isinstance(n, dict):
                add(cid, n.get("target_id"), n.get("type"), n.get("confidence"), f"{e.file} relationship_notes")
    rows = list(out.values())
    if character_ids is not None:
        rows = [r for r in rows if r["source_id"] in character_ids or r["target_id"] in character_ids]
    return rows


def payload_for(change: dict[str, Any], index: EntityIndex) -> dict[str, Any]:
    """State payload for one validated change: NPC -> protagonist uses the classic per-NPC record (no ``source_id``)."""
    src, tgt = change["source_id"], change["target_id"]
    base = {"axis": change["dimension"], "delta": change["delta"], "reason": change.get("evidence", ""),
            "evidence": change.get("evidence", ""), "impact": change.get("impact", "minor")}
    if tgt == PROTAGONIST:
        return {**base, "target_id": src, "target_name": index.name(src)}
    return {**base, "source_id": src, "source_name": index.name(src), "target_id": tgt, "target_name": index.name(tgt)}


def _auto_entries(state: dict[str, Any]):
    for rel in state.get("relationships") or []:
        for h in rel.get("history") or []:
            if h.get("auto") and not h.get("reverted_at") and h.get("delta"):
                yield rel, h


def _expected(rel: dict[str, Any], h: dict[str, Any]) -> float | None:
    """The value the axis should have now if only recorded changes touched it since ``h``: its result plus every later
    recorded delta on the same axis (reverts included). ``None`` for entries from before values were recorded."""
    hist = rel.get("history") or []
    if h.get("new") is None or h not in hist:
        return None
    later = hist[hist.index(h) + 1:]
    return float(h["new"]) + sum(float(x.get("delta") or 0) for x in later if x.get("axis") == h.get("axis"))


def _revert(state: dict[str, Any], rel: dict[str, Any], h: dict[str, Any], why: str) -> dict[str, Any]:
    expected = _expected(rel, h)
    current = (rel.get("axes") or {}).get(h["axis"])
    if expected is not None and current is not None and float(current) != expected:
        # the player edited this value by hand after the automatic change (manual edits replace the value without a
        # history entry): never silently change their number — record that the automatic change was not undone
        h["reverted_at"], h["revert_skipped"] = now_iso(), "the value was edited by hand afterwards"
        who = f"{rel.get('source_name') or rel['source_id']} → {rel['target_name']}" if rel.get("source_id") else rel.get("target_name")
        rel.setdefault("history", []).append({"at": now_iso(), "source": "analysis_revert", "message_id": h.get("message_id"),
                                              "axis": h["axis"], "delta": 0, "reverts": h.get("message_id"), "reason": why,
                                              "change": f"{who}: automatic {h['axis']} {float(h['delta']):+g} not undone — "
                                                        "kept your manual value"})
        return state
    payload = {"axis": h["axis"], "delta": -float(h["delta"]), "reason": why, "reverts": h.get("message_id"),
               "target_id": rel.get("target_id"), "target_name": rel.get("target_name")}
    if rel.get("source_id"):
        payload.update(source_id=rel["source_id"], source_name=rel.get("source_name"))
    h["reverted_at"] = now_iso()
    new, _ = state_service.apply_change(state, "relationship", payload, source="analysis_revert", message_id=h.get("message_id"))
    return new


def revert_message(db: Session, story: Story, branch: MessageBranch, message_ids: set[str], why: str) -> int:
    """Revert the automatic changes that came from ``message_ids`` on this branch (history kept). Returns the count."""
    row = state_service.current(db, branch.id)
    if row is None:
        return 0
    state = state_service.normalize(json.loads(json.dumps(row.state_json)))
    n = 0
    while True:
        # re-found in the *current* state each time: a numeric revert returns a new copy, and marking an entry of the
        # old copy as reverted was lost (v1.4 fix: a reply with two automatic changes could have one reverted twice)
        nxt = next(((rel, h) for rel, h in _auto_entries(state) if h.get("message_id") in message_ids), None)
        if nxt is None:
            break
        state = _revert(state, *nxt, why)
        n += 1
    if n:
        state_service.save(db, story.id, branch.id, state, source="analysis_revert", summary=f"Reverted {n} automatic relationship change(s): {why}")
    return n


def reconcile(db: Session, story: Story, branch: MessageBranch, also: set[str] | None = None) -> int:
    """Revert automatic changes whose source reply is no longer part of this branch's story (or is listed in ``also``,
    e.g. a reply whose text was edited). Approved changes are never touched here."""
    live = story_tree.live_path_ids(db, branch)
    row = state_service.current(db, branch.id)
    if row is None:
        return 0
    stale = {h.get("message_id") for _, h in _auto_entries(state_service.normalize(row.state_json))
             if h.get("message_id") and (h["message_id"] not in live or h["message_id"] in (also or set()))}
    return revert_message(db, story, branch, stale, "its source reply was changed or is no longer part of the story") if stale else 0


def apply_from_analysis(db: Session, story: Story, branch: MessageBranch, message_id: str, changes: list[dict[str, Any]],
                        index: EntityIndex, mode: str) -> list[dict[str, Any]]:
    """Apply/propose/drop validated changes for one analysed reply. Idempotent per reply: earlier automatic changes from
    the same reply are reverted first, and proposals are deduplicated by change identity."""
    from .extraction import _change_identity

    if mode == "off":  # before the revert: analysing a reply again must not undo changes it made while tracking was on
        return []
    outcomes: list[dict[str, Any]] = []
    revert_message(db, story, branch, {message_id}, "the reply was analysed again")
    row = state_service.current(db, branch.id)
    state = state_service.normalize(json.loads(json.dumps(row.state_json))) if row else state_service.normalize({})
    applied = []
    known_props = {_change_identity(branch.id, p.kind, p.payload_json or {}, p.source_message_ids_json or [])
                   for p in db.scalars(select(StateProposal).where(StateProposal.branch_id == branch.id))}
    difficulty = difficulty_of(story.settings_json)
    for c in changes:
        # v1.5 difficulty: the proposed delta is scaled deterministically (classification still uses the proposal)
        scaled = scale_delta(int(c["delta"]), c.get("impact", "minor"), difficulty)
        c = {**c, "proposed_delta": c["delta"], "delta": scaled, "difficulty": difficulty}
        payload = {**payload_for(c, index), "proposed_delta": c["proposed_delta"], "difficulty": difficulty}
        small = abs(c["proposed_delta"]) <= AUTO_MAX_DELTA and c.get("impact") != "major"
        if c["confidence"] < DROP_BELOW_CONFIDENCE:
            outcomes.append({**c, "status": "dropped", "reason": "low confidence"})
        elif scaled == 0:
            outcomes.append({**c, "status": "dropped", "reason": f"absorbed by the {difficulty.capitalize()} difficulty (minor setback)"})
        elif mode == "auto_conservative" and small and c["confidence"] >= AUTO_MIN_CONFIDENCE and c.get("evidence_verified"):
            state, summary = state_service.apply_change(state, "relationship", {**payload, "auto": True},
                                                        source="analysis_auto", message_id=message_id)
            applied.append(summary)
            outcomes.append({**c, "status": "applied", "summary": summary})
        else:
            ident = _change_identity(branch.id, "relationship", payload, [message_id])
            if ident not in known_props:
                known_props.add(ident)
                db.add(StateProposal(story_id=story.id, branch_id=branch.id, kind="relationship", payload_json=payload,
                                     rationale=c.get("evidence") or "", source_message_ids_json=[message_id],
                                     confidence=c["confidence"], dedupe_key=ident))
            outcomes.append({**c, "status": "proposed", "reason": "major or uncertain change: review it in the queue"
                             if mode == "auto_conservative" else "review mode"})
    if applied:
        state_service.save(db, story.id, branch.id, state, source="analysis_auto", summary="; ".join(applied)[:2000],
                           message_id=message_id)
    return outcomes
