"""Rule-based speaker detection and expression suggestions (cheap, offline, marked as suggestions)."""
from __future__ import annotations

import re
from typing import Any

from .entities import EntityIndex, norm

SPEECH_VERBS = r"(?:said|says|asked|asks|replied|replies|answered|whispered|murmured|muttered|shouted|called|snapped|added|continued|retorted|declared|hissed|laughed|sighed|stammered)"

KEYWORDS: dict[int, list[str]] = {
    2: ["smile", "smiled", "smiling", "grin", "grinned", "laugh", "laughed", "beam", "beamed", "cheerful", "delight",
        "pleased", "chuckle", "chuckled", "giggle", "giggled", "happily", "joy", "satisfied", "brighten"],
    3: ["tear", "tears", "sad", "sadly", "sorrow", "sighed", "mourn", "grief", "melanchol", "wistful", "comfort",
        "sympath", "cried", "sob", "sobbed", "regret", "gently", "tender"],
    4: ["anger", "angry", "angrily", "fury", "furious", "rage", "glare", "glared", "snarl", "snarled", "scowl", "scowled",
        "seethed", "shouted", "roared", "outrage", "unsheath", "drew her sword", "drew his sword", "blade raised", "attack",
        "aggressive", "lunged"],
    5: ["disgust", "disgusted", "disdain", "disdainful", "sneer", "sneered", "scoff", "scoffed", "contempt",
        "contemptuous", "scorn", "scornful", "looked down on", "wrinkled her nose", "wrinkled his nose", "disappointed",
        "offended", "coldly"],
    6: ["love", "adoring", "adoringly", "blush", "blushed", "blushing", "flush", "flushed", "stammer", "stammered", "fluster", "flustered", "shy", "shyly",
        "averted her gaze", "averted his gaze", "looked away", "bashful", "embarrass", "cheeks reddened", "cheeks pink"],
}


# v0.6: French mood words, as they look after entities.norm (no accents). Whole-word starts only ("rit" must not match
# "esprit"), so they are matched with a regex rather than by substring like the English list.
FR_KEYWORDS: dict[int, str] = {
    2: r"sourit|souriant|sourire|souriante|rit|riant|rieuse|eclate de rire|joyeu|heureu|ravie?s?|enthousias|gaiement|"
       r"s illumine|petille|amuse",
    3: r"larmes?|triste|tristement|tristesse|sanglot|pleur|chagrin|melancol|abattue?|soupire|la gorge serree|"
       r"voix tremblante|baisse les yeux|desole",
    4: r"colere|furieu|rage|enrage|hurle|fusille du regard|foudroie|grogne|menace|poings? serres?|serre les dents|"
       r"agressi|degaine|s emporte|irrite",
    5: r"mepris|meprisant|dedain|dedaigneu|degout|ricane|toise|renifle|hautain|froidement|leve les yeux au ciel|"
       r"condescend|moqueu",
    6: r"rougi|rougit|rougissante?|rouge aux joues|joues roses|timide|timidement|gene|genee|intimide|"
       r"detourne le regard|balbutie|bafouille|amoureu|tendrement|le coeur battant",
}
_FR_PATTERNS = {slot: re.compile(rf"\b(?:{words})\b") for slot, words in FR_KEYWORDS.items()}


def mood_of(text: str) -> tuple[int, str] | None:
    """(expression 2-6, word found) for a short narration text (French or English), or None when nothing clear.
    A tie between two moods is no mood."""
    s = norm(text)
    scores: dict[int, list[str]] = {}
    for slot, kws in KEYWORDS.items():
        scores[slot] = [k for k in kws if k in s]
    for slot, pat in _FR_PATTERNS.items():
        scores[slot] = scores.get(slot, []) + pat.findall(s)
    ranked = sorted(((len(v), slot, v) for slot, v in scores.items() if v), reverse=True)
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None
    return ranked[0][1], ranked[0][2][0]


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])\s+|\n+", text) if s.strip()]


def detect_speaker(text: str, index: EntityIndex) -> str | None:
    """Return a character id only when dialogue is attributed to exactly one known character."""
    t = norm(text)
    pat = index._pattern()
    if not pat or '"' not in text and "“" not in text and ":" not in text:
        return None
    t = t.replace("“", '"').replace("”", '"')
    speakers: dict[str, int] = {}
    for m in pat.finditer(t):
        eid = next(iter(index.alias_map[m.group(1)]))
        if index.entities[eid].category != "character":
            continue
        before, after = t[max(0, m.start() - 40):m.start()], t[m.end():m.end() + 40]
        if (re.search(r'"\s*[,.!?]?\s*$', before) and re.match(rf"\s+{SPEECH_VERBS}", after)) or \
           re.match(rf'\s+{SPEECH_VERBS}[^"]{{0,20}}[,:]?\s*"', after) or \
           (re.match(r"\s*:\s*\"?", after) and (m.start() == 0 or t[m.start() - 1] == "\n")) or \
           re.search(rf'"\s*{SPEECH_VERBS}\s*$', before):
            speakers[eid] = speakers.get(eid, 0) + 1
    return next(iter(speakers)) if len(speakers) == 1 else None


def suggest_moods(text: str, index: EntityIndex, restrict_to: list[str] | None = None) -> list[dict[str, Any]]:
    """Keyword-based mood suggestions for characters named in the text. Low confidence by design."""
    out: dict[str, dict[str, Any]] = {}
    for sent in _sentences(text):
        ids = index.find_mentions(sent, ("character",))
        if len(ids) != 1:  # ambiguous sentence: don't guess whose mood it is
            continue
        cid = ids[0]
        if restrict_to is not None and cid not in restrict_to:
            continue
        s = norm(sent)
        best, best_hits, ev = None, 0, ""
        for slot, kws in KEYWORDS.items():
            hits = [k for k in kws if k in s]
            if len(hits) > best_hits:
                best, best_hits, ev = slot, len(hits), hits[0]
        if best:
            cur = out.get(cid)
            if not cur or best_hits >= cur["_hits"]:
                out[cid] = {"character_id": cid, "slot": best, "evidence": ev, "confidence": min(0.3 + 0.1 * best_hits, 0.6),
                            "_hits": best_hits}
    return [{k: v for k, v in d.items() if k != "_hits"} for d in out.values()]
