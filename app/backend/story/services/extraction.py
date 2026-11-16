"""Event/fact extraction, recaps, continuity checks and state-change suggestions.

Guarantees:
* Only the unprocessed range (cursor → head) plus a little prior context is analysed, in bounded chunks (v1.4: a
  failed run used to re-send the whole, ever-growing backlog in one request until every answer was cut off).
* The transcript is never modified here; extraction commits in its own transaction.
* The cursor advances only in the same transaction that stores a chunk's results, so failures are retryable, earlier
  chunks are kept, and retries cannot duplicate records (dedupe keys are also checked).
* Source message IDs returned by the model are validated against the analysed range — never invented.
* A range that failed for a non-transient reason is not sent again automatically (capture pauses with the reason);
  the player resumes, retries with smaller chunks or skips it from the Journal.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (EntityFact, ExtractionCursor, MemoryExtractionRun, Message, MessageBranch, Recap, StateProposal,
                      Story, StoryEvent, now_iso)
from ..providers import ChatMessage, ProviderError
from . import settings_service, state_service, story_tree
from . import summaries as summaries_svc
from .context_builder import render_state
from .entities import build_index, norm
from .runtime import AppContext, ConsentRequired, NoModelConfigured
from .turns import apply_expressions

log = logging.getLogger(__name__)

EVENT_TYPES = ["arrival", "departure", "promise", "confrontation", "injury", "death", "discovery", "secret_revealed",
               "item_gained", "item_lost", "quest_accepted", "quest_completed", "relationship_change", "location_change",
               "battle", "faction_action", "decision", "conversation", "other"]
EVIDENCE = ["witnessed", "claim", "rumour", "dream_vision", "plan", "hypothetical"]
FACT_KINDS = ["established", "witnessed", "claim", "rumour", "belief", "plan", "hypothetical", "dream_vision", "secret"]
CHANGE_KINDS = ["stat", "relationship", "inventory_add", "inventory_remove", "condition_add", "condition_remove", "quest",
                "scene", "list_add", "list_resolve", "player"]


def _clamp01(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


PLACEHOLDER_VALUES = {"", "unknown", "none", "null", "n/a", "na", "unspecified", "not specified"}


def _blank_to_none(v: Any) -> Any:
    return None if isinstance(v, str) and v.strip().lower() in PLACEHOLDER_VALUES else v


class XEvent(BaseModel):
    title: str
    summary: str = ""
    event_type: str = "other"
    importance: int = 3
    confidence: float = 0.7
    evidence_kind: str = "witnessed"
    source_message_ids: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    in_world_time: Optional[str] = None
    evidence_excerpt: Optional[str] = None

    @field_validator("location", "in_world_time", "evidence_excerpt", mode="before")
    @classmethod
    def _placeholders(cls, v: Any) -> Any:  # models often write "unknown" instead of null
        return _blank_to_none(v)

    @field_validator("event_type")
    @classmethod
    def _et(cls, v: str) -> str:
        return v if v in EVENT_TYPES else "other"

    @field_validator("evidence_kind")
    @classmethod
    def _ek(cls, v: str) -> str:
        return v if v in EVIDENCE else "witnessed"

    @field_validator("importance")
    @classmethod
    def _imp(cls, v: int) -> int:
        return max(1, min(5, int(v)))

    @field_validator("confidence")
    @classmethod
    def _conf(cls, v: float) -> float:
        return _clamp01(v)


class XFact(BaseModel):
    subject: Optional[str] = None
    predicate: str = ""
    content: str
    fact_kind: str = "established"
    belief_holder: Optional[str] = None
    known_by: list[str] = Field(default_factory=list)
    hidden_from: list[str] = Field(default_factory=list)
    confidence: float = 0.7
    importance: int = 3
    tentative: bool = False
    source_message_ids: list[str] = Field(default_factory=list)

    @field_validator("fact_kind")
    @classmethod
    def _fk(cls, v: str) -> str:
        return v if v in FACT_KINDS else "established"

    @field_validator("confidence")
    @classmethod
    def _conf(cls, v: float) -> float:
        return _clamp01(v)

    @field_validator("importance")
    @classmethod
    def _imp(cls, v: int) -> int:
        return max(1, min(5, int(v)))


class XChange(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    confidence: float = 0.6
    source_message_ids: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _conf(cls, v: float) -> float:
        return _clamp01(v)


class XContradiction(BaseModel):
    description: str
    conflicting_record: str = ""
    source_message_ids: list[str] = Field(default_factory=list)


class XMood(BaseModel):
    character: str
    slot: int
    confidence: float = 0.5


class Extraction(BaseModel):
    events: list[XEvent] = Field(default_factory=list)
    facts: list[XFact] = Field(default_factory=list)
    state_changes: list[XChange] = Field(default_factory=list)
    contradictions: list[XContradiction] = Field(default_factory=list)
    character_moods: list[XMood] = Field(default_factory=list)
    scene_summary: str = ""  # v1.8 phase 7.1: asked only when automatic summaries are on (services/summaries.py)

    @field_validator("scene_summary", mode="before")
    @classmethod
    def _summary(cls, v: Any) -> str:
        return v.strip() if isinstance(v, str) else ""


SCHEMA_TEXT = """Return ONLY a JSON object with this shape (omit nothing; use empty arrays when there is nothing):
{
  "events": [{"title": str, "summary": str (factual, 1-2 sentences), "event_type": one of %s,
              "importance": 1-5, "confidence": 0-1, "evidence_kind": one of %s,
              "source_message_ids": [ids from [msg:...] tags], "entities": [character/place names or ids],
              "location": str|null, "in_world_time": str|null, "evidence_excerpt": short quote (<20 words)|null}],
  "facts": [{"subject": name|id|null, "predicate": short category, "content": str, "fact_kind": one of %s,
             "belief_holder": name|null, "known_by": [names; use "player" for the protagonist], "hidden_from": [names],
             "confidence": 0-1, "importance": 1-5, "tentative": bool, "source_message_ids": [...]}],
  "state_changes": [{"kind": one of %s, "payload": {...}, "rationale": str, "confidence": 0-1, "source_message_ids": [...]}],
  "contradictions": [{"description": str, "conflicting_record": str, "source_message_ids": [...]}],
  "character_moods": [{"character": name|id, "slot": 1-6, "confidence": 0-1}]
}
State change payloads: stat {"stat": label, "delta": n} or {"stat": label, "value": v}; relationship {"target_name": name,
"axis": "@AXES@", "delta": n (small and gradual: usually 1-5, 10+ only for a major turning point), "reason": str,
"label": optional short phrase for how they now see the protagonist, "note": optional}; inventory_add/remove {"name": str, "qty": n};
condition_add {"label": str, "severity": "minor|moderate|severe|critical", "note": str}; condition_remove {"label": str};
quest {"title": str, "status": "active|completed|failed", "objective": str}; scene {"location": str, "time": str,
"weather": str, "present_add": [names], "present_remove": [names]}; list_add {"list": "clues|promises|mysteries|goals", "text": str}.
Mood slots: 1 neutral, 2 happy/smiling, 3 sad/sobbing, 4 angry/aggressive, 5 disdain/disgust, 6 love/shy.""" % (
    EVENT_TYPES, EVIDENCE, FACT_KINDS, CHANGE_KINDS)

def schema_text(state: dict[str, Any] | None, summary: bool = False) -> str:
    """SCHEMA_TEXT with this story's own relationship axes (users can add axes; a fixed list hid them from the extractor).
    ``summary``: also ask for the scene summary of the NEW messages (v1.8 phase 7.1, the same request)."""
    from .summaries import CAPTURE_FIELD

    axes = state_service.normalize(state or {}).get("relationship_axes") or ["trust", "affection", "respect", "fear"]
    text = SCHEMA_TEXT.replace("@AXES@", "|".join(str(a) for a in axes))
    if summary:
        text = text.replace('  "character_moods": [{"character": name|id, "slot": 1-6, "confidence": 0-1}]\n}',
                            '  "character_moods": [{"character": name|id, "slot": 1-6, "confidence": 0-1}],\n' + CAPTURE_FIELD + "\n}")
    return text


EXTRACTION_RULES = """You are a careful continuity clerk for an interactive story. Analyse ONLY the messages marked NEW.
Rules:
- Record only what the NEW messages establish. Never record something merely speculated, imagined, offered, or proposed
  but not accepted by the player. Use evidence_kind to distinguish witnessed events, character claims, rumours,
  dreams/visions, plans and hypotheticals.
- Every item must cite the [msg:ID] tags it comes from. Never invent IDs.
- Facts about secrets must list who knows them (known_by) and who must not (hidden_from).
- Propose state changes only when the text clearly implies them (injury, item gained/lost, relationship shift...).
- Prefer few, accurate records over many speculative ones. Low confidence is fine; invention is not.
- Keep summaries short. Inside JSON strings write quoted speech with single quotes (or escape double quotes as \\").
- At most %d events, %d facts, %d state changes and %d contradictions per request: keep only the most important.
  Every text field under 40 words.
""" % (6, 8, 4, 2)


def extraction_schema(axes: list[str] | None = None, summary: bool = False) -> dict[str, Any]:
    """JSON schema for providers with structured outputs (adapters reduce it to their strict subset or downgrade).
    The application still validates everything itself (``Extraction`` + ``_ingest``)."""
    s = {"type": "string"}
    ids = {"type": "array", "items": s}
    num = {"type": "number"}
    obj = lambda props: {"type": "object", "properties": props, "required": list(props)}  # noqa: E731
    return obj({
        "events": {"type": "array", "items": obj({
            "title": s, "summary": s, "event_type": {"type": "string", "enum": EVENT_TYPES}, "importance": {"type": "integer"},
            "confidence": num, "evidence_kind": {"type": "string", "enum": EVIDENCE}, "source_message_ids": ids,
            "entities": ids, "location": {"type": ["string", "null"]}, "in_world_time": {"type": ["string", "null"]},
            "evidence_excerpt": {"type": ["string", "null"]}})},
        "facts": {"type": "array", "items": obj({
            "subject": {"type": ["string", "null"]}, "predicate": s, "content": s,
            "fact_kind": {"type": "string", "enum": FACT_KINDS}, "belief_holder": {"type": ["string", "null"]},
            "known_by": ids, "hidden_from": ids, "confidence": num, "importance": {"type": "integer"},
            "tentative": {"type": "boolean"}, "source_message_ids": ids})},
        # payloads differ per kind: left open here, validated by state_service when a proposal is accepted
        "state_changes": {"type": "array", "items": obj({
            "kind": {"type": "string", "enum": CHANGE_KINDS}, "payload": {"type": "object"}, "rationale": s,
            "confidence": num, "source_message_ids": ids})},
        "contradictions": {"type": "array", "items": obj({"description": s, "conflicting_record": s, "source_message_ids": ids})},
        "character_moods": {"type": "array", "items": obj({"character": s, "slot": {"type": "integer"}, "confidence": num})},
        **({"scene_summary": s} if summary else {}),
    })


REQUIRED_KEYS = ("events", "facts", "state_changes")
# v1.4 live check: GLM-5 answered six short messages with ~2,500 of the 3,000 output tokens; the owner's replies are
# several times longer. The rules ask for at most this many items per chunk and anything beyond is not stored.
MAX_ITEMS = {"events": 6, "facts": 8, "state_changes": 4, "contradictions": 2, "character_moods": 8}


def validate_extraction(obj: dict[str, Any]) -> "Extraction":
    """Envelope check before the item-level validation: an object without the arrays is not an extraction (an empty
    ``{}`` must never silently count as 'nothing happened' and advance the cursor). Lists are bounded."""
    missing = [k for k in REQUIRED_KEYS if not isinstance(obj.get(k), list)]
    if missing:
        raise ValueError(f"required key(s) missing or not a list: {', '.join(missing)}")
    return Extraction.model_validate({**obj, **{k: obj[k][:n] for k, n in MAX_ITEMS.items() if isinstance(obj.get(k), list)}})


FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?\s*```\s*$", re.S)


def _first_object(t: str) -> str | None:
    """The first complete top-level ``{...}`` in ``t``: a quote/escape-aware brace scanner (a greedy regex would join
    two objects or swallow braces from the prose after the JSON)."""
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return t[start:i + 1]
        start = t.find("{", start + 1) if depth else -1  # unbalanced from here: no complete object
    return None


def parse_json_object(text: str) -> dict[str, Any]:
    """Strict JSON first; then one outer Markdown code fence stripped; then the first balanced top-level object in
    surrounding prose. Anything else (no object, cut-off object, a bare list) is a ``ValueError``."""
    t = (text or "").strip()
    m = FENCE.match(t)
    candidates = [t] + ([m.group(1).strip()] if m else [])
    for c in candidates:
        try:
            v = json.loads(c)
        except ValueError:
            continue
        if isinstance(v, dict):
            return v
    for c in candidates:
        obj = _first_object(c)
        if obj is not None:
            v = json.loads(obj)  # a balanced but invalid object raises ValueError with the JSON error position
            if isinstance(v, dict):
                return v
    if "{" in t:
        raise ValueError("The JSON object in the model output is incomplete (cut off or unbalanced)")
    raise ValueError("No JSON object found in model output")


def _dedupe_key(*parts: Any) -> str:
    return hashlib.sha1("|".join(norm(str(p)) for p in parts).encode()).hexdigest()[:40]


# Memory capture answers in JSON that grows with the batch; with the story's reply limit (often 1,024) a 6-message batch
# was cut off mid-JSON (Ollama done_reason "length") and the run failed. Its prompt is small (~3k tokens), so a separate
# budget fits an 8k context. The continuity check sends the whole story context and keeps the reply limit.
EXTRACTION_MAX_TOKENS = 3000
# v1.4 live check (GLM-5): six *short* messages already used 2,400-2,600 output tokens (verbose items), so models with a
# large window get more room; output tokens are billed only when used. Small (local) windows keep 3,000 so that prompt
# plus answer still fit (see chunk_chars).
EXTRACTION_MAX_TOKENS_LARGE, LARGE_WINDOW = 5000, 32768
# v1.4 bounds (owner's story: one failed run per reply re-sent #12–#N until 54+ messages were cut off every time).
# Chunks of at most six messages / ~9,000 characters of new text, item caps per answer and per-call request caps keep an
# automatic run (after a reply) and a manual click from ever turning into an unbounded batch of paid requests.
CHUNK_MAX_MESSAGES = 6
CHUNK_MAX_CHARS = 9000
AUTO_MAX_CHUNKS, AUTO_MAX_REQUESTS = 2, 3
MANUAL_MAX_CHUNKS, MANUAL_MAX_REQUESTS = 4, 8
MAX_ATTEMPTS_PER_CHUNK = 3  # first try + one repair (parse) or up to two halvings (cut off)
TRANSIENT = {"network", "timeout", "rate_limit", "unavailable"}  # worth an automatic retry later; anything else pauses
AUTOMATIC_METHODS = ("automatic_batch", "after_each_turn")


def _capture_params(params: dict[str, Any], context_limit: int | None = None) -> dict[str, Any]:
    from .context_builder import effective_window

    window = effective_window(context_limit, params)
    budget = EXTRACTION_MAX_TOKENS_LARGE if window and window >= LARGE_WINDOW else EXTRACTION_MAX_TOKENS
    return {**params, "temperature": 0.2, "max_tokens": max(int(params.get("max_tokens") or 0), budget)}


def chunk(pending: list[Message], max_messages: int = CHUNK_MAX_MESSAGES, max_chars: int = CHUNK_MAX_CHARS) -> list[Message]:
    """The next bounded slice of unprocessed messages, oldest first; always at least one message (a single very long
    message is still sent alone rather than never)."""
    out: list[Message] = []
    used = 0
    for m in pending[:max(1, max_messages)]:
        if out and used + len(m.content) > max_chars:
            break
        out.append(m)
        used += len(m.content)
    return out


def chunk_chars(resolved, head: str) -> int:
    """New-text budget for one chunk: the default, lowered so prompt + answer fit the model's real window (e.g. Ollama
    num_ctx 8,192) with the same safety margin as story context. Never below ~one message."""
    from .context_builder import SAFETY_MARGIN, effective_window, est_tokens

    params = _capture_params(resolved.params, resolved.profile.context_limit)
    window = effective_window(resolved.profile.context_limit, params)
    if not window:
        return CHUNK_MAX_CHARS
    room = int(window * SAFETY_MARGIN) - int(params["max_tokens"]) - est_tokens(EXTRACTION_RULES + head) - 200
    return max(1500, min(CHUNK_MAX_CHARS, room * 4))


_ID_TOKEN = re.compile(r"[^\s,;]+")


def resolve_source_ids(cited: list[Any], valid: list[str], seqs: dict[int, str]) -> tuple[list[str], int]:
    """Cited message references -> ids of messages in the analysed chunk, plus the number of unusable citations.
    Models copy the prompt's tag ('[msg:ID]', 'msg:ID'), the '#seq' label, a shortened id or several ids in one string
    (live GLM-5 run: 19 of 19 citations unusable with exact matching). Only ids of this chunk can ever result."""
    good: list[str] = []
    bad = 0
    for raw in cited or []:
        for tok in _ID_TOKEN.findall(str(raw)) or [""]:
            s = re.sub(r"^(?:msg|message|id)[:#\-\s]*", "", tok.strip("[](){}\"'.").strip(), flags=re.I)
            hit = s if s in valid else None
            if hit is None and re.fullmatch(r"#?\d+", s):
                hit = seqs.get(int(s.lstrip("#")))
            if hit is None and len(s) >= 8:
                pref = [v for v in valid if v.startswith(s)]
                hit = pref[0] if len(pref) == 1 else None
            if hit is None:
                bad += 1
            elif hit not in good:
                good.append(hit)
    return good, bad


def half(n: int) -> int:
    """A smaller chunk size that keeps player turns and replies together where possible (6 -> 2, 4 -> 2, 3 -> 1, 2 -> 1)."""
    return max(1, (n // 2) & ~1 or 1) if n > 2 else 1


def _error_category(run: MemoryExtractionRun) -> str | None:
    return (run.result_json or {}).get("error_category")


def pause_reason(db: Session, branch_id: str, first_pending_seq: int | None) -> str | None:
    """Why automatic capture must not resend the next range: the latest run on this branch failed for a non-transient
    reason (or a legacy run without a category) starting exactly where capture would start again."""
    if first_pending_seq is None:
        return None
    last = db.scalar(select(MemoryExtractionRun).where(MemoryExtractionRun.branch_id == branch_id)
                     .order_by(MemoryExtractionRun.started_at.desc()).limit(1))
    if last is None or last.status != "failed" or last.start_seq != first_pending_seq:
        return None
    if _error_category(last) in TRANSIENT:
        return None
    return (f"Automatic memory capture is paused: messages #{last.start_seq}–#{last.end_seq} failed "
            f"({(last.error_summary or 'unknown error')[:200]}). Process the next chunk, retry with smaller chunks or skip "
            "that range in Journal → Maintenance.")


AMOUNT_KEYS = ("delta", "qty", "quantity", "amount", "value", "reason", "note")


def _change_identity(branch_id: str, kind: str, payload: dict[str, Any], src: list[str]) -> str:
    """What a proposed change is about (kind + target/axis/item + source messages), ignoring how much it changes."""
    what = {k: v for k, v in payload.items() if k not in AMOUNT_KEYS}
    return _dedupe_key(branch_id, kind, json.dumps(what, sort_keys=True, default=str), *sorted(src))


def _transcript_block(msgs: list[Message], tag: str) -> str:
    return "\n\n".join(f"[msg:{m.id}] ({tag}, #{m.seq}, {m.role}{' OOC' if m.kind == 'ooc' else ''}): {m.content}" for m in msgs)


class ExtractionService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ helpers
    def _lock(self, branch_id: str) -> asyncio.Lock:
        return self.locks.setdefault(branch_id, asyncio.Lock())

    def _resolve(self, db: Session, story: Story):
        pid = self.ctx.extraction_profile_id(db, story)
        if not pid:
            raise NoModelConfigured("No extraction model is configured (Settings → Memory capture).")
        return self.ctx.resolve(db, pid)

    # ------------------------------------------------------------------ main extraction
    @staticmethod
    def _pending(db: Session, branch: MessageBranch, after_seq: int) -> tuple[list[Message], list[Message]]:
        path = [m for m in story_tree.path_messages(db, branch.head_message_id)
                if m.kind in ("story", "ooc") and m.status in ("complete", "partial", "cancelled") and m.content.strip()]
        return [m for m in path if m.seq <= after_seq], [m for m in path if m.seq > after_seq]

    async def run(self, story_id: str, branch_id: str, capture_method: str = "manual", *, rebuild_from_seq: int | None = None,
                  max_chunks: int | None = None, chunk_messages: int | None = None) -> dict[str, Any]:
        """Process the unprocessed range in bounded chunks, oldest first. Each chunk is one request (plus at most one
        repair or halving), committed on its own, so a failure keeps every earlier chunk and never re-sends them."""
        automatic = capture_method in AUTOMATIC_METHODS
        chunks_left = max_chunks or (AUTO_MAX_CHUNKS if automatic else MANUAL_MAX_CHUNKS)
        requests_left = AUTO_MAX_REQUESTS if automatic else MANUAL_MAX_REQUESTS
        size = max(1, min(chunk_messages or CHUNK_MAX_MESSAGES, CHUNK_MAX_MESSAGES))
        totals: dict[str, Any] = {k: 0 for k in ("events", "facts", "proposals", "contradictions", "duplicates_skipped",
                                                 "dropped_invalid_source_ids", "review_items", "relationship_changes_skipped",
                                                 "summaries")}
        done: list[str] = []
        last_run_id, failure, processed = None, None, [None, None]
        async with self._lock(branch_id):
            with self.ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                cur = db.get(ExtractionCursor, branch.id)
                if cur is None:
                    cur = ExtractionCursor(branch_id=branch.id, story_id=story.id, last_seq=-1)
                    db.add(cur)
                    db.flush()
                pos = rebuild_from_seq - 1 if rebuild_from_seq is not None else cur.last_seq
                _, pending = self._pending(db, branch, pos)
                if not pending:
                    return {"status": "nothing_to_do", "message": "No unprocessed messages on this branch.", **totals}
                if automatic:
                    # the next automatic attempt waits for another full batch interval (backoff after any failure)
                    cur.assistant_turns_since = 0
                    paused = pause_reason(db, branch.id, pending[0].seq) if rebuild_from_seq is None else None
                    if paused:
                        log.info("memory capture paused for story %s: %s", story_id, paused)
                        return {"status": "paused", "reason": paused, "remaining_messages": len(pending), **totals}
                try:
                    resolved = self._resolve(db, story)
                except (NoModelConfigured, ConsentRequired) as e:
                    first = chunk(pending, size)
                    run = MemoryExtractionRun(story_id=story.id, branch_id=branch.id, start_message_id=first[0].id,
                                              end_message_id=first[-1].id, start_seq=first[0].seq, end_seq=first[-1].seq,
                                              capture_method=capture_method, status="failed", finished_at=now_iso(),
                                              result_json={"error_category": "no_model" if isinstance(e, NoModelConfigured) else "consent"},
                                              error_summary=str(e) if isinstance(e, NoModelConfigured) else
                                              "The extraction provider needs your cloud data-sharing approval first.")
                    db.add(run)
                    db.flush()
                    return {"status": "failed", "run_id": run.id, "error": run.error_summary, **totals}
            extra = {"json_schema": None}
            while chunks_left > 0 and requests_left > 0:
                with self.ctx.db.session() as db:
                    story = story_tree.get_story(db, story_id)
                    branch = story_tree.get_branch(db, story, branch_id)
                    prior_all, pending = self._pending(db, branch, pos)
                    if not pending:
                        break
                    st_row = state_service.current(db, branch.id)
                    state = st_row.state_json if st_row else {}
                    index = build_index(db, story.world_id, state)
                    player_text, scene_text = render_state(state_service.normalize(state), index)
                    known = ", ".join(f"{e.name} [{e.id}]" for e in list(index.entities.values())[:80] if e.category == "character")
                    want_summary = summaries_svc.enabled(db)
                    head = "\n\n".join(x for x in [
                        schema_text(state, want_summary), f"Known characters: {known}" if known else "",
                        f"Current state:\n{player_text}\n{scene_text}".strip(),
                        "PRIOR CONTEXT (do not extract from these):\n" + _transcript_block(prior_all[-3:], "prior") if prior_all else "",
                    ] if x)
                    if resolved.adapter.supports_json_schema:
                        axes = state_service.normalize(state).get("relationship_axes") or []
                        extra = {"json_schema": extraction_schema(axes, want_summary)}
                    part = chunk(pending, size, chunk_chars(resolved, head))
                    run = MemoryExtractionRun(story_id=story.id, branch_id=branch.id, start_message_id=part[0].id,
                                              end_message_id=part[-1].id, start_seq=part[0].seq, end_seq=part[-1].seq,
                                              capture_method=capture_method, status="running",
                                              provider_id=resolved.provider.id, model_id=resolved.profile.model_id)
                    db.add(run)
                    db.flush()
                    run_id = last_run_id = run.id
                data, diagnostics, part, err = await self._request(resolved, head, part, extra, requests_left)
                requests_left -= len(diagnostics)
                chunks_left -= 1
                with self.ctx.db.session() as db:  # one transaction: records + cursor + run status
                    story = story_tree.get_story(db, story_id)
                    branch = story_tree.get_branch(db, story, branch_id)
                    r = db.get(MemoryExtractionRun, run_id)
                    r.end_message_id, r.end_seq = part[-1].id, part[-1].seq  # a halved chunk covers less
                    if data is None:
                        msg, cat = err
                        r.status, r.error_summary, r.finished_at = "failed", msg, now_iso()
                        r.result_json = {"error_category": cat, "diagnostics": diagnostics, "messages": len(part)}
                        log.warning("memory capture failed for story %s #%d-#%d (%s): %s", story_id, r.start_seq, r.end_seq, cat, msg)
                        failure = {"run_id": run_id, "error": msg, "category": cat}
                        break
                    ids = [m.id for m in part]
                    counts = self._ingest(db, story, branch, data, set(ids), ids, run_id, capture_method,
                                          resolved.provider.provider_type, resolved.profile.model_id)
                    if want_summary and data.scene_summary:  # the memory summary of the same messages (no extra request)
                        msgs = [db.get(Message, i) for i in ids]
                        counts["summaries"] = int(summaries_svc.store(db, story, branch, [m for m in msgs if m],
                                                                      data.scene_summary, source="capture",
                                                                      model_id=resolved.profile.model_id) is not None)
                    cur = db.get(ExtractionCursor, branch.id)
                    pos = part[-1].seq
                    cur.last_seq, cur.last_message_id, cur.updated_at = max(cur.last_seq, pos), ids[-1], now_iso()
                    if not automatic:
                        cur.assistant_turns_since = 0
                    r.status, r.finished_at = "succeeded", now_iso()
                    r.result_json = {**counts, "diagnostics": diagnostics, "messages": len(part)}
                    log.info("memory capture %s #%d-#%d via %s: %s", story_id, r.start_seq, r.end_seq, resolved.profile.model_id,
                             "; ".join(f"#{d['attempt']} {'ok' if d['ok'] else d.get('category')} {d['seconds']}s" for d in diagnostics))
                    for k in totals:
                        totals[k] += counts.get(k, 0)
                    done.append(run_id)
                    processed = [processed[0] if processed[0] is not None else part[0].seq, part[-1].seq]
            with self.ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                remaining = len(self._pending(db, branch, pos)[1])
        out = {**totals, "run_id": last_run_id, "run_ids": done, "processed": processed if done else None,
               "remaining_messages": remaining}
        if failure:
            return {**out, "status": "partial" if done else "failed", "run_id": failure["run_id"], "error": failure["error"],
                    "error_category": failure["category"]}
        return {**out, "status": "succeeded"}

    async def _request(self, resolved, head: str, part: list[Message], extra: dict[str, Any], budget: int):
        """One chunk: first attempt; a parse/schema/empty failure gets one repair attempt (told what was wrong); a cut-off
        answer is not re-sent unchanged — the chunk is halved (down to one message). Returns
        (Extraction | None, diagnostics, the chunk actually covered, (error message, category) | None)."""
        diagnostics: list[dict[str, Any]] = []
        repair_note = ""
        err: tuple[str, str] | None = None
        for attempt in range(1, min(MAX_ATTEMPTS_PER_CHUNK, budget) + 1):
            t0 = time.monotonic()
            msgs = [ChatMessage("user", head + "\n\nNEW messages to analyse:\n" + _transcript_block(part, "NEW"))]
            if repair_note:
                msgs.append(ChatMessage("user", repair_note))
            diag: dict[str, Any] = {"attempt": attempt, "messages": len(part), "seqs": [part[0].seq, part[-1].seq]}
            try:
                raw = await resolved.adapter.complete(resolved.profile.model_id, EXTRACTION_RULES, msgs,
                                                      _capture_params(resolved.params, resolved.profile.context_limit), json_mode=True,
                                                      **({"json_schema": extra["json_schema"]} if extra.get("json_schema") else {}))
                diag["chars"] = len(raw or "")
                data = validate_extraction(parse_json_object(raw))
                diagnostics.append({**diag, "ok": True, "seconds": round(time.monotonic() - t0, 2)})
                return data, diagnostics, part, None
            except ProviderError as e:
                diagnostics.append({**diag, "ok": False, "category": e.category, "reason": e.message[:200],
                                    "details": (e.details or "")[:200], "seconds": round(time.monotonic() - t0, 2)})
                err = (e.message, e.category)
                if e.category == "truncated" and len(part) > 1:
                    part = part[:half(len(part))]  # a smaller range fits the output budget; never resend the same one
                    repair_note = ""
                    continue
                if e.category in ("empty_output", "invalid_response") and not repair_note:
                    repair_note = ("Your previous answer was empty or unusable. Return ONE complete JSON object with the "
                                   "keys events, facts, state_changes, contradictions, character_moods (empty arrays are fine).")
                    continue
                break  # auth / network / rate limit / refusal / still cut off at one message: report, do not loop
            except (ValueError, ValidationError) as e:
                excerpt = ""
                if isinstance(e, json.JSONDecodeError):
                    excerpt = e.doc[max(0, e.pos - 100):e.pos + 40]
                msg = f"Invalid extraction output: {str(e)[:300]}"
                diagnostics.append({**diag, "ok": False, "category": "parse", "reason": msg[:200], "excerpt": excerpt[:160],
                                    "seconds": round(time.monotonic() - t0, 2)})
                err = (msg, "parse")
                if repair_note:
                    break  # one repair attempt only
                repair_note = (f"Your previous answer could not be used ({msg[:200]}). Return the same extraction again as ONE "
                               "complete JSON object with exactly the keys above: no prose, no code fence, short strings, "
                               "and no unescaped double quotes inside strings (use single quotes for speech).")
        if err and len(diagnostics) > 1:
            err = (f"{err[0]} (after {len(diagnostics)} attempts)", err[1])
        return None, diagnostics, part, err

    async def skip_next(self, story_id: str, branch_id: str, note: str = "") -> dict[str, Any]:
        """Explicit player decision: mark the next chunk as not captured (status ``skipped``, never ``succeeded``) so the
        queue can move on past a range the model keeps failing on. No model call."""
        async with self._lock(branch_id):
            with self.ctx.db.session() as db:
                story = story_tree.get_story(db, story_id)
                branch = story_tree.get_branch(db, story, branch_id)
                cur = db.get(ExtractionCursor, branch.id)
                if cur is None:
                    cur = ExtractionCursor(branch_id=branch.id, story_id=story.id, last_seq=-1)
                    db.add(cur)
                    db.flush()
                _, pending = self._pending(db, branch, cur.last_seq)
                if not pending:
                    return {"status": "nothing_to_do", "message": "No unprocessed messages on this branch."}
                part = chunk(pending)
                run = MemoryExtractionRun(story_id=story.id, branch_id=branch.id, start_message_id=part[0].id,
                                          end_message_id=part[-1].id, start_seq=part[0].seq, end_seq=part[-1].seq,
                                          capture_method="manual_skip", status="skipped", finished_at=now_iso(),
                                          error_summary=note or "Skipped by the player: these messages were not captured.",
                                          result_json={"messages": len(part)})
                db.add(run)
                cur.last_seq, cur.last_message_id, cur.updated_at = part[-1].seq, part[-1].id, now_iso()
                db.flush()
                return {"status": "skipped", "run_id": run.id, "skipped": [part[0].seq, part[-1].seq],
                        "remaining_messages": len(pending) - len(part)}

    @staticmethod
    def _seq(db: Session, mid: str) -> int:
        m = db.get(Message, mid)
        return m.seq if m else -1

    def _ingest(self, db: Session, story: Story, branch: MessageBranch, data: Extraction, valid_ids: set[str],
                ordered_ids: list[str], run_id: str, method: str, provider_type: str, model_id: str) -> dict[str, Any]:
        cfg = settings_service.get_all(db)
        threshold = float(cfg["candidate_confidence_threshold"])
        auto_status = cfg["event_auto_store_status"]
        st_row = state_service.current(db, branch.id)
        index = build_index(db, story.world_id, st_row.state_json if st_row else {})
        meta = {"run_id": run_id, "provider_type": provider_type, "model_id": model_id, "extracted_at": now_iso()}
        counts = {"events": 0, "facts": 0, "proposals": 0, "contradictions": 0, "duplicates_skipped": 0,
                  "dropped_invalid_source_ids": 0, "review_items": 0, "relationship_changes_skipped": 0}
        analysed = analysed_replies(db, ordered_ids)
        from ..models import Avatar
        av = db.get(Avatar, story.active_avatar_id) if story.active_avatar_id else None
        me = {x for x in [av.name if av else (story.avatar_snapshot_json or {}).get("name")] if x}
        me |= {w for n in me for w in n.split() if len(w) >= 3}

        seqs ={m.seq: m.id for m in (db.get(Message, i) for i in ordered_ids) if m is not None}

        def sources(ids: list[str]) -> list[str]:
            good, bad = resolve_source_ids(ids, ordered_ids, seqs)
            counts["dropped_invalid_source_ids"] += bad
            return good

        def resolve_names(names: list[str]) -> tuple[list[str], list[str]]:
            ok, unresolved = [], []
            for n in names:
                if n == "player":
                    ok.append("player")
                    continue
                rid = n if n in index.entities else index.resolve(n)
                (ok if rid else unresolved).append(rid or n)
            return list(dict.fromkeys(ok)), unresolved

        existing_keys = {k for (k,) in db.execute(select(StoryEvent.dedupe_key).where(StoryEvent.branch_id == branch.id))}
        for ev in data.events:
            src = sources(ev.source_message_ids)
            key = _dedupe_key(branch.id, ev.title, ",".join(sorted(src)) or ev.summary[:80])
            if key in existing_keys:
                counts["duplicates_skipped"] += 1
                continue
            existing_keys.add(key)
            ents, unresolved = resolve_names(ev.entities)
            uncertain = ev.confidence < threshold or ev.evidence_kind != "witnessed" or not src
            status = "candidate" if (uncertain or auto_status == "candidate") else auto_status
            loc = index.resolve(ev.location) if ev.location else None
            db.add(StoryEvent(story_id=story.id, branch_id=branch.id, branch_sequence=story_tree.next_event_sequence(db, branch),
                              in_world_time=ev.in_world_time, event_type=ev.event_type, title=ev.title[:300],
                              summary=ev.summary, entity_ids_json=ents, unresolved_entities_json=unresolved,
                              location_id=loc or ev.location, importance=ev.importance, confidence=ev.confidence,
                              verification_status=status, evidence_kind=ev.evidence_kind, source_message_ids_json=src,
                              evidence_excerpt=(ev.evidence_excerpt or "")[:200] or None, capture_method=method,
                              extraction_metadata_json=meta, dedupe_key=key,
                              notes="" if src else "No valid source message cited by the extractor."))
            counts["events"] += 1
            counts["review_items"] += status == "candidate"
        fact_keys = {k for (k,) in db.execute(select(EntityFact.dedupe_key).where(EntityFact.story_id == story.id))}
        for f in data.facts:
            src = sources(f.source_message_ids)
            subj = (f.subject if f.subject in index.entities else index.resolve(f.subject)) if f.subject else None
            key = _dedupe_key(subj or f.subject or "", f.content)
            if key in fact_keys:
                counts["duplicates_skipped"] += 1
                continue
            fact_keys.add(key)
            # unresolved names are kept verbatim: a knowledge boundary must never be silently dropped
            known = sum(resolve_names(f.known_by), [])
            hidden = sum(resolve_names(f.hidden_from), [])
            holder = index.resolve(f.belief_holder) if f.belief_holder else None
            status = "candidate" if (f.tentative or f.confidence < threshold or not src) else "active"
            db.add(EntityFact(story_id=story.id, branch_id=branch.id, scope="branch", subject_entity_id=subj,
                              subject_label=f.subject, predicate=f.predicate[:120], content=f.content, fact_kind=f.fact_kind,
                              belief_holder_id=holder or f.belief_holder, knowledge_json={"known_by": known, "hidden_from": hidden},
                              status=status, confidence=f.confidence, importance=f.importance, source_message_ids_json=src,
                              capture_method=method, dedupe_key=key, extraction_metadata_json=meta))
            counts["facts"] += 1
            counts["review_items"] += status == "candidate"
        prop_keys = {k for (k,) in db.execute(select(StateProposal.dedupe_key).where(StateProposal.story_id == story.id,
                                                                                    StateProposal.dedupe_key.is_not(None)))}
        # the same change from the same messages with a different amount (a model re-run says +4 instead of +5) is
        # still the same moment: proposing it again would let it be applied twice
        prop_ids = {_change_identity(branch.id, p.kind, p.payload_json or {}, p.source_message_ids_json or [])
                    for p in db.scalars(select(StateProposal).where(StateProposal.branch_id == branch.id))
                    if p.source_message_ids_json}
        for ch in data.state_changes:
            if ch.kind not in CHANGE_KINDS:
                continue
            payload = dict(ch.payload)
            if ch.kind == "relationship":
                from .relationships import PROTAGONIST_WORDS
                tname = str(payload.get("target_name") or "").strip()
                # v1.5: an explicit null never blocked resolution before (setdefault), and a record named "player" was
                # created from "the professors -> the player" (owner's story). The NPC whose view changes must be
                # identifiable; the protagonist as an unnamed target is not a relationship record.
                if not payload.get("source_id") and tname.casefold() in PROTAGONIST_WORDS | {n.casefold() for n in me}:
                    counts["relationship_changes_skipped"] += 1
                    continue
                if tname:
                    tid = payload.get("target_id")
                    payload["target_id"] = tid if tid in index.entities else index.resolve(tname)
            if ch.kind == "scene":
                for k in ("present_add", "present_remove"):
                    if payload.get(k):  # only canonical ids; an unresolved name ("player") is never stored as an id
                        payload[k] = [c for c in (index.resolve(n) for n in payload[k]) if c]
            src = sources(ch.source_message_ids)
            if ch.kind == "relationship" and (not src or set(src) & analysed):
                # unsupported (no cited message), or that reply's relationship changes were already evaluated by scene
                # analysis (v1.4: the same handshake was counted twice, +2 from analysis and +3 from here)
                counts["relationship_changes_skipped"] += 1
                continue
            # same change from the same messages (re-extraction / rebuild) is proposed only once
            key = _dedupe_key(branch.id, ch.kind, json.dumps(payload, sort_keys=True, default=str), *sorted(src))
            ident = _change_identity(branch.id, ch.kind, payload, src) if src else None
            if key in prop_keys or ident in prop_ids:
                counts["duplicates_skipped"] += 1
                continue
            prop_keys.add(key)
            if ident:
                prop_ids.add(ident)
            db.add(StateProposal(story_id=story.id, branch_id=branch.id, kind=ch.kind, payload_json=payload,
                                 rationale=ch.rationale, source_message_ids_json=src, dedupe_key=key,
                                 confidence=ch.confidence, extraction_run_id=run_id))
            counts["proposals"] += 1
        for c in data.contradictions:
            db.add(StoryEvent(story_id=story.id, branch_id=branch.id, branch_sequence=story_tree.next_event_sequence(db, branch),
                              event_type="other", title=f"Possible contradiction: {c.description[:120]}",
                              summary=c.description + (f" (conflicts with: {c.conflicting_record})" if c.conflicting_record else ""),
                              verification_status="candidate", evidence_kind="claim", confidence=0.5, importance=3,
                              source_message_ids_json=sources(c.source_message_ids), capture_method=method,
                              tags_json=["contradiction"], extraction_metadata_json=meta,
                              dedupe_key=_dedupe_key(branch.id, "contradiction", c.description)))
            counts["contradictions"] += 1
            counts["review_items"] += 1
        moods = []
        for md in data.character_moods:
            cid = md.character if md.character in index.entities else index.resolve(md.character)
            if cid and 1 <= md.slot <= 6:
                moods.append({"character_id": cid, "slot": md.slot, "evidence": "extraction", "confidence": md.confidence})
        if moods and cfg.get("auto_apply_expression_suggestions"):
            apply_expressions(story, branch.id, moods, source="extraction", message_id=ordered_ids[-1])
        return counts

    # ------------------------------------------------------------------ recaps
    async def generate_recap(self, story_id: str, instructions: str = "") -> dict[str, Any]:
        with self.ctx.db.session() as db:
            story = story_tree.get_story(db, story_id)
            branch = story_tree.get_branch(db, story)
            resolved = self.ctx.resolve(db, self.ctx.extraction_profile_id(db, story) or self.ctx.story_profile_id(db, story))
            path = [m for m in story_tree.path_messages(db, branch.head_message_id) if m.kind in ("story", "ooc") and m.content.strip()]
            if not path:
                raise ValueError("Nothing to summarise yet.")
            prev = db.scalar(select(Recap).where(Recap.branch_id == branch.id, Recap.status == "active").order_by(Recap.version.desc()).limit(1))
            from .context_builder import visible_events
            evs = visible_events(db, story, branch, {m.id for m in path})
            ev_text = "\n".join(f"- #{e.branch_sequence} {e.title}: {e.summary} [{e.verification_status}]" for e in evs[-40:])
            budget_chars = 60000
            transcript, used = [], 0
            for m in reversed(path):
                line = f"#{m.seq} {m.role}: {m.content}"
                if used + len(line) > budget_chars:
                    break
                transcript.append(line)
                used += len(line)
            transcript.reverse()
            first_seq = path[-len(transcript)].seq if transcript else path[0].seq
            prompt = "\n\n".join(x for x in [
                f"Previous recap (covers up to #{prev.end_seq}):\n{prev.content}" if prev else "",
                f"Recorded journal events:\n{ev_text}" if ev_text else "",
                f"Transcript (messages #{first_seq}–#{path[-1].seq}):\n" + "\n\n".join(transcript),
                instructions or "",
            ] if x)
            from .commands import SEEDS
            sys = next(s["template"] for s in SEEDS if s["name"] == "recap").replace("{{input}}", "")
            start_id, end_id, end_seq = path[0].id, path[-1].id, path[-1].seq
            version = (db.scalar(select(Recap.version).where(Recap.branch_id == branch.id).order_by(Recap.version.desc()).limit(1)) or 0) + 1
        text = await resolved.adapter.complete(resolved.profile.model_id, sys, [ChatMessage("user", prompt)], resolved.params)
        with self.ctx.db.session() as db:
            story = story_tree.get_story(db, story_id)
            auto = settings_service.get(db, "recap_auto_replace")
            rc = Recap(story_id=story_id, branch_id=branch.id, version=version, content=text.strip(), start_message_id=start_id,
                       end_message_id=end_id, start_seq=0, end_seq=end_seq, status="candidate", source="generated")
            db.add(rc)
            db.flush()
            if auto:
                activate_recap(db, rc)
            return rc.to_dict()

    # ------------------------------------------------------------------ continuity / recon
    async def continuity_check(self, story_id: str, focus: str, user_input: str = "") -> dict[str, Any]:
        from . import context_builder

        with self.ctx.db.session() as db:
            story = story_tree.get_story(db, story_id)
            branch = story_tree.get_branch(db, story)
            resolved = self.ctx.resolve(db, self.ctx.extraction_profile_id(db, story) or self.ctx.story_profile_id(db, story))
            built = context_builder.build(db, story, branch, context_limit=resolved.profile.context_limit, params=resolved.params)
            path = story_tree.path_messages(db, branch.head_message_id)[-12:]
            transcript = _transcript_block(path, "recent")
        from .commands import SEEDS
        instr = next(s["template"] for s in SEEDS if s["name"] == focus).replace("{{input}}", user_input)
        prompt = (f"{instr}\n\nReturn ONLY JSON: {{\"issues\": [{{\"description\": str, \"records\": [str], \"message_ids\": "
                  f"[ids from [msg:...] tags], \"suggested_fix\": str, \"fix_type\": \"edit_message|create_memory|update_state|none\", "
                  f"\"fix_text\": str}}], \"summary\": str}}\n\nRecent transcript:\n{transcript}")
        raw = await resolved.adapter.complete(resolved.profile.model_id, built.system, [ChatMessage("user", prompt)],
                                              {**resolved.params, "temperature": 0.2}, json_mode=True)
        try:
            data = parse_json_object(raw)
        except ValueError:
            data = {"issues": [], "summary": raw.strip()[:4000], "unstructured": True}
        ids = {m.id for m in path}
        for it in data.get("issues", []) or []:
            it["message_ids"] = [i for i in it.get("message_ids", []) if i in ids]
        data["checked_messages"] = [m.id for m in path]
        return data

    # ------------------------------------------------------------------ state suggestions for one turn
    async def suggest_state_changes(self, story_id: str, message_id: str | None = None) -> dict[str, Any]:
        with self.ctx.db.session() as db:
            story = story_tree.get_story(db, story_id)
            branch = story_tree.get_branch(db, story)
            resolved = self._resolve(db, story)
            path = [m for m in story_tree.path_messages(db, branch.head_message_id) if m.content.strip() and m.kind == "story"]
            if message_id:
                idx = next((i for i, m in enumerate(path) if m.id == message_id), len(path) - 1)
                path = path[: idx + 1]
            new = path[-2:]
            if not new:
                raise ValueError("No completed turn to analyse.")
            st_row = state_service.current(db, branch.id)
            index = build_index(db, story.world_id, st_row.state_json if st_row else {})
            p_text, s_text = render_state(state_service.normalize(st_row.state_json if st_row else {}), index)
            prompt = (schema_text(st_row.state_json if st_row else {}) +"\n\nOnly fill \"state_changes\" (and character_moods if obvious); leave other arrays empty.\n\n"
                      f"Current state:\n{p_text}\n{s_text}\n\nNEW messages to analyse:\n" + _transcript_block(new, "NEW"))
            valid = {m.id for m in new}
        raw = await resolved.adapter.complete(resolved.profile.model_id, EXTRACTION_RULES, [ChatMessage("user", prompt)],
                                              _capture_params(resolved.params, resolved.profile.context_limit), json_mode=True)
        data = Extraction.model_validate(parse_json_object(raw))
        n = skipped = 0
        with self.ctx.db.session() as db:
            analysed = analysed_replies(db, list(valid))
            known = {_change_identity(branch.id, p.kind, p.payload_json or {}, p.source_message_ids_json or [])
                     for p in db.scalars(select(StateProposal).where(StateProposal.branch_id == branch.id))}
            for ch in data.state_changes:
                if ch.kind not in CHANGE_KINDS:
                    continue
                src = [i for i in ch.source_message_ids if i in valid]
                ident = _change_identity(branch.id, ch.kind, ch.payload or {}, src)
                if (ch.kind == "relationship" and (not src or set(src) & analysed)) or ident in known:
                    skipped += 1  # owned by scene analysis / unsupported / already proposed
                    continue
                known.add(ident)
                db.add(StateProposal(story_id=story_id, branch_id=branch.id, kind=ch.kind, payload_json=ch.payload,
                                     rationale=ch.rationale, confidence=ch.confidence, source_message_ids_json=src,
                                     dedupe_key=ident))
                n += 1
        return {"proposals": n, "skipped": skipped}


def analysed_replies(db: Session, message_ids: list[str]) -> set[str]:
    """Replies whose relationship changes were already evaluated by scene analysis v2 (it owns them per reply)."""
    from ..models import TurnAnalysis

    if not message_ids:
        return set()
    return {mid for (mid,) in db.execute(select(TurnAnalysis.message_id).where(
        TurnAnalysis.message_id.in_(message_ids), TurnAnalysis.status == "succeeded", TurnAnalysis.schema_version >= 2))}


def activate_recap(db: Session, rc: Recap) -> None:
    for old in db.scalars(select(Recap).where(Recap.branch_id == rc.branch_id, Recap.kind == rc.kind, Recap.status == "active")):
        if old.id != rc.id:
            old.status = "superseded"
    rc.status = "active"
