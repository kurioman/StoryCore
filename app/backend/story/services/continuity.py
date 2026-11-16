"""Continuity checks that cost no tokens (v0.5, phase 7.6).

* Repetition: phrases the narrator used in several recent replies, and replies that open the same way. The next
  request asks to vary them (a few words in the per-turn context). Small local models repeat a lot.
* A character the journal records as dead who speaks in a reply.
* The in-story time going back on the same day.
* A reply that contradicts a pinned memory: the scene analysis (already made after each reply) is given the pinned
  memories and reports a clear contradiction in its "warnings" (a few lines added to a request that exists anyway).

Every finding is a notice under the reply (``generation_metadata_json.continuity_alerts``: {"kind", ...}); the reply
is never changed. The player can regenerate or edit it.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Message, Story, StoryEvent, TurnAnalysis

REPEAT_N = 5  # words in a repeated phrase
REPEAT_REPLIES = 6  # recent narrator replies compared
MAX_PHRASES = 5
TAG = re.compile(r"\[[^\[\]\n]{1,40}:\s*\d\]")
WORD = re.compile(r"[\w’'-]+", re.U)


def _words(text: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in WORD.findall(TAG.sub(" ", text or ""))]


def repeated_phrases(replies: list[str], n: int = REPEAT_N, limit: int = MAX_PHRASES) -> list[str]:
    """Phrases repeated across these replies: runs of words covered by an ``n``-word sequence found in at least two
    replies (meaningful ones: two words of 4+ letters), the run found in the most replies first, shorter runs preferred
    and runs containing a chosen one skipped; plus a reply opening (first four words) used twice. Deterministic."""
    texts = [_words(t) for t in replies]
    counts: Counter = Counter()
    for w in texts:
        counts.update({tuple(w[i:i + n]) for i in range(len(w) - n + 1)
                       if sum(len(x) >= 4 for x in w[i:i + n]) >= 2})
    rep = {g for g, c in counts.items() if c >= 2}
    runs: set[str] = set()
    for w in texts:
        mark = [False] * len(w)
        for i in range(len(w) - n + 1):
            if tuple(w[i:i + n]) in rep:
                mark[i:i + n] = [True] * n
        i = 0
        while i < len(w):
            if mark[i]:
                j = i
                while j < len(w) and mark[j]:
                    j += 1
                runs.add(" ".join(w[i:j]))
                i = j
            else:
                i += 1
    joined = [" ".join(w) for w in texts]
    support = {r: sum(r in t for t in joined) for r in runs}
    out: list[str] = []
    for r in sorted(runs, key=lambda r: (-support[r], len(r), r)):
        if any(r in o or o in r for o in out):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    openings = Counter(" ".join(w[:4]) for w in texts if len(w) >= 4)
    for o, c in sorted(openings.items(), key=lambda x: (-x[1], x[0]))[:2]:
        if c >= 2 and all(o not in p for p in out) and len(out) < limit + 1:
            out.append(o + " …")
    return out


def repetition_block(convo: list[Message]) -> str:
    replies = [m.content for m in convo if m.role == "assistant" and m.kind == "story"][-REPEAT_REPLIES:]
    if len(replies) < 3:
        return ""
    phrases = repeated_phrases(replies)
    if not phrases:
        return ""
    return ("Your recent replies reuse these phrasings. Vary your wording and sentence openings; do not reuse them: "
            + "; ".join(f"«{p}»" for p in phrases) + ".")


# ------------------------------------------------------------------------------------------- notices
def set_alerts(m: Message, kind: str, items: list[dict[str, Any]]) -> None:
    """Replace this kind of notice on the reply (the JSON column is reassigned so it is saved)."""
    md = dict(m.generation_metadata_json or {})
    kept = [a for a in md.get("continuity_alerts") or [] if a.get("kind") != kind]
    md["continuity_alerts"] = kept + [{"kind": kind, **i} for i in items]
    if not md["continuity_alerts"]:
        md.pop("continuity_alerts")
    m.generation_metadata_json = md


def dead_characters(db: Session, story_id: str, path_ids: set[str], before_seq: int) -> set[str]:
    """Characters whose death the journal records (witnessed, not rejected) in messages before this reply."""
    seqs = {m.id: m.seq for m in db.scalars(select(Message).where(Message.story_id == story_id))}
    out: set[str] = set()
    for e in db.scalars(select(StoryEvent).where(StoryEvent.story_id == story_id, StoryEvent.event_type == "death")):
        if e.verification_status in ("rejected", "candidate") or e.superseded_by_event_id or e.stale:
            continue
        if e.evidence_kind not in ("witnessed", "confirmed"):
            continue
        src = [s for s in e.source_message_ids_json or [] if s in path_ids]
        if src and max(seqs.get(s, 10 ** 9) for s in src) < before_seq:
            out |= set(e.entity_ids_json or [])
    return out


def check_speakers(db: Session, message_id: str) -> list[dict[str, Any]]:
    """After a reply and its analysis: a character recorded as dead who speaks in it."""
    from . import story_tree
    from .entities import build_index
    from . import state_service

    m = db.get(Message, message_id)
    if m is None or m.role != "assistant" or m.kind != "story":
        return []
    story = db.get(Story, m.story_id)
    branch = story_tree.get_branch(db, story, m.branch_id)
    path_ids = story_tree.path_ids(db, branch)
    dead = dead_characters(db, story.id, path_ids, m.seq)
    if not dead:
        set_alerts(m, "dead_speaks", [])
        return []
    speakers: set[str] = set()
    ta = db.scalar(select(TurnAnalysis).where(TurnAnalysis.message_id == m.id))
    if ta is not None and ta.status == "succeeded":
        speakers |= {s.get("character_id") for s in ta.speakers_json or [] if isinstance(s, dict)}
    else:
        st = state_service.current(db, branch.id)
        index = build_index(db, story.world_id, st.state_json if st else {})
        for t in (m.generation_metadata_json or {}).get("portrait_tags_raw") or []:
            cid = index.resolve(t.get("name") or "")
            if cid:
                speakers.add(cid)
        if m.speaker_character_id:
            speakers.add(m.speaker_character_id)
    st = state_service.current(db, branch.id)
    index = build_index(db, story.world_id, st.state_json if st else {})
    found = [{"character_id": c, "name": index.name(c)} for c in sorted(speakers & dead)]
    set_alerts(m, "dead_speaks", found)
    return found


# in-story time of day, as minutes, for "the time went back"
BROAD = [(r"\b(?:midnight|minuit)\b", 24 * 60), (r"\b(?:dawn|daybreak|sunrise|aube|aurore|lever du soleil)\b", 6 * 60),
         (r"\b(?:early morning|petit matin)\b", 7 * 60), (r"\b(?:morning|matin|matinée)\b", 9 * 60),
         (r"\b(?:afternoon|après-midi)\b", 15 * 60), (r"\b(?:noon|midday|midi)\b", 12 * 60),
         (r"\b(?:dusk|sunset|twilight|crépuscule|coucher du soleil)\b", 19 * 60),
         (r"\b(?:evening|soir|soirée)\b", 20 * 60), (r"\b(?:night|nuit)\b", 22 * 60)]


def time_rank(value: Any) -> int | None:
    t = str(value or "").strip().lower()
    if not t:
        return None
    m = re.match(r"^(\d{1,2})[:h](\d{2})", t)
    if m:
        return int(m.group(1)) % 24 * 60 + int(m.group(2))
    for pattern, minutes in BROAD:
        if re.search(pattern, t):
            return minutes
    return None


def time_went_back(old: Any, new: Any) -> bool:
    """Same day, and the new time is clearly earlier (more than an hour and a half; not across midnight)."""
    a, b = time_rank(old), time_rank(new)
    if a is None or b is None:
        return False
    if a >= 22 * 60 and b <= 4 * 60:  # night → small hours: the clock went on
        return False
    return b < a - 90
