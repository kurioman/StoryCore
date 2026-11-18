"""Clean a finished narrator reply before it is kept (v0.6, phase 9).

Small local models sometimes loop: a reply tells again a scene of the previous replies, copying whole paragraphs, or
says the same paragraph twice. Seen live: rocinante-12b answered "Continue" with three paragraphs copied from the reply
before. Every paragraph that repeats one of the last replies (or an earlier paragraph of the same reply) is removed; a
reply cut by the token ceiling is trimmed to its last full sentence; a trailing "What do you do?" menu is dropped.

Positions stored with the reply (portrait tags, music tags) are moved with the text. Nothing is removed when it would
leave the reply empty. No model call.
"""
from __future__ import annotations

import re
from typing import Any

MIN_PARAGRAPH = 60  # shorter lines (a single spoken line) may legitimately echo earlier ones
SIMILAR = 0.6  # share of a paragraph's 4-word sequences already seen
LOOKBACK = 3  # earlier narrator replies compared
SENTENCE_END = re.compile(r"[.!?…][\"»”*)\]]*\s|[\"»”*]\s*$")


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i:i + 4]) for i in range(max(0, len(words) - 3))}


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in re.finditer(r"\n\s*\n", text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def repeated_spans(reply: str, earlier: list[str]) -> list[tuple[int, int]]:
    """Paragraphs of ``reply`` that repeat ``earlier`` replies or an earlier paragraph of ``reply`` itself."""
    seen: set[tuple[str, ...]] = set()
    for e in earlier[-LOOKBACK:]:
        seen |= _shingles(e)
    out = []
    for a, b in _paragraph_spans(reply):
        para = reply[a:b]
        sh = _shingles(para)
        if len(para.strip()) >= MIN_PARAGRAPH and sh and len(sh & seen) / len(sh) >= SIMILAR:
            out.append((a, b))
        else:
            seen |= sh
    return out


def _last_sentence_end(text: str) -> int | None:
    ends = [m.end() for m in SENTENCE_END.finditer(text)]
    return ends[-1] if ends else None


def clean(reply: str, earlier: list[str], *, cut_by_length: bool = False) -> tuple[str, list[tuple[int, int]], dict[str, Any]]:
    """(new text, removed spans of the original text, report)."""
    from .context_builder import strip_trailing_menu

    # a removed paragraph takes the blank line after it along (positions stay exact: nothing else is reflowed)
    removed = [(a, len(reply) - len(reply[b:].lstrip())) for a, b in repeated_spans(reply, earlier)]
    report: dict[str, Any] = {}
    if removed:
        report["repeated_paragraphs"] = len(removed)
    kept_until = len(reply)
    if cut_by_length:
        end = _last_sentence_end(reply)
        if end and end < len(reply) and end > len(reply) // 3:
            removed.append((end, len(reply)))
            kept_until = end
            report["trimmed_unfinished_sentence"] = True
    # what would be left once the spans are removed: a trailing options menu goes too
    text, _ = _apply(reply, removed)
    without_menu, had_menu = strip_trailing_menu(text)
    if had_menu and without_menu.strip():
        cut = len(without_menu.rstrip())
        # map the cut back to the original text: the menu is at the end of what was kept
        removed.append((_original_offset(reply, removed, cut), kept_until))
        report["trailing_menu"] = True
    removed = _merge(removed)
    text, _ = _apply(reply, removed)
    if not text.strip():
        return reply, [], {}
    return text, removed, report


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(s for s in spans if s[1] > s[0]):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _apply(text: str, spans: list[tuple[int, int]]) -> tuple[str, list[tuple[int, int]]]:
    parts, pos = [], 0
    for a, b in _merge(spans):
        parts.append(text[pos:a])
        pos = b
    parts.append(text[pos:])
    return "".join(parts).rstrip(), spans


def _original_offset(text: str, spans: list[tuple[int, int]], new_offset: int) -> int:
    """The offset in ``text`` of position ``new_offset`` of the text with ``spans`` removed (blank-line folding aside)."""
    pos, done = 0, 0
    for a, b in _merge(spans):
        if done + (a - pos) >= new_offset:
            return pos + (new_offset - done)
        done += a - pos
        pos = b
    return pos + (new_offset - done)


def move_offset(offset: int, spans: list[tuple[int, int]]) -> int | None:
    """Where a stored position of the original text lands in the cleaned text; None when its text was removed."""
    shift = 0
    for a, b in _merge(spans):
        if offset >= b:
            shift += b - a
        elif offset >= a:
            return None
    return offset - shift
