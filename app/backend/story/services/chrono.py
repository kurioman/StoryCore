"""Per-reply chronology header (v1.5.1): the in-story day, date, weekday, time, weather and place of each narrated reply.

The header is built by the app from validated world state — never written by the model and never stored in the reply's
text, so the context sent back to the narrator contains the scene exactly once (the CURRENT SCENE block) and no header
lines. Each assistant reply carries its own snapshot in ``generation_metadata_json["chrono"]`` (no schema change):

* ``before_reply`` — taken when generation starts: the last validated state, shown while the reply streams;
* ``analysis``     — replaced once scene analysis of that reply (as the branch head) has applied what the reply
  established (a move, the evening bells, rain, the next morning);
* ``manual``       — the player corrected the current scene; the latest reply's header follows that correction.

Older replies never change when later replies move the clock: past headers keep their own values. Replies written
before v1.5.1 have no snapshot; their header is *reconstructed* read-only from the versioned state history (the last
state saved on that reply's branch before the next reply started), or reported as not recorded — never invented.

D1 is the first in-story day; ``story_day`` counts days (D5 = four days after D1). Unknown stays unknown.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Message, MessageBranch, Story, StoryState, now_iso
from . import state_service, story_tree

FIELDS = ("story_day", "weekday", "day", "month", "year", "date_text", "time", "weather", "location")
SCENE_KEYS = ("story_day", "weekday", "day", "month", "year", "date", "time", "weather", "location")


def snapshot(sc: dict[str, Any], basis: str, *, version: int | None = None, day_one: bool = False) -> dict[str, Any]:
    """Header values from a scene. ``day_one``: an unknown day counts as D1 (the story has been tracked from its start)."""
    day = sc.get("story_day")
    return {"story_day": day if isinstance(day, int) and day > 0 else (1 if day_one else None),
            "weekday": sc.get("weekday") or None, "day": sc.get("day") if isinstance(sc.get("day"), int) else None,
            "month": sc.get("month") or None, "year": sc.get("year") if isinstance(sc.get("year"), int) else None,
            "date_text": sc.get("date") or None, "time": state_service.strip_day_token(sc.get("time")) or None,
            "weather": sc.get("weather") or None,
            "location": sc.get("location") or None, "basis": basis, "at": now_iso(), "state_version": version}


def scene_changed(old: dict[str, Any] | None, new: dict[str, Any] | None) -> bool:
    return any((old or {}).get(k) != (new or {}).get(k) for k in SCENE_KEYS)


def record(m: Message, sc: dict[str, Any], basis: str, *, version: int | None = None, day_one: bool = False) -> dict[str, Any]:
    snap = snapshot(sc, basis, version=version, day_one=day_one)
    md = dict(m.generation_metadata_json or {})
    md["chrono"] = snap
    m.generation_metadata_json = md  # reassigned so the JSON column is flagged dirty
    return snap


def tracked_from_start(db: Session, m: Message) -> bool:
    """True when every earlier narrated reply on this reply's path has a v1.5.1 snapshot (or there is none): an unknown
    day is then D1. A story that ran before day tracking keeps an unknown day until the player sets it."""
    for p in story_tree.path_messages(db, m.parent_id, include_deleted=False) if m.parent_id else []:
        if p.role == "assistant" and p.kind == "story" and "chrono" not in (p.generation_metadata_json or {}):
            return False
    return True


def record_current(db: Session, m: Message, branch: MessageBranch, basis: str) -> dict[str, Any]:
    row = state_service.current(db, branch.id)
    sc = state_service.normalize(row.state_json if row else {})["scene"]
    return record(m, sc, basis, version=row.state_version if row else None, day_one=tracked_from_start(db, m))


def latest_reply(db: Session, branch: MessageBranch) -> Message | None:
    if not branch.head_message_id:
        return None
    for m in reversed(story_tree.path_messages(db, branch.head_message_id, include_deleted=False)):
        if m.role == "assistant" and m.kind == "story":
            return m
    return None


def follow_manual_edit(db: Session, story: Story, branch: MessageBranch, old_scene: dict[str, Any] | None,
                       new_scene: dict[str, Any] | None) -> dict[str, Any] | None:
    """A manual scene correction updates the header of the latest narrated reply (the scene the player is in)."""
    if not scene_changed(old_scene, new_scene):
        return None
    m = latest_reply(db, branch)
    return record_current(db, m, branch, "manual") if m is not None else None


def attach(db: Session, story: Story, path: list[Message], out: list[dict[str, Any]]) -> None:
    """Put each narrated reply's header on its serialized message (``chrono``): its own snapshot, or a read-only
    reconstruction for replies written before v1.5.1."""
    by_id = {d["id"]: d for d in out}
    replies = [m for m in path if m.role == "assistant" and m.kind == "story" and m.id in by_id
               and not (m.status == "failed" and not (m.content or "").strip())]  # a reply that never started: no header
    legacy = [m for m in replies if "chrono" not in (m.generation_metadata_json or {})]
    rebuilt = reconstruct(db, story, path, legacy) if legacy else {}
    for m in replies:
        snap = (m.generation_metadata_json or {}).get("chrono") or rebuilt.get(m.id) or {"basis": "not_recorded"}
        by_id[m.id]["chrono"] = {k: snap.get(k) for k in (*FIELDS, "basis", "state_version", "at")}
        by_id[m.id]["chrono"]["time"] = state_service.strip_day_token(snap.get("time")) or None  # display only, not stored


def reconstruct(db: Session, story: Story, path: list[Message], legacy: list[Message]) -> dict[str, dict[str, Any]]:
    """Legacy headers from persisted state only: the newest state saved on the reply's own branch before the next
    narrated reply on the path was created (for the last reply: the newest state). Not written back."""
    rows = db.execute(select(StoryState.branch_id, StoryState.state_version, StoryState.created_at, StoryState.state_json)
                      .where(StoryState.story_id == story.id).order_by(StoryState.state_version)).all()
    by_branch: dict[str, list[Any]] = {}
    for r in rows:
        by_branch.setdefault(r.branch_id, []).append(r)
    replies = [m for m in path if m.role == "assistant" and m.kind == "story" and not m.deleted_at]
    nxt = {a.id: b.created_at for a, b in zip(replies, replies[1:])}
    out: dict[str, dict[str, Any]] = {}
    for m in legacy:
        limit = nxt.get(m.id)
        cands = [r for r in by_branch.get(m.branch_id, []) if limit is None or (r.created_at or "") < limit]
        if not cands:
            continue
        r = cands[-1]
        sc = state_service.normalize(r.state_json or {})["scene"]
        out[m.id] = snapshot(sc, "reconstructed", version=r.state_version)
    return out
