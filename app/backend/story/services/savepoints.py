"""Named and automatic savepoints: coherent snapshots of a branch's transcript, state, journal, facts and recaps.

Restoring always creates a new branch (optionally archiving the current one), so nothing is destroyed.
"""
from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (EntityFact, ExtractionCursor, Message, MessageBranch, Recap, Savepoint, Story, StoryEvent, now_iso)
from . import state_service, story_tree
from .idmap import remap

SNAPSHOT_VERSION = 1
MAX_AUTO = 20


def snapshot(db: Session, story: Story, branch: MessageBranch) -> dict[str, Any]:
    from .context_builder import visible_events, visible_facts

    msgs = story_tree.path_messages(db, branch.head_message_id, include_deleted=True)
    ids = {m.id for m in msgs}
    st = state_service.current(db, branch.id)
    cur = db.get(ExtractionCursor, branch.id)
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "taken_at": now_iso(),
        "branch": {"id": branch.id, "label": branch.label, "event_sequence": branch.event_sequence},
        "messages": [m.to_dict() for m in msgs],
        "state": {"version": st.state_version if st else 0, "state_json": st.state_json if st else state_service.default_state("none")},
        "events": [e.to_dict() for e in visible_events(db, story, branch, ids)],
        "facts": [f.to_dict() for f in visible_facts(db, story, branch, ids) if f.story_id == story.id],
        "recaps": [r.to_dict() for r in db.scalars(select(Recap).where(Recap.branch_id == branch.id))],
        "cursor": {"last_seq": cur.last_seq if cur else -1},
        "expressions": ((story.settings_json or {}).get("expressions") or {}).get(branch.id, {}),
    }


def create(db: Session, story: Story, branch: MessageBranch, *, label: str, kind: str = "manual", reason: str = "") -> Savepoint:
    sp = Savepoint(story_id=story.id, branch_id=branch.id, label=label[:300] or "Savepoint", kind=kind, reason=reason,
                   snapshot_version=SNAPSHOT_VERSION, snapshot_json=snapshot(db, story, branch))
    db.add(sp)
    db.flush()
    if kind == "auto":  # keep automatic recovery snapshots bounded
        autos = list(db.scalars(select(Savepoint).where(Savepoint.story_id == story.id, Savepoint.kind == "auto")
                                .order_by(Savepoint.created_at.desc())))
        for old in autos[MAX_AUTO:]:
            db.delete(old)
    return sp


def restore(db: Session, story: Story, sp: Savepoint, *, mode: str = "new_branch") -> MessageBranch:
    snap = sp.snapshot_json
    current = story_tree.get_branch(db, story)
    create(db, story, current, label=f"Before restoring '{sp.label}'", kind="auto", reason="savepoint restore")
    mapping: dict[str, str] = {}
    for m in snap["messages"]:
        mapping[m["id"]] = str(uuid.uuid4())
    for e in snap["events"]:
        mapping[e["id"]] = str(uuid.uuid4())
    for f in snap["facts"]:
        mapping[f["id"]] = str(uuid.uuid4())
    for r in snap["recaps"]:
        mapping[r["id"]] = str(uuid.uuid4())
    nb = MessageBranch(story_id=story.id, label=f"Restored: {sp.label}"[:200], parent_branch_id=None,
                       event_sequence=snap["branch"].get("event_sequence", 0))
    db.add(nb)
    db.flush()
    mapping[snap["branch"]["id"]] = nb.id
    head = None
    for m in snap["messages"]:
        d = remap(copy.deepcopy(m), mapping)
        d["branch_id"] = nb.id
        d["request_id"] = None
        if d.get("status") == "streaming":
            d["status"] = "partial"
        db.add(Message(**d))
        head = d["id"]
    db.flush()
    nb.head_message_id = head
    for e in snap["events"]:
        d = remap(copy.deepcopy(e), mapping)
        d["branch_id"] = nb.id
        db.add(StoryEvent(**d))
    for f in snap["facts"]:
        d = remap(copy.deepcopy(f), mapping)
        d["branch_id"] = nb.id if d.get("branch_id") else None
        db.add(EntityFact(**d))
    for r in snap["recaps"]:
        d = remap(copy.deepcopy(r), mapping)
        d["branch_id"] = nb.id
        db.add(Recap(**d))
    state_service.save(db, story.id, nb.id, remap(snap["state"]["state_json"], mapping), source="savepoint_restore",
                       summary=f"Restored from savepoint '{sp.label}' (state v{snap['state']['version']})")
    db.add(ExtractionCursor(branch_id=nb.id, story_id=story.id, last_seq=snap["cursor"]["last_seq"]))
    s = dict(story.settings_json or {})
    ex = dict(s.get("expressions") or {})
    ex[nb.id] = snap.get("expressions") or {}
    s["expressions"] = ex
    story.settings_json = s
    if mode == "replace":
        current.archived = True
    story.active_branch_id = nb.id
    db.flush()
    return nb
