"""Portrait tags (v1.7): the narrator marks who speaks and with which expression, e.g. ``[Selphina:3] "I'm sorry..."``.

Why: portraits used to wait for the scene analysis, a second request that reads the finished reply (30 s to 2 min on a
local model). With tags the narrator says it while writing, so the portrait is known the moment the reply ends.

* ``TagFilter`` removes the tags from the text as it streams: the player never sees them, the stored reply has none.
  It records each tag (name, expression 1-6, the text that followed it).
* ``apply`` (after the reply is saved) resolves each tag to a lore character, finds its paragraph and quoted line, and
  writes the reply's portraits at once (a ``succeeded`` scene-analysis row with ``speaking`` beats) and the expressions.
  The scene analysis still runs afterwards for presence, relationships, the clock and suggestions; it keeps the tagged
  speakers and expressions (``turn_analysis``).
* ``retag`` puts the tags back into earlier replies when they are sent to the model again, so the narrator keeps seeing
  the format it is asked to write (the saved story never contains them). v0.6: also where the app found the speaker
  itself (live detection, ``live_speakers.py``, or the scene analysis, ``from_beats``) when the narrator wrote none.

Syntax: ``[Name:N]`` (also ``[Name|N]``, ``[Name+N]``, ``[Name#N]``), N = 1-6. Expressions: see ``EXPRESSIONS``.
A tag whose name is not a known character is still removed from the text; it simply shows no portrait.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import Message, Story, TurnAnalysis, now_iso
from . import settings_service, state_service, story_tree
from .entities import build_index
from .music import MUSIC_TAG

TAG = re.compile(r"\[\s*([^\[\]\n:|+#]{1,40}?)\s*[:|+#]\s*([1-6])\s*\]")
MAX_TAG_LEN = 48
QUOTED = re.compile(r'["“«]([^"“”«»\n]{1,600})["”»]')

# What each portrait number means (the same numbers as the portrait files: name_1.webp ... name_6.webp)
EXPRESSION_LINE = ("1 neutral (use it when unsure), 2 happy / smiling, 3 sad / sobbing, 4 angry / aggressive, "
                   "5 disdain / disgust, 6 love / shy")


def instruction(protagonist: str) -> str:
    """Narrator rule (context_builder adds it near the end of the system prompt)."""
    return (f"Before each line spoken by a named character, write their portrait tag [Name:N] (the name as the lore "
            f"writes it), N = expression: {EXPRESSION_LINE}. Example: [Selphina:3] \"I... I didn't mean it.\" One tag per "
            f"spoken line; change N with their emotion. Never tag {protagonist} or unnamed extras. The app removes the "
            "tags and shows the portraits.")


class TagFilter:
    """Removes portrait tags from a token stream (a tag may be split across chunks) and records them."""

    def __init__(self) -> None:
        self.buf = ""
        self.clean = ""
        self.tags: list[dict[str, Any]] = []
        self.music: list[dict[str, Any]] = []  # v0.5 music tags: [Music:combat] (services/music.py)
        self._eat = False  # drop the spaces (and one line break) right after a tag
        self._at_line_start = True

    def _emit(self, s: str, out: list[str]) -> None:
        if self._eat and s:
            s = s.lstrip(" \t")
            if s.startswith("\n") and self._at_line_start:  # a tag on its own line: drop that line break too
                s = s[1:]
            if s:
                self._eat = False
        if s:
            out.append(s)
            self.clean += s

    def feed(self, piece: str) -> str:
        self.buf += piece
        out: list[str] = []
        while self.buf:
            i = self.buf.find("[")
            if i < 0:
                self._emit(self.buf, out)
                self.buf = ""
                break
            self._emit(self.buf[:i], out)
            rest = self.buf[i:]
            j = rest.find("]")
            if j < 0:
                if len(rest) > MAX_TAG_LEN or "\n" in rest:
                    self._emit(rest[0], out)
                    self.buf = rest[1:]
                    continue
                self.buf = rest  # maybe a tag still arriving
                break
            mm = MUSIC_TAG.fullmatch(rest[:j + 1])
            if mm:
                self._at_line_start = not self.clean or self.clean.endswith("\n")
                self.music.append({"tag": mm.group(1).strip(), "offset": len(self.clean)})
                self._eat = True
                self.buf = rest[j + 1:]
                continue
            m = TAG.fullmatch(rest[:j + 1])
            if m:
                self._at_line_start = not self.clean or self.clean.endswith("\n")
                self.tags.append({"name": m.group(1).strip(), "slot": int(m.group(2)), "offset": len(self.clean)})
                self._eat = True
                self.buf = rest[j + 1:]
            else:
                self._emit(rest[0], out)
                self.buf = rest[1:]
        return "".join(out)

    def flush(self) -> str:
        tail, self.buf = self.buf, ""
        out: list[str] = []
        self._emit(tail, out)
        return "".join(out)

    def found(self) -> list[dict[str, Any]]:
        """The tags with the text that followed each (used to find its place in the final reply)."""
        return [{"name": t["name"], "slot": t["slot"], "snippet": self.clean[t["offset"]:t["offset"] + 80].strip()}
                for t in self.tags]


def _paragraphs(text: str) -> list[tuple[int, int]]:
    """(start, end) of the non-empty blank-line-separated paragraphs (the same split as turn_analysis.locate)."""
    out, pos = [], 0
    for part in re.split(r"(\n\s*\n)", text):
        if part and not re.fullmatch(r"\n\s*\n", part) and part.strip():
            out.append((pos, pos + len(part)))
        pos += len(part)
    return out


def apply(db: Session, message_id: str) -> bool:
    """Show the reply's portraits at once: from the narrator's tags, or (v0.6) from the speakers found while it was
    written (services/live_speakers.py). True when at least one portrait was placed; the scene analysis then keeps the
    tagged ones and replaces the detected ones when it finds the speakers itself."""
    m = db.get(Message, message_id)
    if m is None or m.role != "assistant" or m.kind != "story" or m.status != "complete":
        return False
    md = dict(m.generation_metadata_json or {})
    raw = md.get("portrait_tags_raw") or []
    live = [x for x in md.get("live_speakers") or [] if x.get("source") == "detected"]
    if not raw and not live:
        return False
    story = db.get(Story, m.story_id)
    st_row = state_service.current(db, m.branch_id)
    state = state_service.normalize(st_row.state_json if st_row else {})
    index = build_index(db, story.world_id, state)
    me = {n.casefold() for n in (str((story.avatar_snapshot_json or {}).get("name") or ""),
                                 str((state.get("player") or {}).get("name") or "")) if n}
    text = m.content
    paras = _paragraphs(text)

    def place(name: str, cid: str, slot: int, pos: int, source: str, conf: float, mood: bool = False) -> dict[str, Any]:
        para = next((k for k, (a, b) in enumerate(paras) if a <= pos < b), None)
        end = paras[para][1] if para is not None else len(text)
        q = QUOTED.search(text, pos, end)
        line = q.group(0) if q else None
        return {"name": name, "character_id": cid, "slot": int(slot), "pos": pos, "paragraph": para, "line": line,
                "anchor": line or text[pos:pos + 60].strip(), "source": source, "confidence": conf, "mood": mood}

    resolved: list[dict[str, Any]] = []
    search_from = 0
    for t in raw:
        name = t.get("name") or ""
        cid = index.resolve(name) or index.resolve(name.split(" ")[0])
        if not cid or index.entities[cid].category != "character" or name.casefold() in me:
            continue
        snip = (t.get("snippet") or "")[:40]
        pos = text.find(snip, search_from) if snip else -1
        if pos < 0 and snip:
            pos = text.find(snip)
        if pos < 0:
            continue
        search_from = pos + 1
        resolved.append(place(name, cid, int(t["slot"]), pos, "tag", 1.0))
    if resolved:  # v0.6: a later line of a tagged character that the narrator left untagged keeps its own portrait
        tagged_paras = {r["paragraph"] for r in resolved}
        for x in live:
            cid, pos = x.get("character_id"), x.get("pos")
            if not isinstance(pos, int) or not 0 <= pos < len(text):
                continue
            earlier = [r for r in resolved if r["character_id"] == cid and r["source"] == "tag" and r["pos"] <= pos]
            para = next((k for k, (a, b) in enumerate(paras) if a <= pos < b), None)
            if earlier and para not in tagged_paras:  # the mood read in its paragraph, else their last tag's
                slot = int(x.get("slot") or 1) if x.get("mood") else earlier[-1]["slot"]
                resolved.append(place(earlier[-1]["name"], cid, slot, pos, "detected", 0.8, bool(x.get("mood"))))
        resolved.sort(key=lambda r: r["pos"])
    if not resolved:  # v0.6: no tag written (most small models): the speakers found next to the quotes
        for x in live:
            cid, pos = x.get("character_id"), x.get("pos")
            if cid in index.entities and index.entities[cid].category == "character" and isinstance(pos, int) \
                    and 0 <= pos < len(text) and index.name(cid).casefold() not in me:
                resolved.append(place(index.name(cid), cid, int(x.get("slot") or 1), pos, "detected",
                                      float(x.get("confidence") or 0.6), bool(x.get("mood"))))
    md["portrait_tags"] = [{k: r[k] for k in ("name", "character_id", "slot", "pos", "paragraph", "source")}
                           for r in resolved]
    m.generation_metadata_json = md
    if not resolved:
        return False
    tagged = any(r["source"] == "tag" for r in resolved)

    cfg = settings_service.get_all(db)
    branch = story_tree.get_branch(db, story, m.branch_id)
    held = ((story.settings_json or {}).get("expressions") or {}).get(branch.id) or {}
    auto = bool(cfg.get("auto_apply_expression_suggestions", True))

    def slot_for(r: dict[str, Any]) -> int:
        h = held.get(r["character_id"]) or {}
        return int(h.get("slot") or 1) if (h.get("locked") or not auto) else r["slot"]

    beats, seen = [], set()
    for r in resolved:
        key = (r["character_id"], r["paragraph"])
        if key in seen:
            beats = [b for b in beats if (b["character_id"], b["paragraph"]) != key]  # the later tag in a paragraph wins
        seen.add(key)
        beats.append({"character_id": r["character_id"], "expression": slot_for(r), "beat": "speaking",
                      "anchor": r["anchor"], "paragraph": r["paragraph"], "source": r["source"],
                      **({"mood": True} if r.get("mood") else {})})
    last = {}
    for r in resolved:
        last[r["character_id"]] = r
    speakers = [{"character_id": c, "expression": slot_for(r), "evidence": r["anchor"], "confidence": r["confidence"]}
                for c, r in last.items()]
    dialogue = [{"character_id": r["character_id"], "text": r["line"]} for r in resolved if r["line"]]
    row = db.query(TurnAnalysis).filter(TurnAnalysis.message_id == m.id).one_or_none()
    if row is None:
        row = TurnAnalysis(message_id=m.id, story_id=m.story_id, branch_id=m.branch_id)
        db.add(row)
    row.speakers_json, row.active_speaker_id = speakers, resolved[-1]["character_id"]
    row.beats_json, row.dialogue_json = beats, dialogue
    row.suggestions_json = row.suggestions_json or []
    row.discoveries_json = row.discoveries_json or []
    row.status, row.error, row.updated_at = "succeeded", None, now_iso()
    from .turn_analysis import SCHEMA_VERSION
    row.schema_version = SCHEMA_VERSION
    row.diagnostics_json = [{"source": "portrait_tags" if tagged else "live_speakers", "tags": len(resolved)}]
    m.speaker_character_id = resolved[-1]["character_id"]
    m.generation_metadata_json = {**md, "portrait_tags_applied": True}  # a new dict: JSON columns track reassignment only
    if branch.head_message_id == m.id and auto and tagged:  # a detected speaker keeps the expression already shown
        from .turns import apply_expressions
        apply_expressions(story, branch.id, [{"character_id": c, "slot": r["slot"], "evidence": r["anchor"]}
                                             for c, r in last.items()], source="tag", message_id=m.id)
    db.flush()
    return True


def from_beats(content: str, beats: list[dict[str, Any]], name_of) -> list[dict[str, Any]]:
    """v0.6: tag positions for a reply whose speakers the scene analysis found (the narrator wrote no tag). Put back
    into the history sent to the model (``retag``), they show it the format: small models copy what they see."""
    paras = _paragraphs(content)
    out = []
    for b in beats or []:
        k = b.get("paragraph")
        if b.get("beat") != "speaking" or not isinstance(k, int) or not 0 <= k < len(paras) or not b.get("character_id"):
            continue
        a, e = paras[k]
        pos = -1
        anchor = (b.get("anchor") or "").strip()
        if anchor:
            i = content.find(anchor, a, e)
            if i >= 0:
                j = i
                while j > a and content[j - 1] in " \u00a0":
                    j -= 1
                pos = j - 1 if j > a and content[j - 1] in "\"“«" else i
        if pos < 0:
            q = QUOTED.search(content, a, e)
            pos = q.start() if q else a
        out.append({"name": name_of(b["character_id"]), "character_id": b["character_id"],
                    "slot": int(b.get("expression") or 1), "pos": pos, "paragraph": k, "source": "analysis"})
    return out


def retag(m: Message, content: str, fallback: list[dict[str, Any]] | None = None, *, portraits: bool = True) -> str:
    """The reply as the narrator wrote it (tags put back), for the context sent to the model. Unchanged after an edit.
    v0.6: the tags also come from the speakers found by the app (``fallback``: older replies analysed before 0.6), so
    the model keeps seeing the format even when it did not write it. ``portraits=False`` (tags switched off): music only."""
    meta = m.generation_metadata_json or {}
    tags = (meta.get("portrait_tags") or fallback or []) if portraits else []
    music = meta.get("music_tags") or []
    if (not tags and not music) or m.edited_at or content != m.content:
        return content
    out = content
    for t in sorted(music, key=lambda t: t.get("offset") or 0, reverse=True):  # v0.5: the narrator's music tags too
        p = t.get("offset")
        if isinstance(p, int) and 0 <= p <= len(out) and not tags:
            out = f"{out[:p]}[Music:{t['tag']}]\n{out[p:]}"
    for t in sorted(tags, key=lambda t: t.get("pos") or 0, reverse=True):
        p = t.get("pos")
        if isinstance(p, int) and 0 <= p <= len(out):
            out = f"{out[:p]}[{t['name']}:{t['slot']}] {out[p:]}"
    if music and tags:  # both kinds of offsets refer to the streamed text: keep it simple, the first music tag on top
        out = f"[Music:{music[0]['tag']}]\n{out}"
    return out


def history_fallback(db: Session, messages: list[Message], name_of) -> dict[str, list[dict[str, Any]]]:
    """v0.6: tags for earlier replies that have none stored (analysed before 0.6, or the narrator wrote none and only
    the analysis found the speakers): message id -> tag positions from their scene analysis."""
    want = {m.id: m for m in messages if m.role == "assistant" and m.kind == "story" and not m.edited_at
            and not (m.generation_metadata_json or {}).get("portrait_tags")}
    if not want:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for row in db.query(TurnAnalysis).filter(TurnAnalysis.message_id.in_(list(want)), TurnAnalysis.status == "succeeded"):
        tags = from_beats(want[row.message_id].content, row.beats_json or [], name_of)
        if tags:
            out[row.message_id] = tags
    return out


def reminder(example: str, lang_code: str | None = None) -> str:
    """v0.6: the short note sent next to the player's message (small models follow it far better than a system rule)."""
    line = "« Bonjour. »" if lang_code == "fr" else '"Hello."'
    return (f"\n\n(Portraits: right before each line spoken by a named character, write their tag [Name:N], "
            f"e.g. [{example}:2] {line} N = 1 neutral … 6 shy.)")
