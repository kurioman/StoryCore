"""Message tree and branch helpers.

Messages form a tree via ``parent_id``. A branch points at a head message; its transcript is the
chain from the head back to the root. Regenerating a leaf adds a sibling inside the same branch;
regenerating or branching from an earlier point creates a new branch, preserving the old one.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Message, MessageBranch, Story, now_iso


class NotFound(Exception):
    pass


def get_story(db: Session, story_id: str) -> Story:
    s = db.get(Story, story_id)
    if s is None:
        raise NotFound("Story not found")
    return s


def get_branch(db: Session, story: Story, branch_id: str | None = None) -> MessageBranch:
    b = db.get(MessageBranch, branch_id or story.active_branch_id)
    if b is None or b.story_id != story.id:
        raise NotFound("Branch not found")
    return b


def path_messages(db: Session, head_id: str | None, include_deleted: bool = False) -> list[Message]:
    """Messages from root to ``head_id`` (inclusive)."""
    if not head_id:
        return []
    by_id: dict[str, Message] = {}
    head = db.get(Message, head_id)
    if head is None:
        return []
    # pull the whole story once; trees are small enough and this avoids N queries
    for m in db.scalars(select(Message).where(Message.story_id == head.story_id)):
        by_id[m.id] = m
    chain: list[Message] = []
    cur: Message | None = by_id.get(head_id)
    seen = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        chain.append(cur)
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    chain.reverse()
    if not include_deleted:
        chain = [m for m in chain if m.deleted_at is None]
    return chain


def path_ids(db: Session, branch: MessageBranch) -> set[str]:
    return {m.id for m in path_messages(db, branch.head_message_id, include_deleted=True)}


def live_path_ids(db: Session, branch: MessageBranch) -> set[str]:
    """Ids on the branch path that are still canonical (deleted messages are not evidence for anything)."""
    return {m.id for m in path_messages(db, branch.head_message_id)}


def lineage_branch_ids(db: Session, branch: MessageBranch) -> list[str]:
    out, cur, seen = [], branch, set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        out.append(cur.id)
        cur = db.get(MessageBranch, cur.parent_branch_id) if cur.parent_branch_id else None
    return out


def siblings(db: Session, msg: Message) -> list[Message]:
    q = select(Message).where(Message.story_id == msg.story_id, Message.deleted_at.is_(None))
    q = q.where(Message.parent_id == msg.parent_id) if msg.parent_id else q.where(Message.parent_id.is_(None))
    return list(db.scalars(q.order_by(Message.created_at)))


def has_children(db: Session, msg_id: str) -> bool:
    return db.scalar(select(Message.id).where(Message.parent_id == msg_id).limit(1)) is not None


def append_message(db: Session, story: Story, branch: MessageBranch, *, role: str, content: str, kind: str = "story",
                   status: str = "complete", parent_id: str | None = "__head__", **extra) -> Message:
    parent_id = branch.head_message_id if parent_id == "__head__" else parent_id
    parent = db.get(Message, parent_id) if parent_id else None
    m = Message(story_id=story.id, branch_id=branch.id, parent_id=parent_id, seq=(parent.seq + 1) if parent else 0,
                role=role, kind=kind, content=content, status=status, **extra)
    db.add(m)
    db.flush()
    branch.head_message_id = m.id
    story.updated_at = now_iso()
    return m


def create_branch(db: Session, story: Story, *, from_branch: MessageBranch, fork_message_id: str | None, label: str) -> MessageBranch:
    b = MessageBranch(story_id=story.id, label=label, parent_branch_id=from_branch.id, fork_message_id=fork_message_id,
                      head_message_id=fork_message_id, event_sequence=0)
    db.add(b)
    db.flush()
    return b


def next_event_sequence(db: Session, branch: MessageBranch) -> int:
    branch.event_sequence = (branch.event_sequence or 0) + 1
    return branch.event_sequence
