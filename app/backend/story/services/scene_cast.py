"""Who is physically in the scene (v1.5): ``scene.present`` maintained from scene analysis.

Before v1.5 nothing updated ``scene.present`` automatically (only accepted memory-capture proposals or manual edits), so a
silent Serena standing next to Lucia had no presence and no portrait. Now the analysis of the branch head reports who is
present (with a quote found in the reply) and who leaves; this module applies it to the versioned scene:

* present characters are added; characters reported as leaving are removed;
* when the reply moves the scene to another location, the previous cast is replaced by the reported one (v1.6: a
  reworded place or a spot inside the same place is not a move, so silent characters stay);
* a character who is only *mentioned* is never added (presence ≠ mention ≠ speaking);
* only canonical character ids are stored (never raw names such as "player").

Each update is recorded in ``scene.presence_history`` with its reply and reverted when the reply leaves the story
(regenerated, deleted, edited, alternative switched) — the same pattern as the in-story clock (``world_state``). A later
manual edit of the cast is never overwritten by a revert.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import Message, MessageBranch, Story, now_iso
from . import state_service, story_tree
from .entities import EntityIndex, norm

PLACE_FILLER = set("the and near next inside within toward towards moving back front side area part its".split())
# what shows a gathering is under way: a lesson for a class, a meeting/session for any other kind
MEETING = re.compile(r"\b(meeting|meetings|session|sessions|council|assembly|gathering|briefing|audience|rehearsal|"
                     r"training|drill|réunion|séance|conseil)\b", re.I)
LESSON = re.compile(r"\b(class|classes|classroom|lesson|lessons|lecture|lectures|seminar|practical|cours|classe|leçon|"
                    r"amphi|amphithéâtre)\b", re.I)
QUIET_AFTER = 2  # replies without speaking or visibly reacting before a character counts as quiet
MAX_QUIET = 2


def same_place(a: Any, b: Any) -> bool:
    """True unless two descriptions are clearly different places: "library" / "library, second level" and a rewording
    are the same room. A cast is only replaced by a real move."""
    words = lambda s: {w for w in re.findall(r"[^\W_]+", norm(str(s or ""))) if w not in PLACE_FILLER}  # noqa: E731
    x, y = words(a), words(b)
    return not x or not y or x <= y or y <= x or len(x & y) / len(x | y) >= 0.7


def lesson_under_way(active_class: dict[str, Any] | None, location: str, recent: str, present: list[str]) -> bool:
    """A gathering's roster only fills the room while it is under way: named as one (a lesson for a class, a meeting or
    session for any other kind), or its leader with one of its members. The word "spell" in a corridor conversation does
    not make a class."""
    if not active_class:
        return False
    teacher = (active_class["teacher"] or {}).get("character_id")
    students = {s["character_id"] for s in active_class["students"]}
    words = LESSON if (active_class.get("kind") or "class") == "class" else MEETING
    return bool(words.search(f"{location} {recent}")) or (teacher in present and bool(students & set(present)))


def group_scene(db: Session, state: dict[str, Any], index: EntityIndex, path: list[Message], active_class: dict[str, Any] | None,
                known: set[str], recent: str) -> str:
    """A short note for the narrator when several people share the scene: who is in the room (silent or not), who has been
    quiet, and how attention should move. Narrator knowledge only: it records no presence and no discovery, and a roster
    stays a list of likely attendees. Empty for one-to-one scenes."""
    from .encounters import recent_activity

    sc = state.get("scene") or {}
    present = [c for c in sc.get("present") or [] if c in index.entities and index.entities[c].category == "character"]
    lesson = lesson_under_way(active_class, sc.get("location") or "", recent, present)
    if not lesson and len(present) < 2:
        return ""
    activity = recent_activity(db, path)
    teacher = (active_class["teacher"] or {}).get("character_id") if lesson and active_class else None
    roster = [s["character_id"] for s in active_class["students"] if s["character_id"]] if lesson and active_class else []
    likely = [c for c in roster if c not in present and c not in activity["left"]]
    room = [*present, *likely]
    stamp = f"{sc.get('story_day')}|{sc.get('time')}|{len(path)}"
    # students of the class who have not appeared at all come first: live (v1.6), a note naming them equally with those
    # already on stage left Sia and Rena out again
    quiet = sorted((c for c in room if c != teacher and activity["active"].get(c, QUIET_AFTER) >= QUIET_AFTER),
                   key=lambda c: (c not in likely, hashlib.sha1(f"{stamp}|{c}".encode()).hexdigest()))[:MAX_QUIET]
    is_class = (active_class or {}).get("kind", "class") == "class"
    label = lambda c: index.name(c) + ((" (teaching)" if is_class else " (leading)") if c == teacher else "")  # noqa: E731
    noun = "class" if is_class else (active_class or {}).get("kind") or "gathering"
    lines = [("In the room: " + ", ".join(label(c) for c in present) + "." if present else "")
             + (f" Usually in this {noun}: {', '.join(index.name(c) for c in likely)}." if likely else "")]
    lines.append("- Whoever is here stays here, even in silence, until the story shows them leaving or the scene moves.")
    lines.append("- Attention moves naturally: most replies, one or two others do something small (a glance, an aside, a "
                 "reaction, a word to each other). Nobody has to speak, and there is no taking turns."
                 + (f" Quiet for a while: {', '.join(index.name(c) for c in quiet)}; a small moment for one of them would "
                    "keep the room alive." if quiet else ""))
    lines.append("- They react to events and to each other, not only when addressed, and still leave the protagonist room "
                 "to act.")
    unmet = [c for c in likely if c not in known]
    if unmet:
        lines.append(f"- Not yet met by the protagonist: {', '.join(index.name(c) for c in unmet)}. Show them by look or "
                     "manner; use a name only once it is plausibly learned.")
    return "\n".join(x.strip() for x in lines)


def clean_ids(ids: list[Any], index: EntityIndex) -> list[str]:
    return [c for c in dict.fromkeys(str(x) for x in ids or []) if c in index.entities and index.entities[c].category == "character"]


def apply_from_analysis(db: Session, story: Story, branch: MessageBranch, message_id: str, present: list[str],
                        left: list[str], index: EntityIndex, *, location_changed: bool) -> dict[str, Any] | None:
    """Apply one reply's presence for the branch head; idempotent (an earlier update from the same reply is reverted
    first). Returns the history entry, or None when nothing changed."""
    revert_message(db, story, branch, {message_id}, "the reply was analysed again")
    row = state_service.current(db, branch.id)
    state = state_service.normalize(json.loads(json.dumps(row.state_json)) if row else {})
    sc = state["scene"]
    before = list(sc.get("present") or [])
    present, left = clean_ids(present, index), clean_ids(left, index)
    if location_changed and present:
        after = list(present)
    else:
        after = [c for c in before if c not in left] + [c for c in present if c not in before and c not in left]
    if after == before:
        return None
    sc["present"] = after
    entry = {"message_id": message_id, "at": now_iso(), "auto": True, "before": before, "after": after,
             "added": [c for c in after if c not in before], "removed": [c for c in before if c not in after]}
    sc["presence_history"] = [*(sc.get("presence_history") or []), entry][-60:]
    names = lambda ids: ", ".join(index.name(c) for c in ids)  # noqa: E731
    summary = "Cast: " + "; ".join(x for x in [f"+{names(entry['added'])}" if entry["added"] else "",
                                               f"−{names(entry['removed'])}" if entry["removed"] else ""] if x)
    state_service.save(db, story.id, branch.id, state, source="analysis_auto", summary=summary[:2000], message_id=message_id)
    return entry


def revert_message(db: Session, story: Story, branch: MessageBranch, message_ids: set[str], why: str) -> int:
    row = state_service.current(db, branch.id)
    if row is None:
        return 0
    state = state_service.normalize(json.loads(json.dumps(row.state_json)))
    sc = state["scene"]
    n = 0
    for e in reversed(sc.get("presence_history") or []):
        if e.get("message_id") not in message_ids or e.get("reverted_at"):
            continue
        cur = list(sc.get("present") or [])
        if cur == e.get("after"):
            sc["present"] = list(e.get("before") or [])
        else:  # changed since (later reply or a manual edit): undo only this reply's own additions/removals
            cur = [c for c in cur if c not in (e.get("added") or [])]
            cur += [c for c in (e.get("removed") or []) if c not in cur]
            sc["present"] = cur
            e["revert_partial"] = True
        e["reverted_at"], e["revert_reason"] = now_iso(), why
        n += 1
    if n:
        state_service.save(db, story.id, branch.id, state, source="analysis_revert", summary=f"Cast: reverted {n} update(s): {why}")
    return n


def reconcile(db: Session, story: Story, branch: MessageBranch, also: set[str] | None = None) -> int:
    live = story_tree.live_path_ids(db, branch)
    row = state_service.current(db, branch.id)
    if row is None:
        return 0
    hist = ((row.state_json or {}).get("scene") or {}).get("presence_history") or []
    stale = {e["message_id"] for e in hist if e.get("message_id") and not e.get("reverted_at")
             and (e["message_id"] not in live or e["message_id"] in (also or set()))}
    return revert_message(db, story, branch, stale, "its source reply was changed or is no longer part of the story") if stale else 0
