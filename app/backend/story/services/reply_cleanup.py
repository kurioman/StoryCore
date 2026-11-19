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


LEAK = re.compile(r"\n\s*(?:Human:|User:|<\|im_(?:start|end)\|>|\[Story context for this turn)")

# v0.6 (test report "30 tours", B8): small models sometimes wrap a whole paragraph of narration in quotation marks
# ("The hero's toast raises smiles all around the table..."). The screen then showed it as a line spoken by the last
# character. Such a paragraph loses its two quotation marks when it reads as narration: no first person, long enough,
# and told about "you" / the hero / a named character in the third person. Real lines keep their quotes.
OPEN_Q, CLOSE_Q = "\"“«", "\"”»"
FIRST_PERSON = re.compile(r"\b(?:i|i'm|i’m|i've|i’ve|i'll|i’ll|i'd|i’d|me|my|mine|myself|we|we're|we’re|we've|we’ve|"
                          r"we'll|we’ll|us|our|ours|ourselves|je|j|moi|mon|ma|mes|nous|notre|nos|m)\b", re.I)
YOU_ACT = re.compile(r"(?:^|[.!?;,]\s+|\b(?:and|then|et|puis)\s+)(?:you|vous|tu)\s+(?!(?:must|should|will|would|can|could|"
                     r"may|might|need|have|are|were|do|did|don|know|see|devez|pouvez|allez|êtes|avez|savez|voyez)\b|"
                     r"[’'])[a-zà-ÿ]+", re.I)
THE_HERO = re.compile(r"\b(?:the\s+hero|le\s+h[ée]ros|la\s+h[ée]ro[ïi]ne)\b", re.I)
THIRD = re.compile(r"\b(?:he|she|they|his|her|their|him|them|il|elle|ils|elles|lui|leur|leurs|sa|son|ses)\b", re.I)
YOU = re.compile(r"\b(?:you|your|vous|votre|vos)\b", re.I)
NARRATIVE_START = re.compile(r"^(?:as|when|while|then|after|before|with|lorsque|quand|tandis|alors|puis|après|avant|"
                             r"pendant|le\s+lendemain|the\s+next)\b", re.I)
NARRATION_MIN = 80


def reads_as_narration(inner: str, names: set[str] | None = None) -> bool:
    """A quoted paragraph (without its quotation marks) that is really narration (see B8 above)."""
    t = inner.strip()
    if len(t) < NARRATION_MIN or FIRST_PERSON.search(t) or re.search(r'["“”«»]', t):
        return False
    if YOU_ACT.search(t) or THE_HERO.search(t):
        return True
    named = bool(names) and any(re.search(rf"\b{re.escape(n)}\b", t, re.I) for n in names)
    return named and bool(THIRD.search(t)) and (bool(YOU.search(t)) or bool(NARRATIVE_START.match(t)))


def quoted_narration_spans(reply: str, names: set[str] | None = None) -> list[tuple[int, int]]:
    """The opening and closing quotation marks of every paragraph of narration wrapped in quotes (1-character spans)."""
    out: list[tuple[int, int]] = []
    for a, b in _paragraph_spans(reply):
        para = reply[a:b]
        lead = len(para) - len(para.lstrip())
        body = para.strip()
        if len(body) < 3 or body[0] not in OPEN_Q or body[-1] not in CLOSE_Q:
            continue
        if reads_as_narration(body[1:-1], names):
            start = a + lead
            out += [(start, start + 1), (start + len(body) - 1, start + len(body))]
    return out


# Test 2: the model copied the app's own notes into its reply: "(OOC: Please continue with Kurio's actions and
# dialogue.)" and the portrait-tag reminder sent next to the player's message. Such a line is removed.
INSTRUCTION_LINE = re.compile(r"^[ \t]*[\[(]\s*(?:OOC\b|Portraits?\s*:|Note\s+to\s+(?:the\s+)?(?:player|user)\b|"
                              r"Story\s+context\b|Remember\s*:)[^\n]*[\])][ \t]*$", re.I | re.M)


def instruction_spans(reply: str) -> list[tuple[int, int]]:
    """Lines that are notes to the model or the player, not story (with the line break before them)."""
    out = []
    for m in INSTRUCTION_LINE.finditer(reply):
        a = m.start()
        while a > 0 and reply[a - 1] in "\n \t":
            a -= 1
        out.append((a, m.end()))
    return out


MOSTLY_REPEATED = 0.5  # B9: share of a reply removed as repetition above which the player is told (and offered a retry)


def clean(reply: str, earlier: list[str], *, cut_by_length: bool = False,
          names: set[str] | None = None) -> tuple[str, list[tuple[int, int]], dict[str, Any]]:
    """(new text, removed spans of the original text, report). ``names``: the world's character names (B8)."""
    from .context_builder import strip_trailing_menu

    leak = LEAK.search(reply)
    if leak and leak.start() > 0:  # the model went on writing the next turn itself (wrong chat template): cut there
        text, spans, report = clean(reply[:leak.start()], earlier, cut_by_length=False, names=names)
        return text, spans + [(leak.start(), len(reply))], {**report, "leaked_turn_cut": True}
    # a removed paragraph takes the blank line after it along (positions stay exact: nothing else is reflowed)
    removed = [(a, len(reply) - len(reply[b:].lstrip())) for a, b in repeated_spans(reply, earlier)]
    report: dict[str, Any] = {}
    if removed:
        report["repeated_paragraphs"] = len(removed)
        repeated_chars = sum(b - a for a, b in _merge(removed))
        if repeated_chars > len(reply.strip()) * MOSTLY_REPEATED:
            report["mostly_repeated"] = True  # B9: shown under the reply with a "Regenerate" button
    notes = instruction_spans(reply)
    if notes:
        removed += notes
        report["instruction_lines"] = len(notes)
    unquoted = [s for s in quoted_narration_spans(reply, names)
                if not any(a <= s[0] < b for a, b in removed)]
    if unquoted:
        removed += unquoted
        report["unquoted_narration"] = len(unquoted) // 2
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
    if not text.strip():  # nothing would be left: the reply is kept as it is, but the player is still told (B9)
        return reply, [], {"mostly_repeated": True} if report.get("mostly_repeated") else {}
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
