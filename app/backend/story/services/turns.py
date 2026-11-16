"""Story turns: send, regenerate, branch, edit, delete — plus post-generation processing."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import EntityFact, ExtractionCursor, Message, MessageBranch, MessageVersion, Story, StoryEvent, now_iso
from . import commands as commands_svc
from . import context_builder, savepoints, settings_service, state_service, story_tree
from .entities import build_index
from .expressions import detect_speaker, suggest_moods
from .runtime import AppContext

log = logging.getLogger(__name__)


class TurnError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _ensure_idle(ctx: AppContext, branch: MessageBranch) -> None:
    if ctx.generations.active_for_branch(branch.id):
        raise TurnError("A response is still being generated on this branch. Stop it or wait for it to finish.", 409)


def _start_generation(ctx: AppContext, db: Session, story: Story, branch: MessageBranch, placeholder: Message,
                      extra_instruction: str | None = None) -> dict[str, Any] | None:
    """Commit first, then build context and start the provider job.

    The player's turn and the reply placeholder are durable before anything that can fail (context build, provider
    resolution). If starting fails, the placeholder is marked ``failed`` with the error and the player turn is kept, so
    the user can retry from the transcript instead of losing their text.
    """
    db.commit()
    marker_filter, immersive_meta = None, None
    try:
        resolved = ctx.resolve(db, ctx.story_profile_id(db, story))
        resolved.story = story
        # v1.5 optional immersive interleaving: only when the story opted in and the player's turn clearly has several
        # quoted lines; the player's message itself is never changed (services/immersive.py)
        anchor = db.get(Message, placeholder.parent_id) if placeholder.parent_id else None
        if (story.settings_json or {}).get("narrative_presentation") == "immersive" and anchor is not None \
                and anchor.role == "user" and anchor.kind == "story" and not anchor.command_json:
            from . import immersive
            seg = immersive.segment(anchor.content)
            if seg["eligible"]:
                from ..models import Avatar
                av = db.get(Avatar, story.active_avatar_id) if story.active_avatar_id else None
                pname = (av.name if av else (story.avatar_snapshot_json or {}).get("name")) or "the protagonist"
                note = immersive.instruction(anchor.content, seg, pname)
                extra_instruction = f"{extra_instruction}\n\n{note}" if extra_instruction else note
                marker_filter = immersive.MarkerFilter(seg, anchor.content, anchor.id)
            immersive_meta = {"mode": "immersive", "status": "streaming" if seg["eligible"] else "classic",
                              "reason": seg["reason"]}
        built = context_builder.build(db, story, branch, context_limit=resolved.profile.context_limit, params=resolved.params,
                                      exclude_message_ids={placeholder.id}, extra_instruction=extra_instruction)
        if built.manifest.get("first_sent_seq") is not None:  # v1.8: the next request keeps this start while it fits
            starts = dict((story.settings_json or {}).get("window_starts") or {})
            starts[branch.id] = built.manifest["first_sent_seq"]
            story.settings_json = {**(story.settings_json or {}), "window_starts": starts}
    except Exception as e:
        db.rollback()
        log.exception("could not start generation for message %s", placeholder.id)
        ph = db.get(Message, placeholder.id)
        ph.status = "failed"
        ph.generation_metadata_json = {"error": {"category": "start_failed", "message": "The reply could not be started; your message is saved. Retry when ready.",
                                                 "details": f"{type(e).__name__}: {str(e)[:300]}"}}
        db.commit()
        return None
    placeholder.generation_metadata_json = {
        "provider_id": resolved.provider.id, "provider_type": resolved.provider.provider_type,
        "provider_name": resolved.provider.display_name, "model_id": resolved.profile.model_id,
        "model_profile_id": resolved.profile.id, "started_at": now_iso(), "context": built.manifest,
        "params": resolved.adapter.filter_params(resolved.params),
        **({"immersive": immersive_meta} if immersive_meta else {}),
    }
    if placeholder.kind == "story":
        # v1.5.1: one chronology header per reply — the last validated scene while it streams, refined by its analysis
        from . import chrono
        chrono.record_current(db, placeholder, branch, "before_reply")
    db.commit()
    ctx.generations.start(placeholder, resolved, built.system, built.messages, marker_filter=marker_filter)
    return built.manifest


def _existing_turn(db: Session, story_id: str, request_id: str) -> dict[str, Any] | None:
    existing = db.scalar(select(Message).where(Message.story_id == story_id, Message.request_id == request_id, Message.role == "user"))
    if existing is None:
        return None
    reply = db.scalar(select(Message).where(Message.parent_id == existing.id, Message.role == "assistant").order_by(Message.created_at))
    return {"user_message_id": existing.id, "assistant_message_id": reply.id if reply else None, "duplicate": True,
            "story_id": story_id, "branch_id": existing.branch_id,
            "assistant_status": reply.status if reply else None}


def send(ctx: AppContext, db: Session, story_id: str, *, content: str, command: dict[str, Any] | None,
         request_id: str | None) -> dict[str, Any]:
    story = story_tree.get_story(db, story_id)
    branch = story_tree.get_branch(db, story)
    if request_id:  # double-click / retry / lost-response protection: the same request never creates a second turn
        dup = _existing_turn(db, story.id, request_id)
        if dup is not None:
            return dup
    _ensure_idle(ctx, branch)
    if not content.strip() and not command:
        raise TurnError("Write something or choose a command.")
    kind = "story"
    command_json = None
    if command:
        cmd = commands_svc.find(db, story.id, command.get("name", "")) if not command.get("id") else None
        if command.get("id"):
            from ..models import SlashCommand
            cmd = db.get(SlashCommand, command["id"])
        if cmd is None:
            raise TurnError(f"Unknown command '/{command.get('name')}'.")
        if cmd.kind == "local_action":
            raise TurnError(f"/{cmd.name} is a local action; it does not send a message.")
        st_row = state_service.current(db, branch.id)
        st = (st_row.state_json if st_row else {}) or {}
        expansion = commands_svc.expand(cmd.template, content, {
            "location": (st.get("scene") or {}).get("location", ""), "player_name": (st.get("player") or {}).get("name", "")})
        command_json = {"id": cmd.id, "name": cmd.name, "expansion": expansion, "output_target": cmd.output_target}
        if cmd.output_target == "ooc":
            kind = "ooc"
    # resolve before persisting so a missing model / consent doesn't leave orphan messages
    ctx.resolve(db, ctx.story_profile_id(db, story))
    try:
        # the unique (story, request_id) index can fire at any write here (appending already flushes), not just at the end
        user = story_tree.append_message(db, story, branch, role="user", content=content.strip(), kind=kind,
                                         command_json=command_json, request_id=request_id)
        placeholder = story_tree.append_message(db, story, branch, role="assistant", content="", kind=kind, status="streaming")
        db.flush()
    except IntegrityError:  # a concurrent request with the same request_id won the race (unique index)
        db.rollback()
        dup = _existing_turn(db, story.id, request_id or "")
        if dup is not None:
            return dup
        raise
    manifest = _start_generation(ctx, db, story, branch, placeholder)
    return {"user_message_id": user.id, "assistant_message_id": placeholder.id, "context": manifest,
            "story_id": story.id, "branch_id": branch.id, "duplicate": False,
            "assistant_status": "streaming" if manifest is not None else "failed"}


def regenerate(ctx: AppContext, db: Session, story_id: str, message_id: str) -> dict[str, Any]:
    """Regenerate an assistant message (or generate a reply to a user message).

    * leaf assistant message → new sibling alternative in the same branch (old one kept)
    * anything with later messages → new branch forked at the parent user message (old branch kept)
    """
    story = story_tree.get_story(db, story_id)
    branch = story_tree.get_branch(db, story)
    _ensure_idle(ctx, branch)
    msg = db.get(Message, message_id)
    if msg is None or msg.story_id != story.id:
        raise TurnError("Message not found.", 404)
    anchor = msg if msg.role == "user" else db.get(Message, msg.parent_id) if msg.parent_id else None
    if anchor is None or anchor.role != "user":
        raise TurnError("Can only regenerate replies to a user message.")
    ctx.resolve(db, ctx.story_profile_id(db, story))
    target_is_leaf = msg.role == "assistant" and not story_tree.has_children(db, msg.id) and branch.head_message_id == msg.id
    user_is_head = msg.role == "user" and branch.head_message_id == msg.id
    created_branch = None
    if target_is_leaf or user_is_head:
        target_branch = branch
    else:
        savepoints.create(db, story, branch, label=f"Before regenerating from #{anchor.seq}", kind="auto",
                          reason="branch regeneration")
        n = db.query(MessageBranch).filter(MessageBranch.story_id == story.id).count()
        target_branch = story_tree.create_branch(db, story, from_branch=branch, fork_message_id=anchor.id,
                                                 label=f"Branch {n + 1} (from #{anchor.seq})")
        state_service.fork(db, story.id, branch, target_branch, anchor)
        _fork_cursor(db, story, branch, target_branch, anchor)
        story.active_branch_id = target_branch.id
        created_branch = target_branch.id
    placeholder = story_tree.append_message(db, story, target_branch, role="assistant", content="", kind=anchor.kind,
                                            status="streaming", parent_id=anchor.id)
    if msg.role == "assistant":
        _flag_stale(db, story, [msg.id], f"Message #{msg.seq} was regenerated")
        from . import relationships, scene_cast, world_state  # automatic changes from the replaced reply leave with it
        relationships.reconcile(db, story, target_branch)
        world_state.reconcile(db, story, target_branch)
        scene_cast.reconcile(db, story, target_branch)
    manifest = _start_generation(ctx, db, story, target_branch, placeholder)
    return {"assistant_message_id": placeholder.id, "branch_id": target_branch.id, "created_branch_id": created_branch,
            "context": manifest}


def branch_from(db: Session, story_id: str, message_id: str, label: str | None = None) -> MessageBranch:
    story = story_tree.get_story(db, story_id)
    branch = story_tree.get_branch(db, story)
    msg = db.get(Message, message_id)
    if msg is None or msg.story_id != story.id:
        raise TurnError("Message not found.", 404)
    n = db.query(MessageBranch).filter(MessageBranch.story_id == story.id).count()
    nb = story_tree.create_branch(db, story, from_branch=branch, fork_message_id=msg.id, label=label or f"Branch {n + 1} (from #{msg.seq})")
    state_service.fork(db, story.id, branch, nb, msg)
    _fork_cursor(db, story, branch, nb, msg)
    story.active_branch_id = nb.id
    return nb


def select_alternative(db: Session, story_id: str, message_id: str) -> None:
    """Make a sibling alternative the head of the active branch (only for leaf alternatives)."""
    story = story_tree.get_story(db, story_id)
    branch = story_tree.get_branch(db, story)
    msg = db.get(Message, message_id)
    if msg is None or msg.story_id != story.id:
        raise TurnError("Message not found.", 404)
    if story_tree.has_children(db, msg.id):
        raise TurnError("That alternative has later messages; switch to its branch instead.")
    path = story_tree.path_messages(db, branch.head_message_id, include_deleted=True)
    if msg.parent_id not in {m.id for m in path} and msg.parent_id is not None:
        raise TurnError("That alternative belongs to a different branch.")
    branch.head_message_id = msg.id


def edit(db: Session, story_id: str, message_id: str, content: str) -> Message:
    msg = db.get(Message, message_id)
    if msg is None or msg.story_id != story_id:
        raise TurnError("Message not found.", 404)
    if msg.status == "streaming":
        raise TurnError("Stop the generation before editing this message.", 409)
    if content == msg.content:
        return msg
    db.add(MessageVersion(message_id=msg.id, content=msg.content, reason="edit"))
    msg.content = content
    msg.edited_at = now_iso()
    if msg.command_json and msg.role == "user":
        # keep the command expansion consistent with the edited free text
        from ..models import SlashCommand
        cmd = db.get(SlashCommand, msg.command_json.get("id")) if msg.command_json.get("id") else None
        if cmd is not None:
            msg.command_json = dict(msg.command_json, expansion=commands_svc.expand(cmd.template, content))
    _flag_stale(db, story_tree.get_story(db, story_id), [msg.id], f"Message #{msg.seq} was edited")
    return msg


def restore_version(db: Session, story_id: str, message_id: str, version_id: str) -> Message:
    v = db.get(MessageVersion, version_id)
    if v is None or v.message_id != message_id:
        raise TurnError("Version not found.", 404)
    return edit(db, story_id, message_id, v.content)


def delete(db: Session, story_id: str, message_id: str) -> Message:
    msg = db.get(Message, message_id)
    if msg is None or msg.story_id != story_id:
        raise TurnError("Message not found.", 404)
    if msg.status == "streaming":
        raise TurnError("Stop the generation before deleting this message.", 409)
    msg.deleted_at = now_iso()
    story = story_tree.get_story(db, story_id)
    _flag_stale(db, story, [msg.id], f"Message #{msg.seq} was deleted")
    # if the deleted message was a branch head, move the head to its parent so new turns attach correctly
    for b in db.scalars(select(MessageBranch).where(MessageBranch.head_message_id == msg.id)):
        if not story_tree.has_children(db, msg.id):
            parent = db.get(Message, msg.parent_id) if msg.parent_id else None
            while parent is not None and parent.deleted_at is not None:
                parent = db.get(Message, parent.parent_id) if parent.parent_id else None
            b.head_message_id = parent.id if parent else None
    return msg


def undelete(db: Session, story_id: str, message_id: str) -> Message:
    msg = db.get(Message, message_id)
    if msg is None or msg.story_id != story_id:
        raise TurnError("Message not found.", 404)
    msg.deleted_at = None
    # restoring a deleted last reply/turn makes it the branch head again (delete had moved the head to its parent)
    for b in db.scalars(select(MessageBranch).where(MessageBranch.story_id == story_id, MessageBranch.head_message_id == msg.parent_id)):
        if msg.parent_id and not story_tree.has_children(db, msg.id) and b.id == msg.branch_id:
            b.head_message_id = msg.id
    return msg


def _flag_stale(db: Session, story: Story, message_ids: list[str], reason: str) -> int:
    n = 0
    ids = set(message_ids)
    for e in db.scalars(select(StoryEvent).where(StoryEvent.story_id == story.id)):
        if ids & set(e.source_message_ids_json or []):
            e.stale, e.stale_reason = True, reason
            n += 1
    for f in db.scalars(select(EntityFact).where(EntityFact.story_id == story.id)):
        if ids & set(f.source_message_ids_json or []):
            f.stale = True
            n += 1
    from . import summaries  # v1.8: the memory summary of that text is written again
    n += summaries.mark_stale(db, story.id, list(ids))
    return n


def _fork_cursor(db: Session, story: Story, src: MessageBranch, dst: MessageBranch, fork_msg: Message | None) -> None:
    cur = db.get(ExtractionCursor, src.id)
    last = min(cur.last_seq, fork_msg.seq) if cur and fork_msg else -1
    db.add(ExtractionCursor(branch_id=dst.id, story_id=story.id, last_seq=last))


# --------------------------------------------------------------------------- post-processing
def post_process(ctx: AppContext, message_id: str) -> str | None:
    """Speaker + mood heuristics after a reply is saved; returns branch_id if extraction should be queued."""
    with ctx.db.session() as db:
        m = db.get(Message, message_id)
        if m is None or m.status not in ("complete", "partial") or not m.content.strip():
            return None
        story = db.get(Story, m.story_id)
        st_row = state_service.current(db, m.branch_id)
        state = st_row.state_json if st_row else {}
        index = build_index(db, story.world_id, state)
        md = dict(m.generation_metadata_json or {})
        if m.kind == "story":
            m.speaker_character_id = detect_speaker(m.content, index)
            mentioned = index.find_mentions(m.content, ("character",))
            md["mentioned_characters"] = mentioned
            sugg = suggest_moods(m.content, index)
            md["mood_suggestions"] = sugg
            if settings_service.get(db, "auto_apply_expression_suggestions") and sugg and m.status == "complete":
                apply_expressions(story, m.branch_id, sugg, source="suggested", message_id=m.id)
            if m.role == "assistant":
                # invented holders of locked posts / unknown authorities: a notice under the reply, text unchanged
                from . import roles
                from ..models import Avatar
                av = db.get(Avatar, story.active_avatar_id) if story.active_avatar_id else None
                me = {av.name if av else (story.avatar_snapshot_json or {}).get("name") or ""}
                md["lore_conflicts"] = roles.detect_conflicts(m.content, roles.build_registry(db, story.world_id, index), index,
                                                              ignore=me | {w for n in me for w in n.split()})
        m.generation_metadata_json = md
        if m.kind != "story" or m.status != "complete":
            return None
        cur = db.get(ExtractionCursor, m.branch_id)
        if cur is None:
            cur = ExtractionCursor(branch_id=m.branch_id, story_id=story.id, last_seq=-1)
            db.add(cur)
        cur.assistant_turns_since = (cur.assistant_turns_since or 0) + 1
        mode = settings_service.get(db, "event_capture_mode")
        every = int(settings_service.get(db, "event_capture_batch_turns") or 3)
        if mode == "after_each_turn" or (mode == "batch" and cur.assistant_turns_since >= every):
            return m.branch_id
    return None


def apply_expressions(story: Story, branch_id: str, suggestions: list[dict[str, Any]], *, source: str,
                      message_id: str | None = None) -> None:
    s = dict(story.settings_json or {})
    exprs = dict(s.get("expressions") or {})
    cur = dict(exprs.get(branch_id) or {})
    for sg in suggestions:
        prev = cur.get(sg["character_id"]) or {}
        if prev.get("locked"):
            continue
        cur[sg["character_id"]] = {"slot": int(sg["slot"]), "locked": False, "source": source,
                                   "evidence": sg.get("evidence"), "message_id": message_id, "updated_at": now_iso()}
    exprs[branch_id] = cur
    s["expressions"] = exprs
    story.settings_json = s
