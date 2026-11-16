"""Automatic memory summaries (v1.8, phase 7): the story compressed while it is played.

Layers (phase 7.2), all tied to the exact messages they cover:
* scene    — a short summary of a few consecutive messages. Memory capture (services/extraction.py) writes it in the
             request it makes anyway; ``catch_up`` asks the story's own model for what is still missing (capture off or
             manual, games older than this feature, an empty field). A scene also carries one memory line per character
             involved and the threads (promises, debts, quests, mysteries) it opened or settled (``data_json``).
* chapter  — when scenes pile up, the oldest ones are merged into one chapter summary (one short request).
* story    — when chapters pile up, the oldest ones are folded into a single "story so far", rewritten incrementally.
A merged row's children are marked ``superseded`` with ``parent_id``: what is ``active`` always partitions the story,
so the memory sent to the narrator stays bounded however long the game is (services/context_builder.py).

Summaries are written in English (like the lore: compact and well understood by every model); names stay as they are.
A row is used only on a path that contains all of its messages (branches and regenerated replies never see a summary
of text they do not have). Editing, regenerating or deleting a covered message marks every row covering it ``stale``;
their other children become active again and the missing summaries are written again.
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
SUMMARY_MAX_TOKENS = 700
MERGE_MAX_TOKENS = 900
AUTO_MAX_CHUNKS = 2  # catch-up requests after one reply (a long old game is summarised a little at every turn)
MAX_CHARS = 1500  # a scene summary longer than this is cut (a model that ignored "2 to 5 sentences")
MAX_MERGED_CHARS = {"chapter": 2200, "story": 3200}
NOTE_CHARS = 240
RETRY_AFTER_FAILURE = 600  # seconds before an automatic catch-up tries again after a failed request
# layers: scenes beyond KEEP_SCENES are merged CHAPTER_SCENES at a time; chapters beyond KEEP_CHAPTERS are folded
# STORY_CHAPTERS at a time into the story so far
KEEP_SCENES, CHAPTER_SCENES = 4, 8
KEEP_CHAPTERS, STORY_CHAPTERS = 4, 2
MAX_THREADS = 12
_failed_at: dict[str, float] = {}

RULES = """SCENE SUMMARY. You keep the memory of an interactive story. Summarise ONLY the messages marked NEW.
Answer in exactly this format (English, even if the story is in another language; names exactly as written):
SUMMARY: 2 to 5 short sentences, past tense, third person, about what happens. The protagonist is {name}.
CHARACTERS:
- Name: one sentence on what happened between this character and {name}, or what they learned, decided or now feel
OPENED:
- a promise, debt, quest, appointment or mystery that starts here and is still pending
RESOLVED:
- the id (like T2) of an open thread that these messages settle
Write "- none" under a heading that has nothing. Only what the NEW messages establish: no invention, no commentary.
Never list {name} under CHARACTERS."""

MERGE_RULES = {
    "chapter": """CHAPTER SUMMARY. You keep the memory of an interactive story. Merge the scene summaries below into ONE
chapter summary of 4 to 8 sentences, past tense, in English, oldest first. Keep names, places, items, promises, decisions,
injuries, discoveries and how relationships with {name} changed; drop small talk and repeated details. Never invent.
Answer with the summary text only.""",
    "story": """STORY SO FAR. You keep the memory of an interactive story. Rewrite the story so far as ONE summary of at most
12 sentences, past tense, in English, oldest first: the previous "story so far" (if any) followed by the chapters below.
Keep what still matters: who {name} is with, important events, promises, enemies, discoveries, where things stand.
Drop details that no longer matter. Never invent. Answer with the summary text only.""",
}

# the fields memory capture fills in the same request (services/extraction.py)
CAPTURE_FIELD = (
    '  "scene_summary": str (2-5 short sentences in English, past tense: what happens in the NEW messages — who did '
    'what, names, places, items, promises, decisions, discoveries; no invention),\n'
    '  "character_notes": [{"character": name, "note": one sentence in English: what happened between them and the '
    'protagonist, or what they learned, decided or now feel}] (never the protagonist),\n'
    '  "threads_opened": [short English text of each promise, debt, quest, appointment or mystery that starts in the '
    'NEW messages and is still pending],\n'
    '  "threads_resolved": [ids like "T2" of the open threads listed above that the NEW messages settle]')


def enabled(db: Session) -> bool:
    return settings_service.get(db, "scene_summaries_enabled") is not False


def path_messages(db: Session, branch: MessageBranch) -> list[Message]:
    """The messages a summary can cover, in story order (the same ones memory capture reads)."""
    return [m for m in story_tree.path_messages(db, branch.head_message_id)
            if m.kind in ("story", "ooc") and m.status in ("complete", "partial", "cancelled") and m.content.strip()]


def visible(db: Session, story_id: str, path_ids: set[str], level: str | tuple[str, ...] = "scene",
            statuses: tuple[str, ...] = ("active",)) -> list[MemorySummary]:
    """Summaries of these levels and statuses whose messages are all on this path, oldest first."""
    levels = (level,) if isinstance(level, str) else level
    rows = db.scalars(select(MemorySummary).where(MemorySummary.story_id == story_id, MemorySummary.level.in_(levels),
                                                  MemorySummary.status.in_(statuses)))
    out = [r for r in rows if r.message_ids_json and set(r.message_ids_json) <= path_ids]
    out.sort(key=lambda r: (r.start_seq, r.end_seq))
    return out


def scenes(db: Session, story_id: str, path_ids: set[str]) -> list[MemorySummary]:
    """Every scene summary of this path, merged into a chapter or not (the source of notes and threads)."""
    return visible(db, story_id, path_ids, "scene", ("active", "superseded"))


def covered_ids(rows: list[MemorySummary]) -> set[str]:
    return {i for r in rows for i in (r.message_ids_json or [])}


def clean(text: str, limit: int = MAX_CHARS) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()  # a code fence around plain text
    t = re.sub(r"^(?:(?:scene|chapter|story)\s+)?(?:summary|so far)\s*:\s*", "", t, flags=re.I).strip()
    t = re.sub(r"\s*\n\s*", " ", t)
    if len(t) > limit:
        cut = t[:limit]
        t = cut[:cut.rfind(". ") + 1] if ". " in cut else cut + " …"
    return t


NONE = re.compile(r"^(?:none|nothing|n/?a|-)?\.?$", re.I)


def parse_answer(text: str) -> dict[str, Any]:
    """The catch-up answer (SUMMARY / CHARACTERS / OPENED / RESOLVED blocks). A model that answered with plain prose
    gives a summary without extras."""
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", (text or "").strip()).strip()
    heads = list(re.finditer(r"^\s*\**\s*(SUMMARY|CHARACTERS|OPENED|RESOLVED)\s*\**\s*:?", t, re.I | re.M))
    if not heads:
        return {"summary": clean(t), "notes": [], "opened": [], "resolved": []}
    blocks: dict[str, str] = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(t)
        blocks[h.group(1).upper()] = t[h.end():end].strip()

    def items(key: str) -> list[str]:
        out = []
        for line in (blocks.get(key) or "").splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if line and not NONE.match(line):
                out.append(line)
        return out

    notes = []
    for line in items("CHARACTERS"):
        name, sep, note = line.partition(":")
        if sep and name.strip() and note.strip():
            notes.append({"character": name.strip().strip("*"), "note": note.strip()})
    return {"summary": clean(blocks.get("SUMMARY", "")), "notes": notes, "opened": items("OPENED"),
            "resolved": [r for x in items("RESOLVED") for r in re.findall(r"T\d+", x, re.I)]}


# ------------------------------------------------------------------------------------------- notes and threads
def open_threads(rows: list[MemorySummary]) -> list[dict[str, Any]]:
    """Threads still open after these scenes (oldest first): [{"key", "text", "seq"}]."""
    open_: dict[str, dict[str, Any]] = {}
    for r in sorted(rows, key=lambda r: (r.start_seq, r.end_seq)):
        d = r.data_json or {}
        for k in d.get("threads_resolved") or []:
            open_.pop(k, None)
        for i, text in enumerate(d.get("threads_opened") or []):
            open_[f"{r.id}:{i}"] = {"key": f"{r.id}:{i}", "text": text, "seq": r.end_seq}
    return list(open_.values())


def thread_labels(threads: list[dict[str, Any]]) -> tuple[str, dict[str, str]]:
    """The open threads as the prompts show them (T1, T2...) and the label → key map used to read the answer."""
    shown = threads[-MAX_THREADS:]
    labels = {f"T{i + 1}": t["key"] for i, t in enumerate(shown)}
    text = "\n".join(f"T{i + 1}: {t['text']}" for i, t in enumerate(shown))
    return text, labels


def extras(notes: list[dict[str, Any]], opened: list[str], resolved: list[str], labels: dict[str, str], index=None,
           protagonist: str = "") -> dict[str, Any]:
    """data_json of a scene: character notes keyed by lore id (or by name), threads opened and settled."""
    me = {w.lower() for w in protagonist.split()} | {protagonist.lower()}
    out_notes = []
    for n in notes[:8]:
        name, note = str(n.get("character") or "").strip(), clean(str(n.get("note") or ""), NOTE_CHARS)
        if not name or not note or name.lower() in me or name.lower() in ("player", "protagonist", "you"):
            continue
        cid = (name if index is not None and name in index.entities else index.resolve(name)) if index is not None else None
        out_notes.append({"key": cid or f"name:{name.lower()}", "name": index.name(cid) if cid else name, "note": note})
    keys = [labels[x.upper()] for x in resolved if x.upper() in labels]
    return {"notes": out_notes, "threads_opened": [clean(o, NOTE_CHARS) for o in opened[:4] if o.strip()],
            "threads_resolved": list(dict.fromkeys(keys))}


def character_memory(rows: list[MemorySummary], keys: list[str], names_in_text: str = "", per_char: int = 3,
                     max_chars: int = 8) -> list[tuple[str, list[str]]]:
    """For the characters in focus (lore ids), and characters without a lore record whose name appears in the recent
    text: their latest memory lines, newest first."""
    found: dict[str, tuple[str, list[str]]] = {}
    low = names_in_text.lower()
    for r in sorted(rows, key=lambda r: (r.end_seq, r.start_seq), reverse=True):
        for n in (r.data_json or {}).get("notes") or []:
            k = n.get("key") or ""
            wanted = k in keys or (k.startswith("name:") and k[5:] and re.search(rf"\b{re.escape(k[5:])}\b", low))
            if not wanted:
                continue
            name, lines = found.setdefault(k, (n.get("name") or k, []))
            if len(lines) < per_char:
                lines.append(f"(#{r.start_seq}–#{r.end_seq}) {n['note']}")
    order = [k for k in keys if k in found] + [k for k in found if k not in keys]
    return [found[k] for k in order][:max_chars]


# ------------------------------------------------------------------------------------------- storage
def store(db: Session, story: Story, branch: MessageBranch, msgs: list[Message], text: str, *, source: str,
          model_id: str | None = None, data: dict[str, Any] | None = None) -> MemorySummary | None:
    """Save the scene summary of ``msgs`` (consecutive messages). Nothing is saved for an empty text or when one of the
    messages already has a summary on this path (a summary is never duplicated or overlapped)."""
    text = clean(text)
    if not text or not msgs:
        return None
    path_ids = {m.id for m in path_messages(db, branch)}
    ids = [m.id for m in msgs]
    if not set(ids) <= path_ids or set(ids) & covered_ids(scenes(db, story.id, path_ids)):
        return None
    row = MemorySummary(story_id=story.id, branch_id=branch.id, level="scene", content=text, message_ids_json=ids,
                        start_message_id=ids[0], end_message_id=ids[-1], start_seq=msgs[0].seq, end_seq=msgs[-1].seq,
                        status="active", source=source, model_id=model_id, data_json=data or {})
    db.add(row)
    db.flush()
    return row


def mark_stale(db: Session, story_id: str, message_ids: list[str]) -> int:
    """A covered message was edited, regenerated or deleted: every row covering it no longer describes the text. Their
    other children (scenes of a chapter, chapters of a story so far) become active again; the rest is written again."""
    ids, stale = set(message_ids), []
    for r in db.scalars(select(MemorySummary).where(MemorySummary.story_id == story_id,
                                                    MemorySummary.status.in_(("active", "superseded")))):
        if ids & set(r.message_ids_json or []):
            r.status, r.updated_at = "stale", now_iso()
            stale.append(r.id)
    if stale:
        for child in db.scalars(select(MemorySummary).where(MemorySummary.parent_id.in_(stale),
                                                            MemorySummary.status == "superseded")):
            child.status, child.parent_id, child.updated_at = "active", None, now_iso()
    return len(stale)


# ------------------------------------------------------------------------------------------- catch-up
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
    todo = path_ids - covered_ids(scenes(db, story.id, path_ids))
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


def protagonist(db: Session, story: Story) -> str:
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


def _index(db: Session, story: Story, branch: MessageBranch):
    from . import state_service
    from .entities import build_index
    st = state_service.current(db, branch.id)
    return build_index(db, story.world_id, st.state_json if st else {})


def merge_candidate(db: Session, story: Story, branch: MessageBranch) -> tuple[str, list[MemorySummary]] | None:
    """The next merge, if one is due: ("chapter", oldest scenes) or ("story", [story so far?] + oldest chapters)."""
    path_ids = {m.id for m in path_messages(db, branch)}
    active_scenes = visible(db, story.id, path_ids, "scene")
    if len(active_scenes) >= KEEP_SCENES + CHAPTER_SCENES:
        return "chapter", active_scenes[:CHAPTER_SCENES]
    chapters = visible(db, story.id, path_ids, "chapter")
    if len(chapters) >= KEEP_CHAPTERS + STORY_CHAPTERS:
        prev = visible(db, story.id, path_ids, "story")
        return "story", prev[-1:] + chapters[:STORY_CHAPTERS]
    return None


def save_merge(db: Session, story: Story, branch: MessageBranch, level: str, parts: list[MemorySummary], text: str,
               model_id: str | None) -> MemorySummary | None:
    text = clean(text, MAX_MERGED_CHARS[level])
    fresh = [db.get(MemorySummary, p.id) for p in parts]
    if not text or any(p is None or p.status != "active" for p in fresh):
        return None  # empty answer, or the parts changed meanwhile
    ids = list(dict.fromkeys(i for p in fresh for i in p.message_ids_json))
    row = MemorySummary(story_id=story.id, branch_id=branch.id, level=level, content=text, message_ids_json=ids,
                        start_message_id=fresh[0].start_message_id, end_message_id=fresh[-1].end_message_id,
                        start_seq=min(p.start_seq for p in fresh), end_seq=max(p.end_seq for p in fresh),
                        status="active", source="summary", model_id=model_id, data_json={})
    db.add(row)
    db.flush()
    for p in fresh:
        p.status, p.parent_id, p.updated_at = "superseded", row.id, now_iso()
    return row


async def catch_up(ctx: AppContext, story_id: str, branch_id: str | None = None, *,
                   max_chunks: int = AUTO_MAX_CHUNKS, automatic: bool = True, max_merges: int = 1) -> dict[str, Any]:
    """Summarise what memory capture left without a summary (at most ``max_chunks`` short requests, oldest first), then
    merge layers that piled up (at most ``max_merges`` requests), with the story's own model. Never raises for model
    problems (the next reply tries again, after a pause if it failed)."""
    with ctx.db.session() as db:
        story = story_tree.get_story(db, story_id)
        branch = story_tree.get_branch(db, story, branch_id)
        branch_id = branch.id
        if not enabled(db):
            return {"status": "off", "written": 0, "merged": 0}
    if automatic and time.time() - _failed_at.get(branch_id, 0) < RETRY_AFTER_FAILURE:
        return {"status": "waiting", "written": 0, "merged": 0}
    written = merged = 0

    def failed(e: ProviderError) -> dict[str, Any]:
        _failed_at[branch_id] = time.time()
        log.warning("memory summary failed for story %s (%s): %s", story_id, e.category, e.message)
        return {"status": "failed", "written": written, "merged": merged, "error": e.message}

    async with ctx.extraction._lock(branch_id):  # one model request at a time per story (local models)
        for _ in range(max(0, max_chunks)):
            with ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                try:
                    resolved = ctx.resolve(db, ctx.story_profile_id(db, story))
                except (NoModelConfigured, ConsentRequired) as e:
                    return {"status": "no_model", "written": written, "merged": merged, "error": str(e)}
                name = protagonist(db, story)
                system = RULES.format(name=name)
                part = next_chunk(db, story, branch)
                if not part:
                    break
                path_ids = {m.id for m in path_messages(db, branch)}
                before = [r for r in scenes(db, story.id, path_ids) if r.end_seq < part[0].seq]
                threads_text, labels = thread_labels(open_threads(before))
                context = "\n\n".join(x for x in [
                    f"Earlier (context only, do not summarise again): {before[-1].content}" if before else "",
                    f"Open threads (use these ids under RESOLVED):\n{threads_text}" if threads_text else ""] if x)
                context = context + "\n\n" if context else ""
                part = next_chunk(db, story, branch, _chunk_chars(resolved, system + context))
                ids = [m.id for m in part]
                prompt = context + "NEW messages:\n" + transcript(part)
            try:
                text = await resolved.adapter.complete(resolved.profile.model_id, system, [ChatMessage("user", prompt)],
                                                       {**resolved.params, "temperature": 0.3,
                                                        "max_tokens": SUMMARY_MAX_TOKENS})
            except ProviderError as e:
                return failed(e)
            ans = parse_answer(text)
            with ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                msgs = [db.get(Message, i) for i in ids]
                data = extras(ans["notes"], ans["opened"], ans["resolved"], labels, _index(db, story, branch), name)
                row = store(db, story, branch, [m for m in msgs if m is not None], ans["summary"], source="summary",
                            model_id=resolved.profile.model_id, data=data)
            if row is None:  # empty answer, or the messages changed meanwhile: stop for now
                _failed_at[branch_id] = time.time()
                break
            _failed_at.pop(branch_id, None)
            written += 1
        for _ in range(max(0, max_merges)):
            with ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                due = merge_candidate(db, story, branch)
                if due is None:
                    break
                try:
                    resolved = ctx.resolve(db, ctx.story_profile_id(db, story))
                except (NoModelConfigured, ConsentRequired) as e:
                    return {"status": "no_model", "written": written, "merged": merged, "error": str(e)}
                level, parts = due
                system = MERGE_RULES[level].format(name=protagonist(db, story))
                prompt = "\n\n".join(
                    (f"Previous story so far:\n{p.content}" if p.level == "story" else
                     f"{p.level.capitalize()} (messages #{p.start_seq}–#{p.end_seq}):\n{p.content}") for p in parts)
            try:
                text = await resolved.adapter.complete(resolved.profile.model_id, system, [ChatMessage("user", prompt)],
                                                       {**resolved.params, "temperature": 0.3,
                                                        "max_tokens": MERGE_MAX_TOKENS})
            except ProviderError as e:
                return failed(e)
            with ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                row = save_merge(db, story, branch, level, parts, text, resolved.profile.model_id)
            if row is None:
                break
            merged += 1
    return {"status": "succeeded", "written": written, "merged": merged}
