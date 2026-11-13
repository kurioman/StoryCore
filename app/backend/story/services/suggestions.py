"""Player-ready suggestions (v1.6): three short drafts the player could send, written in the player's own voice.

Before v1.6 the analysis was asked for "what the protagonist could do", which produced notes to an AI ("Ask Serena about
her family"): none of the 318 stored in the owner's stories contained a spoken line. Drafts are still part of the single
scene-analysis request, so they cost no extra call, and that request only holds the turn, the reply, the scene and a list
of names: hidden lore is not available to it. ``check`` then rejects what a draft must not be. A rejected draft is dropped,
never repaired; nothing is ever invented to fill a gap.

The app has no language or perspective setting, so ``voice`` reads them from the story: the reply's language, and from the
player's recent turns their grammatical person and whether they write *actions* between asterisks.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .entities import EntityIndex, norm

MAX_LEN = 320
MIN_LEN = 6
RECENT_TURNS = 6

WORDS = {
    "en": set("the and that with for you she her his was were have said from not this they what".split()),
    "fr": set("le la les des une est dans avec pour vous elle sur que qui pas mais son ses dit".split()),
}
LANGUAGE_NAMES = {"en": "English", "fr": "French"}
FIRST_PERSON = {
    "en": re.compile(r"\b(i|i'm|i'll|i've|i'd|me|my|mine|myself|we|our|us)\b", re.I),
    "fr": re.compile(r"\b(je|j'|j’|me|m'|m’|mon|ma|mes|moi|nous|notre|nos)(?=\b|\w)", re.I),
}
QUOTED = re.compile(r'"[^"]+"|“[^”]+”|«[^»]+»')
# notes to the narrator, in the shape the old prompt produced them
INSTRUCTION_START = re.compile(
    r"^(ask|tell|go|look|check|visit|find|talk|speak|follow|inquire|learn|request|seek|approach|observe|watch|study|head|"
    r"try|explore|investigate|confront|thank|mention|deflect|offer|introduce|stay|wait|leave|take|give|turn|change|keep|"
    r"demander|demande|interroger|aller|va|regarder|regarde|observer|observe|parler|parle|chercher|cherche|suivre|suis|"
    r"attendre|attends|quitter|quitte|proposer|propose|remercier|remercie)\b", re.I)
META = re.compile(r"\b(the player|the protagonist|the narrator|the story|the scene|you could|you should|you might|you can|"
                  r"option|turn the conversation|steer the conversation|le joueur|le protagoniste|le narrateur|l'histoire|"
                  r"tu pourrais|tu devrais|vous pourriez|vous devriez)\b", re.I)
GENERIC = re.compile(r"^\W*(what (do|should|shall) (we|i) do|what now|what next|que (fait-on|faire|faisons-nous)|on fait quoi)\W*$", re.I)


def detect_language(text: str) -> str:
    """"en", "fr", or "other" when neither clearly matches (validation then skips the language-specific checks)."""
    words = re.findall(r"[^\W\d_]+", (text or "").lower())
    hits = {k: sum(1 for w in words if w in v) for k, v in WORDS.items()}
    best = max(hits, key=lambda k: hits[k])
    return best if hits[best] >= 3 and hits[best] > 1.5 * min(hits.values()) else "other"


def voice(turns: list[str], reply: str, protagonist: str) -> dict[str, Any]:
    """How the player writes: {"language", "person", "asterisks", "name"}. Default first person; third person only when
    the player's own turns name the protagonist and never say "I"."""
    language = detect_language(reply)
    own = " ".join(turns)
    first = FIRST_PERSON.get(language, FIRST_PERSON["en"])
    first_name = (protagonist or "").split(" ")[0]
    third = bool(turns) and bool(first_name) and first_name.casefold() in own.casefold() and not first.search(QUOTED.sub(" ", own))
    return {"language": language, "person": "third" if third else "first", "name": protagonist,
            "asterisks": any("*" in t for t in turns) or not turns}


def rule(v: dict[str, Any]) -> str:
    """The suggestion lines of the analysis prompt, for this story's voice."""
    name = v["name"] or "the protagonist"
    lang = LANGUAGE_NAMES.get(v["language"])
    who = f"third person, naming {name}" if v["person"] == "third" else "first person (I)"
    quotes = "« … »" if v["language"] == "fr" else '" … "'
    act = "*a short action in asterisks*" if v["asterisks"] else "a short action in plain prose"
    return (f"- suggestions: exactly three short messages the PLAYER could send next, ready to send, in {who}, in "
            f"{lang or 'the language of the REPLY'}. Each is one or two sentences: {act} and/or a spoken line in {quotes}; "
            "neither is needed every time. Never a note to the narrator (not \"Ask Serena about her family\").\n"
            "  Three genuinely different approaches for this moment (e.g. curious, reserved, assertive: pick your own), not "
            f"one idea reworded. Use only what {name} has seen or been told in this turn or the current scene; no secrets, no "
            "guessing at hidden motives, and no new detail about a person, object or past event that the text does not "
            "state. Never decide how anyone reacts or that a plan works. Fit the mood: no sudden "
            "violence or flirting, no generic \"what do we do?\". \"approach\" names the tone in one or two words, in the "
            "same language.\n")


def _words(s: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]{3,}", norm(s)))


def similar(a: str, b: str) -> bool:
    """True for a copy or a light rewording of the same draft."""
    x, y = _words(a), _words(b)
    return not (x and y) or len(x & y) / len(x | y) >= 0.75


def balanced(s: str) -> bool:
    return s.count('"') % 2 == 0 and s.count("“") == s.count("”") and s.count("«") == s.count("»")


def checker(v: dict[str, Any], index: EntityIndex, allowed: set[str]) -> Callable[[str], str | None]:
    """A check returning why a draft cannot be offered, or None. ``allowed`` is who this turn's analysis may name: anyone
    else from the lore would tell the player about someone they have no way of knowing."""
    first = FIRST_PERSON.get(v["language"])
    name = (v["name"] or "").split(" ")[0].casefold()

    def check(text: str) -> str | None:
        if not MIN_LEN <= len(text) <= MAX_LEN:
            return "length"
        if not balanced(text):
            return "unbalanced quotes"
        spoken = QUOTED.findall(text)
        narration = QUOTED.sub(" ", text).strip(" *_.,")
        if GENERIC.match(narration or " ".join(spoken)):
            return "generic"
        if META.search(narration):
            return "note to the narrator"
        if narration and INSTRUCTION_START.match(narration.lstrip("*_ ")):
            return "instruction"
        if not spoken and first is not None:
            voiced = name in narration.casefold() if v["person"] == "third" and name else bool(first.search(narration))
            if not voiced:
                return "not in the player's voice"
        if any(c not in allowed for c in index.find_mentions(text, ("character",))):
            return "names someone the player does not know"
        return None

    return check


def select(raw: list[Any], check: Callable[[str], str | None] | None, *, cap: int = 3) -> tuple[list[dict[str, Any]], list[str]]:
    """Up to ``cap`` valid, distinct drafts from the model's list, plus why the others were dropped."""
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    for s in raw:
        obj = s if isinstance(s, dict) else {}
        text = re.sub(r"[ \t]+", " ", str(obj.get("text") or obj.get("label") or (s if isinstance(s, str) else ""))).strip()
        if not text:
            continue
        reason = check(text) if check else None
        if reason is None and any((similar(text, k["label"]) if check else text.casefold() == k["label"].casefold()) for k in kept):
            reason = "duplicate"
        if reason:
            dropped.append(reason)
            continue
        kept.append({"id": f"s{len(kept) + 1}", "label": text, "description": "", "raw_kind": obj.get("kind"),
                     "approach": re.sub(r"\s+", " ", str(obj.get("approach") or "")).strip()[:24],
                     **({"format": "draft"} if check else {})})
        if len(kept) == cap:
            break
    return kept, dropped
