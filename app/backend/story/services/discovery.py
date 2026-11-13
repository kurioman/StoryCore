"""Per-story character discovery: which characters the protagonist has actually heard of, met or come to know.

The lore catalogue is not the roster. Records are append-only and tied to the message that established them, so a
branch only sees discoveries from its own path (same visibility rule as journal events), unselected alternatives never
leak, and replaying analysis for the same message cannot create duplicates (unique dedupe key per story).
Discovery status is separate from relationship state (ally/hostile live in the story-state relationships).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import CharacterDiscovery, Message, MessageBranch, Story
from . import story_tree

STATUSES = ("rumored", "encountered", "known")
RANK = {"removed": 0, "rumored": 1, "encountered": 2, "known": 3}


def _visible(db: Session, story: Story, branch: MessageBranch) -> list[CharacterDiscovery]:
    path = story_tree.live_path_ids(db, branch)
    lineage = set(story_tree.lineage_branch_ids(db, branch))
    rows = db.scalars(select(CharacterDiscovery).where(CharacterDiscovery.story_id == story.id))
    return [r for r in rows if (r.source_message_id in path if r.source_message_id else r.branch_id in lineage)]


def history(db: Session, story: Story, branch: MessageBranch, character_id: str | None = None) -> list[CharacterDiscovery]:
    rows = sorted(_visible(db, story, branch), key=lambda r: (r.created_at, r.id))
    return [r for r in rows if character_id is None or r.character_id == character_id]


def roster(db: Session, story: Story, branch: MessageBranch) -> dict[str, CharacterDiscovery]:
    """Latest visible record per character, without removed ones."""
    latest: dict[str, CharacterDiscovery] = {}
    for r in history(db, story, branch):
        latest[r.character_id] = r
    return {cid: r for cid, r in latest.items() if r.status != "removed"}


def record(db: Session, story: Story, branch: MessageBranch, *, character_id: str, name: str, status: str,
           source_message_id: str | None, evidence: str = "", method: str = "analysis") -> CharacterDiscovery | None:
    """Add a discovery record. Automatic records never downgrade (a rumour after a meeting changes nothing) and are
    idempotent per (character, status, message). Manual records always apply (corrections, removals)."""
    if status not in (*STATUSES, "removed"):
        raise ValueError(f"Unknown discovery status '{status}'.")
    if method != "manual":
        cur = roster(db, story, branch).get(character_id)
        if cur is not None and RANK[cur.status] >= RANK[status]:
            return None
        key = f"{character_id}|{status}|{source_message_id or branch.id}"
    else:
        from ..models import new_id
        key = f"manual|{character_id}|{status}|{new_id()}"
    if db.scalar(select(CharacterDiscovery.id).where(CharacterDiscovery.story_id == story.id, CharacterDiscovery.dedupe_key == key)):
        return None
    row = CharacterDiscovery(story_id=story.id, branch_id=branch.id, character_id=character_id, character_name=name[:200],
                             status=status, source_message_id=source_message_id, evidence=(evidence or "")[:500],
                             capture_method=method, dedupe_key=key)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:  # a concurrent replay recorded the same discovery
        return None
    return row


def to_dict(r: CharacterDiscovery, db: Session | None = None) -> dict[str, Any]:
    d = r.to_dict()
    if db is not None and r.source_message_id:
        m = db.get(Message, r.source_message_id)
        d["source_seq"] = m.seq if m else None
    return d
