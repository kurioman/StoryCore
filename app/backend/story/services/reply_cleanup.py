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
LOOKBACK = 8  # earlier narrator replies compared (step 1, test report "50 tours": 3 let a fight loop come back)
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


LEAK = re.compile(r"\n\s*(?:Human:|User:|<\|im_(?:start|end)\|>|\[Story context for this turn|<context\b)")

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


# Step 1 (test report "50 tours", 19/11): what Rocinante 12B left in its replies that is not story.
# - code fences: 53 replies of 55 began with ``` (and every new reply copied the earlier ones from the history);
# - the app's own label before the player's message, "[The player's turn]" (copied at turns 33, 39 and 49), and
#   "[The scene continues in the next message. Please wait for my response...]" (turn 26);
# - a bracketed header line ("[Lumencia Academy Entrance]"): the app shows the place and time itself.
# A bracketed line with a colon is a tag ([Lilia:2], [Music:battle]) and is never touched here.
FENCE_LINE = re.compile(r"^[ \t]*```[\w+-]*[ \t]*$", re.M)
TECH_LINE = re.compile(
    r"^[ \t]*(?:\[[^\]\n:]{1,140}\]"
    r"|<(?:context|narrator-note)\b[^>\n]*>[^\n]*|</(?:context|narrator-note)>"
    r"|please\s+wait\s+for\s+(?:my|your|the\s+player'?s?)\s+(?:response|reply|turn|message)\b[^\n]*)[ \t]*$", re.I | re.M)


def _line_spans(reply: str, pattern: re.Pattern) -> list[tuple[int, int]]:
    out = []
    for m in pattern.finditer(reply):
        a = m.start()
        while a > 0 and reply[a - 1] in "\n \t":  # the line break before goes along
            a -= 1
        b = m.end()
        if a == 0:  # at the very start: the line break after goes instead, so the text starts with words
            while b < len(reply) and reply[b] in "\n \t":
                b += 1
        out.append((a, b))
    return out


def fence_spans(reply: str) -> list[tuple[int, int]]:
    """Lines that are only a code fence (``` or ```text)."""
    return _line_spans(reply, FENCE_LINE)


def technical_spans(reply: str) -> list[tuple[int, int]]:
    """Lines written for the app or the player, not story: "[The player's turn]", "Please wait for my response"..."""
    return _line_spans(reply, TECH_LINE)


def strip_for_history(text: str) -> str:
    """An earlier reply as sent again to the model: without fences and technical lines (they were copied from it)."""
    out, _ = _apply(text, fence_spans(text) + technical_spans(text) + instruction_spans(text))
    return out.lstrip("\n")


# Step 1: the reply that begins by telling the player's own action again ("You return to your seat next to Lilia
# and quietly ask her, ..." after "I return to my seat next to Lilia and quietly ask her, ..."), in the second or the
# third person. Its first sentences are compared with the player's message, word for word once pronouns, the
# protagonist's names and small words are set aside; they go while they only repeat it.
_SMALL = set("""a an the and or but then so to of in on at by for from with into onto toward towards over under up down
out off back as while just also very really still again now here there this that these those it its it's is are was were
be been being am do does did have has had will would can could shall should may might must not no yes oh well
i me my mine myself you your yours yourself he him his himself she her hers herself we us our ours ourselves they them
their theirs themselves""".split())
ECHO_WORDS = 0.75  # share of a sentence's words that come from the player's message
ECHO_COVER = 0.4  # share of the player's message that the removed opening must repeat
_SENTENCE = re.compile(r"[^.!?…\n]+(?:[.!?…]+[\"'”»’)]*)?")


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _words(text: str, names: set[str]) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-zà-ÿ0-9']+", text.lower().replace("’", "'"))
            if w not in _SMALL and w not in names and len(w) > 1}


def echo_spans(reply: str, player_turn: str, protagonist: set[str] | None = None,
               skip: list[tuple[int, int]] | None = None) -> list[tuple[int, int]]:
    """The opening sentences of ``reply`` that only tell ``player_turn`` again (one span, or none)."""
    names = {w.lower() for n in (protagonist or set()) for w in str(n).split() if w}
    q = _words(player_turn or "", names)
    if len(q) < 3:
        return []
    skip = _merge(skip or [])
    start = end = None
    took: set[str] = set()
    for m in _SENTENCE.finditer(reply):
        if not m.group().strip() or any(a <= m.start() < b for a, b in skip):
            continue
        if re.fullmatch(r"\s*\[[^\]\n]*:\s*\d\]\s*", m.group()):
            continue
        w = _words(m.group(), names)
        if not w or len(w & q) / len(w) < ECHO_WORDS:
            break
        start = m.start() if start is None else start
        end = m.end()
        took |= w & q
    if start is None or len(took) / len(q) < ECHO_COVER:
        return []
    while end < len(reply) and reply[end] in " \t\n":
        end += 1
    while start > 0 and reply[start - 1] in " \t\"“«":  # an opening quotation mark of a copied line goes along
        start -= 1
    return [(start, end)]


# Step 1: a short line said again word for word (a cultist's "You shall pay for this!" in four replies in a row).
# Only lines between quotation marks, from 15 to 60 characters, in a short paragraph made mostly of them.
SHORT_LINE_MIN, SHORT_LINE_MAX = 15, 60
_QUOTED = re.compile(r"[\"“«]([^\"“”«»\n]{1,200})[\"”»]")


def _norm_line(t: str) -> str:
    return re.sub(r"[^\w]+", " ", t.lower()).strip()


def repeated_line_spans(reply: str, earlier: list[str]) -> list[tuple[int, int]]:
    said = {_norm_line(q) for e in earlier[-LOOKBACK:] for q in _QUOTED.findall(e)}
    said = {q for q in said if SHORT_LINE_MIN <= len(q) <= SHORT_LINE_MAX}
    if not said:
        return []
    out = []
    for a, b in _paragraph_spans(reply):
        para = reply[a:b]
        if len(para.strip()) >= MIN_PARAGRAPH * 2:
            continue
        quotes = _QUOTED.findall(para)
        if not quotes or not all(_norm_line(q) in said for q in quotes):
            continue
        if sum(len(q) for q in quotes) >= len(para.strip()) * 0.5:
            out.append((a, b))
    return out


NO_STORY_CHARS = 40  # letters left once fences, notes and the echo are gone, below which the reply has no story


def story_left(reply: str, player_turn: str = "", protagonist: set[str] | None = None) -> str:
    """The reply without fences, technical lines, notes and the opening echo of the player's turn (tags removed)."""
    skip = fence_spans(reply) + technical_spans(reply) + instruction_spans(reply)
    text, _ = _apply(reply, skip + echo_spans(reply, player_turn, protagonist, skip))
    return re.sub(r"\[[^\]\n]*:[^\]\n]*\]", "", text)


def has_story(reply: str, player_turn: str = "", protagonist: set[str] | None = None) -> bool:
    return len(re.findall(r"[^\W\d_]", story_left(reply, player_turn, protagonist))) >= NO_STORY_CHARS


MOSTLY_REPEATED = 0.5  # B9: share of a reply removed as repetition above which the player is told (and offered a retry)


def clean(reply: str, earlier: list[str], *, cut_by_length: bool = False,
          names: set[str] | None = None, player_turn: str = "",
          protagonist: set[str] | None = None) -> tuple[str, list[tuple[int, int]], dict[str, Any]]:
    """(new text, removed spans of the original text, report). ``names``: the world's character names (B8);
    ``player_turn``: the player's message this reply answers and ``protagonist`` their names (step 1: the echo)."""
    from .context_builder import strip_trailing_menu

    leak = LEAK.search(reply)
    if leak and leak.start() > 0:  # the model went on writing the next turn itself (wrong chat template): cut there
        text, spans, report = clean(reply[:leak.start()], earlier, cut_by_length=False, names=names,
                                    player_turn=player_turn, protagonist=protagonist)
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
    fences = fence_spans(reply)
    if fences:
        removed += fences
        report["code_fences"] = len(fences)
    tech = [t for t in technical_spans(reply) if t not in notes]
    if tech:
        removed += tech
        report["technical_lines"] = len(tech)
    echo = echo_spans(reply, player_turn, protagonist, fences + tech + notes)
    if echo:
        removed += echo
        report["player_echo_chars"] = echo[0][1] - echo[0][0]
    lines = [(a, len(reply) - len(reply[b:].lstrip())) for a, b in repeated_line_spans(reply, earlier)
             if not any(x <= a < y for x, y in removed)]
    if lines:
        removed += lines
        report["repeated_lines"] = len(lines)
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
    text, removed = trim_start(reply, removed)
    if not text.strip():  # nothing would be left: the reply is kept as it is, but the player is still told (B9)
        return reply, [], {**({"mostly_repeated": True} if report.get("mostly_repeated") else {}),
                           **({"no_story": True} if not has_story(reply, player_turn, protagonist) else {})}
    return text, removed, report


def trim_start(reply: str, removed: list[tuple[int, int]]) -> tuple[str, list[tuple[int, int]]]:
    """The text without ``removed``, and without the line breaks left at its very start once the first lines are gone
    (the spans then include them)."""
    removed = _merge(removed)
    text, _ = _apply(reply, removed)
    for _i in range(8):
        if not text or not text[0].isspace() or not text.strip():
            break
        o = 0
        for a, b in removed:  # the first character of the original text that is kept
            if a <= o < b:
                o = b
        removed = _merge(removed + [(o, o + 1)])
        text, _ = _apply(reply, removed)
    return text, removed


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
