"""Automatic memory summaries (v1.8, phase 7.1): the story compressed while it is played.

Every few turns memory capture reads the newest messages anyway (services/extraction.py); it now also writes a short
"scene summary" of them in the same request, so the memory costs no extra call. When capture did not write one (capture
switched off or manual, a story older than this feature, a model that left the field empty) ``catch_up`` asks the
story's own model for the summary alone, a couple of short requests at most after a reply, oldest messages first.

The context builder (services/context_builder.py) sends these summaries for the messages that no longer fit word for
word, so the narrator keeps the thread of a long game without the whole transcript.

Summaries are written in English (like the lore: compact and well understood by every model); names stay as they are.
A summary belongs to the exact messages it covers: it is used only on a path that contains all of them (branches and
regenerated replies never see a summary of text they do not have), and editing one of them marks it stale (it is then
written again).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Avatar, ExtractionCursor, MemorySummary, Message, MessageBranch, Story, now_iso
from ..providers import ChatMessage, ProviderError
from . import settings_service, story_tree
from .runtime import AppContext, ConsentRequired, NoModelConfigured

log = logging.getLogger(__name__)

# one catch-up request covers at most this much (≈3,500 tokens of story), lowered to fit small model windows
CHUNK_MESSAGES = 10
CHUNK_CHARS = 14000
MIN_NEW = 6  # the newest messages wait until a chunk is worth a request (older gaps are summarised at once)
SUMMARY_MAX_TOKENS = 500
AUTO_MAX_CHUNKS = 2  # catch-up requests after one reply (a long old game is summarised a little at every turn)
MAX_CHARS = 1500  # a summary longer than this is cut (a model that ignored "2 to 5 sentences")
RETRY_AFTER_FAILURE = 600  # seconds before an automatic catch-up tries again after a failed request
_failed_at: dict[str, float] = {}

MARK = "SCENE SUMMARY"
RULES = """SCENE SUMMARY. You keep the memory of an interactive story. Summarise ONLY the messages marked NEW.
- 2 to 5 short sentences, past tense, third person. The protagonist is {name}.
- Keep what matters later: who did what, names of characters and places, items, promises, decisions, injuries,
  discoveries, what a character learned, and how a character's attitude toward {name} changed.
- Only what the NEW messages establish: no invention, no commentary, no headings, no lists, no quotes.
- Write in English, even if the story is in another language; keep names exactly as written.
Answer with the summary text only."""

# the field memory capture fills in the same request (services/extraction.py)
CAPTURE_FIELD = ('  "scene_summary": str (2-5 short sentences in English, past tense: what happens in the NEW messages — '
                 'who did what, names, places, items, promises, decisions, discoveries; no invention)')


def enabled(db: Session) -> bool:
    return settings_service.get(db, "scene_summaries_enabled") is not False


def path_messages(db: Session, branch: MessageBranch) -> list[Message]:
    """The messages a summary can cover, in story order (the same ones memory capture reads)."""
    return [m for m in story_tree.path_messages(db, branch.head_message_id)
            if m.kind in ("story", "ooc") and m.status in ("complete", "partial", "cancelled") and m.content.strip()]


def visible(db: Session, story_id: str, path_ids: set[str], level: str = "scene") -> list[MemorySummary]:
    """Active summaries whose messages are all on this path, oldest first."""
    rows = db.scalars(select(MemorySummary).where(MemorySummary.story_id == story_id, MemorySummary.level == level,
                                                  MemorySummary.status == "active"))
    out = [r for r in rows if r.message_ids_json and set(r.message_ids_json) <= path_ids]
    out.sort(key=lambda r: (r.start_seq, r.end_seq))
    return out


def covered_ids(rows: list[MemorySummary]) -> set[str]:
    return {i for r in rows for i in (r.message_ids_json or [])}


def clean(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()  # a code fence around plain text
    t = re.sub(r"^(?:scene\s+)?summary\s*:\s*", "", t, flags=re.I).strip()
    t = re.sub(r"\s*\n\s*", " ", t)
    if len(t) > MAX_CHARS:
        cut = t[:MAX_CHARS]
        t = cut[:cut.rfind(". ") + 1] if ". " in cut else cut + " …"
    return t


def store(db: Session, story: Story, branch: MessageBranch, msgs: list[Message], text: str, *, source: str,
          model_id: str | None = None) -> MemorySummary | None:
    """Save the summary of ``msgs`` (consecutive messages). Nothing is saved for an empty text or when one of the
    messages already has a summary on this path (a summary is never duplicated or overlapped)."""
    text = clean(text)
    if not text or not msgs:
        return None
    path_ids = {m.id for m in path_messages(db, branch)}
    ids = [m.id for m in msgs]
    if not set(ids) <= path_ids or set(ids) & covered_ids(visible(db, story.id, path_ids)):
        return None
    row = MemorySummary(story_id=story.id, branch_id=branch.id, level="scene", content=text, message_ids_json=ids,
                        start_message_id=ids[0], end_message_id=ids[-1], start_seq=msgs[0].seq, end_seq=msgs[-1].seq,
                        status="active", source=source, model_id=model_id)
    db.add(row)
    db.flush()
    return row


def mark_stale(db: Session, story_id: str, message_ids: list[str]) -> int:
    """A covered message was edited, regenerated or deleted: its summary no longer describes the text (written again)."""
    ids, n = set(message_ids), 0
    for r in db.scalars(select(MemorySummary).where(MemorySummary.story_id == story_id, MemorySummary.status == "active")):
        if ids & set(r.message_ids_json or []):
            r.status, r.updated_at = "stale", now_iso()
            n += 1
    return n


def _runs(path: list[Message], todo: set[str]) -> list[list[Message]]:
    """Runs of consecutive path messages that are in ``todo``, oldest first."""
    runs, cur = [], []
    for m in path:
        if m.id in todo:
            cur.append(m)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def next_chunk(db: Session, story: Story, branch: MessageBranch, max_chars: int = CHUNK_CHARS) -> list[Message]:
    """The next messages the catch-up should summarise, or [] (nothing to do, or the newest messages are left to
    memory capture, which summarises them in its own request)."""
    path = path_messages(db, branch)
    path_ids = {m.id for m in path}
    todo = {m.id for m in path} - covered_ids(visible(db, story.id, path_ids))
    mode = settings_service.get(db, "event_capture_mode")
    if mode in ("batch", "after_each_turn") and settings_service.get(db, "extraction_model_source") != "none":
        cur = db.get(ExtractionCursor, branch.id)
        done = cur.last_seq if cur else -1
        todo = {m.id for m in path if m.id in todo and m.seq <= done}  # capture has passed them without a summary
        wait_for_more = False
    else:
        wait_for_more = True
    for run in _runs(path, todo):
        if wait_for_more and run[-1].id == path[-1].id and len(run) < MIN_NEW:
            return []  # the newest few: wait until a chunk is worth a request
        out, used = [], 0
        for m in run[:CHUNK_MESSAGES]:
            if out and used + len(m.content) > max_chars:
                break
            out.append(m)
            used += len(m.content)
        return out
    return []


def _protagonist(db: Session, story: Story) -> str:
    av = db.get(Avatar, story.active_avatar_id) if story.active_avatar_id else None
    return (av.name if av else (story.avatar_snapshot_json or {}).get("name")) or "the protagonist"


def _chunk_chars(resolved, fixed_text: str) -> int:
    from .context_builder import SAFETY_MARGIN, effective_window, est_tokens

    window = effective_window(resolved.profile.context_limit, resolved.params)
    if not window:
        return CHUNK_CHARS
    room = int(window * SAFETY_MARGIN) - SUMMARY_MAX_TOKENS - est_tokens(fixed_text) - 200
    return max(1500, min(CHUNK_CHARS, room * 4))


def transcript(msgs: list[Message]) -> str:
    return "\n\n".join(f"[NEW #{m.seq}] {m.role}{' (out of character)' if m.kind == 'ooc' else ''}: {m.content}"
                       for m in msgs)


async def catch_up(ctx: AppContext, story_id: str, branch_id: str | None = None, *,
                   max_chunks: int = AUTO_MAX_CHUNKS, automatic: bool = True) -> dict[str, Any]:
    """Summarise what memory capture left without a summary: at most ``max_chunks`` short requests, oldest first, with
    the story's own model. Never raises for model problems (the next reply tries again, after a pause if it failed)."""
    with ctx.db.session() as db:
        story = story_tree.get_story(db, story_id)
        branch = story_tree.get_branch(db, story, branch_id)
        branch_id = branch.id
        if not enabled(db):
            return {"status": "off", "written": 0}
    if automatic and time.time() - _failed_at.get(branch_id, 0) < RETRY_AFTER_FAILURE:
        return {"status": "waiting", "written": 0}
    written = 0
    async with ctx.extraction._lock(branch_id):  # one model request at a time per story (local models)
        for _ in range(max(1, max_chunks)):
            with ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                try:
                    resolved = ctx.resolve(db, ctx.story_profile_id(db, story))
                except (NoModelConfigured, ConsentRequired) as e:
                    return {"status": "no_model", "written": written, "error": str(e)}
                system = RULES.format(name=_protagonist(db, story))
                part = next_chunk(db, story, branch)
                if not part:
                    break
                path = path_messages(db, branch)
                path_ids = {m.id for m in path}
                prev = [r for r in visible(db, story.id, path_ids) if r.end_seq < part[0].seq]
                context = f"Earlier (context only, do not summarise again): {prev[-1].content}\n\n" if prev else ""
                part = next_chunk(db, story, branch, _chunk_chars(resolved, system + context))
                ids = [m.id for m in part]
                prompt = context + "NEW messages:\n" + transcript(part)
            try:
                text = await resolved.adapter.complete(resolved.profile.model_id, system, [ChatMessage("user", prompt)],
                                                       {**resolved.params, "temperature": 0.3,
                                                        "max_tokens": SUMMARY_MAX_TOKENS})
            except ProviderError as e:
                _failed_at[branch_id] = time.time()
                log.warning("memory summary failed for story %s (%s): %s", story_id, e.category, e.message)
                return {"status": "failed", "written": written, "error": e.message}
            with ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                msgs = [db.get(Message, i) for i in ids]
                row = store(db, story, branch, [m for m in msgs if m is not None], text, source="summary",
                            model_id=resolved.profile.model_id)
            if row is None:  # empty answer, or the messages changed meanwhile: stop for now
                _failed_at[branch_id] = time.time()
                break
            _failed_at.pop(branch_id, None)
            written += 1
    return {"status": "succeeded", "written": written}
