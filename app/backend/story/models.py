"""SQLAlchemy ORM models.

IDs are UUID strings. Timestamps are ISO-8601 UTC strings (portable in exports).
JSON columns hold structured, schema-validated payloads.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}

    def to_dict(self) -> dict[str, Any]:
        return {c.key: getattr(self, c.key) for c in self.__mapper__.column_attrs}


# --------------------------------------------------------------------------- settings
class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=True)


# --------------------------------------------------------------------------- lore
class World(Base):
    __tablename__ = "worlds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    source_path: Mapped[Optional[str]] = mapped_column(Text)
    import_version: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[Optional[str]] = mapped_column(String(40))
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    stats_template: Mapped[str] = mapped_column(String(120), default="fantasy")
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LoreDocument(Base):
    __tablename__ = "lore_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    rel_path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))  # json | md
    title: Mapped[str] = mapped_column(String(300), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    parse_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text)
    import_version: Mapped[int] = mapped_column(Integer, default=1)


class LoreEntity(Base):
    __tablename__ = "lore_entities"
    __table_args__ = (UniqueConstraint("world_id", "category", "entity_id", name="uq_lore_entity"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), default="")
    name: Mapped[str] = mapped_column(String(300))
    aliases_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[Optional[str]] = mapped_column(String(20))
    canon_status: Mapped[Optional[str]] = mapped_column(String(60))
    source_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    file: Mapped[str] = mapped_column(Text, default="")


class LoreChunk(Base):
    __tablename__ = "lore_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    entity_row_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(36))
    entity_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[Optional[str]] = mapped_column(String(20))
    canon_status: Mapped[Optional[str]] = mapped_column(String(60))


class ImportRun(Base):
    __tablename__ = "import_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(30))
    world_id: Mapped[Optional[str]] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="running")
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    finished_at: Mapped[Optional[str]] = mapped_column(String(40))


class LocalCanon(Base):
    __tablename__ = "local_canon"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    world_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    story_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    scope: Mapped[str] = mapped_column(String(20), default="story")  # story | local | global_draft
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    entity_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    overrides_entity_id: Mapped[Optional[str]] = mapped_column(String(200))
    source_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


# --------------------------------------------------------------------------- avatars / stories
class Avatar(Base):
    __tablename__ = "avatars"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    portrait_path: Mapped[Optional[str]] = mapped_column(Text)
    favourite: Mapped[bool] = mapped_column(Boolean, default=False)
    tags_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


class Story(Base):
    __tablename__ = "stories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300))
    world_id: Mapped[Optional[str]] = mapped_column(String(36))
    active_avatar_id: Mapped[Optional[str]] = mapped_column(String(36))
    avatar_snapshot_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    active_branch_id: Mapped[Optional[str]] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | archived | template
    cover_path: Mapped[Optional[str]] = mapped_column(Text)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    archived_at: Mapped[Optional[str]] = mapped_column(String(40))


class MessageBranch(Base):
    __tablename__ = "message_branches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200), default="Main")
    parent_branch_id: Mapped[Optional[str]] = mapped_column(String(36))
    fork_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    head_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_story_request", "story_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    kind: Mapped[str] = mapped_column(String(20), default="story")  # story | ooc | utility | recap
    speaker_character_id: Mapped[Optional[str]] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    command_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="complete")
    request_id: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    edited_at: Mapped[Optional[str]] = mapped_column(String(40))
    deleted_at: Mapped[Optional[str]] = mapped_column(String(40))
    generation_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MessageVersion(Base):
    __tablename__ = "message_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(40), default="edit")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


# --------------------------------------------------------------------------- state
class StoryState(Base):
    __tablename__ = "story_states"
    __table_args__ = (UniqueConstraint("branch_id", "state_version", name="uq_state_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    state_version: Mapped[int] = mapped_column(Integer)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    summary: Mapped[str] = mapped_column(Text, default="")
    message_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class StateProposal(Base):
    __tablename__ = "state_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text, default="")
    source_message_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | accepted | rejected | failed
    extraction_run_id: Mapped[Optional[str]] = mapped_column(String(36))
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(80), index=True)  # re-extraction never re-proposes
    applied_state_version: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    resolved_at: Mapped[Optional[str]] = mapped_column(String(40))


# --------------------------------------------------------------------------- scene presentation & discovery
class TurnAnalysis(Base):
    """Post-turn metadata for one assistant message: ordered speakers/expressions and three suggested next actions.

    Kept out of the visible transcript; tied to one message (and therefore to one branch/alternative)."""
    __tablename__ = "turn_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), unique=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | succeeded | failed | skipped
    # [{"character_id", "expression": 1-6, "evidence", "confidence"}] in speaking order
    speakers_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    active_speaker_id: Mapped[Optional[str]] = mapped_column(String(200))
    # exactly three [{"id", "label", "description"}] or empty with suggestions_error
    suggestions_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    suggestions_error: Mapped[Optional[str]] = mapped_column(Text)
    discoveries_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text)
    provider_id: Mapped[Optional[str]] = mapped_column(String(36))
    model_id: Mapped[Optional[str]] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)
    # v2 (migration 0005): [{"character_id", "expression", "beat": speaking|reacting, "anchor", "paragraph"}] in reading
    # order; [{"character_id", "text"}] exact dialogue substrings of the reply; relationship changes with their outcome
    # (applied / proposed / dropped); one diagnostics entry per provider attempt (no prompts, no secrets)
    beats_json: Mapped[Optional[list[Any]]] = mapped_column(JSON)
    dialogue_json: Mapped[Optional[list[Any]]] = mapped_column(JSON)
    relationships_json: Mapped[Optional[list[Any]]] = mapped_column(JSON)
    diagnostics_json: Mapped[Optional[list[Any]]] = mapped_column(JSON)
    schema_version: Mapped[Optional[int]] = mapped_column(Integer)


class CharacterDiscovery(Base):
    """Append-only record of what the protagonist knows about a character in one story.

    Visible on a branch when its source message is on the branch's path (manual records without a message: when the
    branch is in the lineage). The latest visible record per character wins; ``removed`` hides an accidental discovery."""
    __tablename__ = "character_discoveries"
    __table_args__ = (UniqueConstraint("story_id", "dedupe_key", name="uq_discovery_dedupe"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    character_id: Mapped[str] = mapped_column(String(200), index=True)
    character_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20))  # rumored | encountered | known | removed
    source_message_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    capture_method: Mapped[str] = mapped_column(String(40), default="analysis")  # analysis | manual
    dedupe_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


# --------------------------------------------------------------------------- journal & memory
class StoryEvent(Base):
    __tablename__ = "story_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    branch_sequence: Mapped[int] = mapped_column(Integer, default=0)
    in_world_time: Mapped[Optional[str]] = mapped_column(String(200))
    chapter_id: Mapped[Optional[str]] = mapped_column(String(120))
    scene_id: Mapped[Optional[str]] = mapped_column(String(120))
    order_key: Mapped[Optional[str]] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(60), default="other")
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    entity_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    unresolved_entities_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    location_id: Mapped[Optional[str]] = mapped_column(String(200))
    tags_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    importance: Mapped[int] = mapped_column(Integer, default=3)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    verification_status: Mapped[str] = mapped_column(String(40), default="recorded_unverified")
    evidence_kind: Mapped[str] = mapped_column(String(40), default="witnessed")
    source_message_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    evidence_excerpt: Mapped[Optional[str]] = mapped_column(Text)
    capture_method: Mapped[str] = mapped_column(String(40), default="manual")
    extraction_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    related_event_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    supersedes_event_id: Mapped[Optional[str]] = mapped_column(String(36))
    superseded_by_event_id: Mapped[Optional[str]] = mapped_column(String(36))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[Optional[str]] = mapped_column(Text)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


class EntityFact(Base):
    __tablename__ = "entity_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    branch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    scope: Mapped[str] = mapped_column(String(20), default="story")
    category: Mapped[str] = mapped_column(String(30), default="fact")  # fact | memory
    subject_entity_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    subject_label: Mapped[Optional[str]] = mapped_column(String(200))
    predicate: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text)
    tags_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # established | witnessed | claim | rumour | belief | plan | hypothetical | dream_vision | secret
    fact_kind: Mapped[str] = mapped_column(String(30), default="established")
    belief_holder_id: Mapped[Optional[str]] = mapped_column(String(200))
    # {"known_by": [...], "hidden_from": [...], "learned_via": {"<entity>": "<event id or how>"}}
    knowledge_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")  # candidate | active | disputed | superseded | rejected
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    importance: Mapped[int] = mapped_column(Integer, default=3)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from_event_id: Mapped[Optional[str]] = mapped_column(String(36))
    valid_until_event_id: Mapped[Optional[str]] = mapped_column(String(36))
    superseded_by_fact_id: Mapped[Optional[str]] = mapped_column(String(36))
    contradicts_fact_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source_event_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source_message_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    capture_method: Mapped[str] = mapped_column(String(40), default="manual")
    user_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    extraction_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


class MemoryExtractionRun(Base):
    __tablename__ = "memory_extraction_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    start_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    end_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    start_seq: Mapped[int] = mapped_column(Integer, default=0)
    end_seq: Mapped[int] = mapped_column(Integer, default=0)
    capture_method: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | succeeded | failed | cancelled | skipped
    provider_id: Mapped[Optional[str]] = mapped_column(String(36))
    model_id: Mapped[Optional[str]] = mapped_column(String(200))
    error_summary: Mapped[Optional[str]] = mapped_column(Text)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    finished_at: Mapped[Optional[str]] = mapped_column(String(40))


class ExtractionCursor(Base):
    __tablename__ = "extraction_cursors"
    branch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    last_seq: Mapped[int] = mapped_column(Integer, default=-1)
    last_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    assistant_turns_since: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Recap(Base):
    __tablename__ = "recaps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="rolling")  # rolling | chapter
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, default="")
    start_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    end_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    start_seq: Mapped[Optional[int]] = mapped_column(Integer)
    end_seq: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="candidate")  # candidate | active | superseded | rejected
    source: Mapped[str] = mapped_column(String(30), default="generated")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


class MemorySummary(Base):
    """v0.5 (phase 7): the AI's own memory of the story, written automatically while playing.

    A "scene" summary covers a short run of consecutive messages (the ones memory capture just read, or a catch-up
    request). It is valid on any path that contains all of ``message_ids_json``, so regenerated replies and other
    branches never see a summary of text they do not have. Editing a covered message marks it ``stale``; it is then
    written again. Level "chapter" (phase 7.2) merges scene summaries. ``data_json`` holds extras (later steps)."""
    __tablename__ = "memory_summaries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    level: Mapped[str] = mapped_column(String(20), default="scene")  # scene | chapter
    content: Mapped[str] = mapped_column(Text, default="")
    message_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    start_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    end_message_id: Mapped[Optional[str]] = mapped_column(String(36))
    start_seq: Mapped[int] = mapped_column(Integer, default=0)
    end_seq: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | stale | superseded
    source: Mapped[str] = mapped_column(String(30), default="capture")  # capture | summary | edited
    parent_id: Mapped[Optional[str]] = mapped_column(String(36))  # the chapter that absorbed it (phase 7.2)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_id: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


class Savepoint(Base):
    __tablename__ = "savepoints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36))
    label: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20), default="manual")  # manual | auto
    reason: Mapped[str] = mapped_column(String(200), default="")
    snapshot_version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


# --------------------------------------------------------------------------- notes / commands
class UserNote(Base):
    __tablename__ = "user_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(20))  # global | story
    story_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


class SlashCommand(Base):
    __tablename__ = "slash_commands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), index=True)
    aliases_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="prompt")  # prompt | local_action | hybrid
    action: Mapped[Optional[str]] = mapped_column(String(60))
    output_target: Mapped[str] = mapped_column(String(20), default="chat")  # chat | utility | ooc
    scope: Mapped[str] = mapped_column(String(20), default="global")
    story_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(60), default="General")
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


# --------------------------------------------------------------------------- providers
class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_type: Mapped[str] = mapped_column(String(30))  # mock | ollama | anthropic | openai | openai_compat
    display_name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[Optional[str]] = mapped_column(Text)
    model_listing_mode: Mapped[str] = mapped_column(String(20), default="auto")  # auto | manual
    nonsecret_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    secret_reference: Mapped[Optional[str]] = mapped_column(String(200))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(300))
    generation_settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_limit: Mapped[Optional[int]] = mapped_column(Integer)
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_favourite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)




class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    world_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    role_id: Mapped[str] = mapped_column(String(80), index=True)
    character_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(300))
    aliases_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso, onupdate=now_iso)


# --------------------------------------------------------------------------- assets
class AssetRoot(Base):
    __tablename__ = "asset_roots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="folder")  # folder | uploaded
    label: Mapped[str] = mapped_column(String(200), default="")
    # v0.5: the world whose portraits these are (a lore pack's image folder). None = shared by every world (folders
    # the player added by hand). Portraits are matched and looked up per world, so two packs can both have a "lily".
    world_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    links_file_info_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    last_scan_at: Mapped[Optional[str]] = mapped_column(String(40))


class AssetManifestEntry(Base):
    __tablename__ = "asset_manifest"
    __table_args__ = (UniqueConstraint("root_id", "rel_path", name="uq_asset_path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    root_id: Mapped[str] = mapped_column(ForeignKey("asset_roots.id", ondelete="CASCADE"), index=True)
    rel_path: Mapped[str] = mapped_column(Text)
    slug: Mapped[Optional[str]] = mapped_column(String(200))
    character_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    slot: Mapped[Optional[int]] = mapped_column(Integer)
    ext: Mapped[str] = mapped_column(String(10), default="")
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    readable: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="unmatched")  # matched | override | ambiguous | unmatched | invalid | ignored
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    match_reason: Mapped[str] = mapped_column(Text, default="")
    candidates_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    remote_url: Mapped[Optional[str]] = mapped_column(Text)
    scanned_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class AssetOverride(Base):
    __tablename__ = "asset_overrides"
    __table_args__ = (UniqueConstraint("root_id", "rel_path", name="uq_asset_override"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    root_id: Mapped[str] = mapped_column(ForeignKey("asset_roots.id", ondelete="CASCADE"), index=True)
    rel_path: Mapped[str] = mapped_column(Text)
    character_id: Mapped[Optional[str]] = mapped_column(String(200))
    slot: Mapped[Optional[int]] = mapped_column(Integer)
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class SlugOverride(Base):
    __tablename__ = "slug_overrides"
    slug: Mapped[str] = mapped_column(String(200), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(200))
