"""In-story time, place and weather with a story-day counter (v1.4).

Stored in the versioned per-branch scene (no migration): ``location``, ``time``, ``weather`` (existing strings) plus
``weekday``, ``day``, ``month``, ``year`` and ``story_day`` (D1 = the first in-story day), ``established`` (which reply
established each field, with its quote) and ``world_history`` (automatic updates, for reverting).

Updates come from the existing post-turn scene analysis: one small object listing only what the reply (or the player's
turn) establishes, each change with an exact quote that must be found in that text. Values are validated (weekday and
month names, day within the month, bounded lengths and day jumps); anything else is dropped and the last valid state is
kept. A weekday/date rolls forward deterministically when days pass. Applied only for the branch head and tied to that
reply: when it leaves the story (deleted, regenerated, edited, alternative switched) its update is reverted, unless a
later change or a manual edit already replaced the value. Story-world time is never the real clock.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import MessageBranch, Story, now_iso
from . import state_service, story_tree
from .entities import EntityIndex

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December"]
MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # Feb 29 allowed (leap year status is unknown)
FIELDS = ("location", "time", "weather", "weekday", "day", "month", "year")
MAX_LEN = {"location": 80, "time": 40, "weather": 60}
HOUR_WORDS = {w: i + 1 for i, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve".split())}
HOUR_WORDS.update({w: i + 1 for i, w in enumerate("une deux trois quatre cinq six sept huit neuf dix onze douze".split())})
HOUR = r"(\d{1,2}|" + "|".join(sorted(HOUR_WORDS, key=len, reverse=True)) + ")"
MERIDIEM = r"\s*(a\.?m\.?|p\.?m\.?)?"
LATE_PERIOD = re.compile(r"\b(afternoon|evening|night|dusk|sunset|après-midi|soir|soirée|nuit)\b", re.I)
EARLY_PERIOD = re.compile(r"\b(morning|dawn|sunrise|matin|matinée|aube)\b", re.I)
MAX_DAYS_PASSED = 30
PLACEHOLDERS = {"", "unknown", "none", "null", "n/a", "unspecified", "not established", "not specified", "same", "unchanged"}
NOT_ESTABLISHED = "not established"


def _pick(v: Any, names: list[str]) -> str | None:
    s = str(v or "").strip().casefold().rstrip(".")
    return next((n for n in names if n.casefold() == s or (len(s) >= 3 and n.casefold().startswith(s))), None)


def _int(v: Any) -> int | None:
    m = re.search(r"-?\d+", str(v if v is not None else ""))
    return int(m.group(0)) if m else None


def clean_value(field: str, v: Any) -> Any:
    """A valid value for ``field`` or None (never a guess)."""
    if field == "weekday":
        return _pick(v, WEEKDAYS)
    if field == "month":
        return _pick(v, MONTHS)
    if field == "day":
        n = _int(v)
        return n if n is not None and 1 <= n <= 31 else None
    if field == "year":
        n = _int(v)
        return n if n is not None and 1 <= n <= 99999 else None
    s = re.sub(r"\s+", " ", str(v or "")).strip().strip("\"'“”")
    if field == "time":
        s = state_service.strip_day_token(s)
        if not (clock_of(s) or TIME_WORD.search(s)):
            return None  # test 2: "past" was stored as the time of day
    if s.casefold() in PLACEHOLDERS or len(s) > MAX_LEN[field]:
        return None
    return s


def starter_scene(raw: Any) -> dict[str, Any]:
    """The starting scene an opening defines (pack.json ``starters[].scene``), validated like any scene value: location,
    time, weather, weekday, day, month (name or number), year and ``present`` (character ids). Invalid parts are left out.
    A dated opening starts on story day 1."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for f in FIELDS:
        v = raw.get(f)
        if f == "month" and _int(v) is not None and str(v).strip().isdigit():
            n = _int(v)
            v = MONTHS[n - 1] if 1 <= n <= 12 else None
        val = clean_value(f, v) if v not in (None, "") else None
        if val is not None:
            out[f] = val
    if isinstance(raw.get("present"), list):
        out["present"] = [str(c) for c in raw["present"] if isinstance(c, str) and c.strip()]
    if any(k in out for k in ("day", "month", "year", "weekday")):
        out["story_day"] = 1
    return out


def _hour(s: str) -> int:
    return int(s) if s.isdigit() else HOUR_WORDS[s.lower()]


def clock_of(text: Any) -> tuple[int, int, bool] | None:
    """An hour stated in ``text``: (hour, minute, certain). Not certain means a 12-hour reading that morning or evening
    still has to settle ("eight thirty"). Bells, "first hour" and the like are not clock times."""
    t = str(text or "")
    if re.search(r"\b(midnight|minuit)\b", t, re.I):
        return 0, 0, True
    if re.search(r"\b(noon|midday|midi)\b", t, re.I):
        return 12, 0, True

    def out(h: int, m: int, mer: str | None, sure: bool = False) -> tuple[int, int, bool] | None:
        if mer:
            pm = mer.lower().startswith("p")
            h = (h % 12) + (12 if pm else 0)
            sure = True
        return (h, m, sure or h > 12 or h == 0) if 0 <= h <= 24 and 0 <= m < 60 else None

    for pat, fn in (
        (rf"\b(\d{{1,2}})[:hH](\d{{2}})\b{MERIDIEM}", lambda g: out(int(g[0]), int(g[1]), g[2], sure=len(g[0]) == 2 and g[0].startswith("0"))),
        (rf"\b{HOUR}\s+heures?\s+et\s+demie\b", lambda g: out(_hour(g[0]), 30, None, True)),
        (rf"\b{HOUR}\s+heures?\s+et\s+quart\b", lambda g: out(_hour(g[0]), 15, None, True)),
        (rf"\b{HOUR}\s+heures?\s+moins\s+le\s+quart\b", lambda g: out(_hour(g[0]) - 1, 45, None, True)),
        (rf"\b{HOUR}\s+heures?(?:\s+(\d{{1,2}}))?\b", lambda g: out(_hour(g[0]), int(g[1] or 0), None, True)),
        (rf"\bhalf\s+past\s+{HOUR}\b{MERIDIEM}", lambda g: out(_hour(g[0]), 30, g[1])),
        (rf"\bquarter\s+past\s+{HOUR}\b{MERIDIEM}", lambda g: out(_hour(g[0]), 15, g[1])),
        (rf"\bquarter\s+to\s+{HOUR}\b{MERIDIEM}", lambda g: out(_hour(g[0]) - 1, 45, g[1])),
        (rf"\b{HOUR}\s+(thirty|fifteen|forty-five)\b{MERIDIEM}", lambda g: out(_hour(g[0]), {"thirty": 30, "fifteen": 15, "forty-five": 45}[g[1].lower()], g[2])),
        (rf"\b{HOUR}\s+o['’]clock\b{MERIDIEM}", lambda g: out(_hour(g[0]), 0, g[1])),
        (r"\b(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)(?!\w)", lambda g: out(int(g[0]), 0, g[1])),
    ):
        m = re.search(pat, t, re.I)
        if m:
            return fn(m.groups())
    return None


def resolve_time(value: str, evidence: str, current: Any) -> tuple[str | None, str | None]:
    """(time to store, reason it was refused). An hour needs its quote: a stated hour becomes HH:MM, an hour found only in
    the value is refused (never an invented clock). A 12-hour reading is settled by the value's or the scene's time of day;
    otherwise it stays as written. A broad time of day stays broad."""
    said, wanted = clock_of(evidence), clock_of(value)
    if wanted and (not said or (said[0] % 12, said[1]) != (wanted[0] % 12, wanted[1])):
        return None, "clock time not stated in the text"
    if not said:
        return value, None
    h, m, sure = wanted if wanted and (wanted[2] or not said[2]) else said
    if not sure:
        hint = f"{value} {current or ''}"
        if LATE_PERIOD.search(hint):
            h = h % 12 + 12
        elif EARLY_PERIOD.search(hint):
            h = h % 12
        else:
            return value, None
    return f"{h % 24:02d}:{m:02d}", None


def advance(scene: dict[str, Any], days: int, year_start: str = "January") -> dict[str, Any]:
    """Weekday and calendar date ``days`` later (only the parts that are established). The weekday only rolls an
    established weekday through the 7-day week — it is never derived from the date (no Gregorian rule is assumed for an
    in-world calendar). The year number changes on the world's new-year month (v1.5.1: March for the world's imperial
    year, per the lore pack's calendar; January when a world has no calendar)."""
    out: dict[str, Any] = {}
    if days <= 0:
        return out
    if scene.get("weekday") in WEEKDAYS:
        out["weekday"] = WEEKDAYS[(WEEKDAYS.index(scene["weekday"]) + days) % 7]
    if scene.get("month") in MONTHS and isinstance(scene.get("day"), int):
        mi, d, y = MONTHS.index(scene["month"]), scene["day"], scene.get("year")
        new_year = MONTHS.index(year_start) if year_start in MONTHS else 0
        for _ in range(days):
            d += 1
            if d > MONTH_DAYS[mi] - (1 if mi == 1 else 0):  # roll February after the 28th (a 29th must be stated)
                d, mi = 1, (mi + 1) % 12
                if mi == new_year and isinstance(y, int):
                    y += 1
        out.update(day=d, month=MONTHS[mi])
        if isinstance(y, int) and y != scene.get("year"):
            out["year"] = y
    return out


def validate(raw: Any, reply: str, player_turn: str, scene: dict[str, Any], year_start: str = "January") -> dict[str, Any]:
    """Grounded changes from the model's ``world_state`` object: {"changes": {field: value}, "days_passed": n,
    "evidence": {field: quote}, "dropped": [...]}. Empty when nothing valid is established."""
    from .turn_analysis import locate  # quotes are verified exactly like analysis anchors

    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {"changes": {}, "days_passed": 0, "evidence": {}, "dropped": []}

    def grounded(quote: Any, loose: bool = False) -> str | None:
        hit = locate(reply, quote, 4) or locate(player_turn, quote, 4)
        if hit:
            return hit[0]
        # v0.6 (test report "30 tours", B3): small models reword their quote ("the sun sets" for "the sun begins to
        # set"); for the clock, the weather and passing days a sentence holding most of the quote's words is enough
        return (loose_quote(reply, quote) or loose_quote(player_turn, quote)) if loose else None

    for c in (raw.get("changes") or [])[:len(FIELDS) + 2]:
        if not isinstance(c, dict) or c.get("field") not in FIELDS:
            continue
        f = c["field"]
        val = clean_value(f, c.get("value"))
        # test 2: a reworded quote also counts for the place (it was refused 4 times in 30 turns); a place quoted
        # only inside dialogue is still refused just below
        ev = grounded(c.get("evidence"), loose=f in ("time", "weather", "location"))
        if val is None or ev is None:
            out["dropped"].append({"field": f, "value": str(c.get("value"))[:80],
                                   "reason": "invalid value" if val is None else "evidence not found in the text"})
            continue
        if f == "location" and in_dialogue(reply, ev) and not locate(player_turn, ev, 4):
            # B5: a place someone talks about ("there is an outpost not far from here") is not where the scene is
            out["dropped"].append({"field": f, "value": str(c.get("value"))[:80], "reason": "only mentioned in dialogue"})
            continue
        if f == "time":
            val, refused = resolve_time(val, ev, scene.get("time"))
            if refused:
                out["dropped"].append({"field": f, "value": str(c.get("value"))[:80], "reason": refused})
                continue
        if val != scene.get(f) and f not in out["changes"]:
            out["changes"][f] = val
            out["evidence"][f] = ev
    try:
        days = int(raw.get("days_passed") or 0)
    except (TypeError, ValueError):
        days = 0
    if days and (days < 0 or days > MAX_DAYS_PASSED or grounded(raw.get("days_evidence"), loose=True) is None):
        out["dropped"].append({"field": "days_passed", "value": str(days), "reason": "out of range or no evidence"})
        days = 0
    new_wd, old_wd = out["changes"].get("weekday"), scene.get("weekday")
    if not days and new_wd and old_wd in WEEKDAYS:
        days = (WEEKDAYS.index(new_wd) - WEEKDAYS.index(old_wd)) % 7  # a stated new weekday means days have passed
    if days:
        out["days_passed"] = days
        out["evidence"].setdefault("days_passed", grounded(raw.get("days_evidence"), loose=True) or out["evidence"].get("weekday"))
        for k, v in advance(scene, days, year_start).items():  # derived, unless the reply states the value itself
            out["changes"].setdefault(k, v)
        if scene.get("time") and "time" not in out["changes"]:
            out["changes"]["time"] = ""  # yesterday's "evening" is not today's: unknown until the story says
    if out["changes"].get("day") is not None:  # a stated day must exist in the (stated or current) month
        month = out["changes"].get("month") or scene.get("month")
        if month in MONTHS and out["changes"]["day"] > MONTH_DAYS[MONTHS.index(month)]:
            out["dropped"].append({"field": "day", "value": str(out["changes"].pop("day")), "reason": "not a day of that month"})
    return out


SPEECH_SPANS = re.compile(r'"[^"\n]*"|“[^”\n]*”|«[^»\n]*»')


def in_dialogue(text: str, quote: str) -> bool:
    """True when ``quote`` is found in ``text`` only inside quoted speech."""
    if not quote:
        return False
    spans = [(m.start(), m.end()) for m in SPEECH_SPANS.finditer(text or "")]
    pos, found = (text or "").find(quote), False
    while pos >= 0:
        found = True
        if not any(a <= pos < b for a, b in spans):
            return False
        pos = text.find(quote, pos + 1)
    return found


def _words_of(s: Any) -> list[str]:
    from .entities import norm
    return [w for w in re.findall(r"[^\W_]+", norm(str(s or ""))) if len(w) >= 3]


def loose_quote(text: str, quote: Any, share: float = 0.75) -> str | None:
    """The sentence of ``text`` holding most of the words of a reworded quote (at least three words), else None."""
    want = set(_words_of(quote))
    if len(want) < 3 or not text:
        return None
    best, score = None, 0.0
    for sent in re.split(r"(?<=[.!?…])\s+|\n+", text):
        have = set(_words_of(sent))
        k = len(want & have) / len(want)
        if k > score:
            best, score = sent.strip(), k
    return best[:160] if best and score >= share else None


# B3: the clock never moved in a 30-turn game (sunset, a night, "the next morning"): the scene analysis is often
# skipped or stopped by the next reply, and its quotes were reworded. These plain cues, read in the narration only
# (never in what characters say: "be ready by dawn"), move the time of day forward and count a new day. No model call.
TIME_WORD = re.compile(r"\b(?:\d{1,2}[:h]\d{2}|dawn|daybreak|sunrise|morning|forenoon|noon|midday|afternoon|evening|dusk|"
                       r"sunset|twilight|night|midnight|bell|bells|hour|o'clock|first\s+light|aube|matin|matin[ée]e|midi|"
                       r"apr[èe]s-midi|soir|soir[ée]e|cr[ée]puscule|nuit|minuit|heure|heures)\b", re.I)
PERIODS = ("dawn", "morning", "noon", "afternoon", "evening", "night")
PERIOD_CUES = [
    ("dawn", re.compile(r"\b(?:dawn|daybreak|sunrise|first\s+light|[àa]\s+l['’]aube|l['’]aube\s+"
                        r"(?:se\s+l[èe]ve|pointe)|lever\s+du\s+soleil|point\s+du\s+jour)\b", re.I)),
    ("morning", re.compile(r"\b(?:morning\s+(?:sun|light|air|mist|chill)|early\s+morning|wake\s+(?:up\s+)?(?:the\s+next|in\s+the)\s+"
                           r"morning|ce\s+matin|au\s+matin|le\s+matin|la\s+matin[ée]e)\b", re.I)),
    ("noon", re.compile(r"\b(?:at\s+noon|midday\s+sun|[àa]\s+midi)\b", re.I)),
    ("afternoon", re.compile(r"\b(?:afternoon\s+sun|late\s+afternoon|in\s+the\s+afternoon|l['’]apr[èe]s[- ]midi|"
                             r"fin\s+d['’]apr[èe]s[- ]midi)\b", re.I)),
    ("evening", re.compile(r"\b(?:sun\s+(?:\w+\s+){0,3}(?:sets|setting|set|sinks|sinking)|sunset|dusk|twilight|evening|"
                           r"dinner|supper|coucher\s+du\s+soleil|soleil\s+(?:\w+\s+){0,2}couche|cr[ée]puscule|"
                           r"ce\s+soir|la\s+soir[ée]e|le\s+soir|d[îi]ner|souper)\b", re.I)),
    ("night", re.compile(r"\b(?:night\s+(?:falls|has\s+fallen)|nightfall|dead\s+of\s+(?:the\s+)?night|late\s+at\s+night|"
                         r"midnight|moonlight|the\s+night\s+is|la\s+nuit\s+(?:est\s+)?tomb[ée]e?|tomb[ée]e\s+de\s+la\s+nuit|"
                         r"nuit\s+noire|minuit|en\s+pleine\s+nuit|clair\s+de\s+lune)\b", re.I)),
]
NEXT_DAY = re.compile(r"\b(?:the\s+next\s+(?:morning|day)|next\s+morning|the\s+following\s+(?:morning|day)|the\s+morning\s+"
                      r"after|(?:le|au)\s+lendemain(?:\s+matin)?|le\s+jour\s+suivant|le\s+matin\s+suivant)\b", re.I)
MORNING_WORD = re.compile(r"morning|matin", re.I)
# test 2: "I lie down and try to sleep" then "at dawn" never counted a new day (the cues read only the reply)
SLEEP = re.compile(r"\b(?:go(?:es)?\s+to\s+(?:bed|sleep)|went\s+to\s+bed|fall(?:s)?\s+asleep|fell\s+asleep|sleep(?:s)?\s+through|"
                   r"(?:try|tries)\s+to\s+sleep|lie\s+down\s+and\s+(?:try\s+to\s+)?sleep|bed\s+early|night'?s\s+sleep|"
                   r"(?:me|se|vous)\s+couch|m['’]endor|s['’]endor|vous\s+endorm|dorm(?:ir|ez|ons))\b", re.I)


def period_rank(value: Any) -> int:
    """0 unknown, then 1 dawn ... 6 night, for a stored time ("09:00", "evening", "late morning")."""
    v = str(value or "").strip()
    if not v:
        return 0
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
    if m:
        h = int(m.group(1)) % 24
        return 1 if 5 <= h < 7 else 2 if 7 <= h < 12 else 3 if h == 12 else 4 if 13 <= h < 18 else 5 if 18 <= h < 21 else 6
    low = v.casefold()
    for k, name in reversed(list(enumerate(PERIODS, 1))):
        if name in low:
            return k
    for k, words in ((1, ("aube",)), (2, ("matin",)), (3, ("midi",)), (4, ("après-midi", "apres-midi")),
                     (5, ("soir", "crépuscule")), (6, ("nuit", "minuit"))):
        if any(w in low for w in words):
            return k
    return 0


def time_cues(reply: str, scene: dict[str, Any], player_turn: str = "") -> dict[str, Any]:
    """{"time": period | None, "days": 0/1, "evidence": quote} read in the reply's narration (see B3 above)."""
    narration = SPEECH_SPANS.sub(lambda m: " " * len(m.group(0)), reply or "")
    out: dict[str, Any] = {"time": None, "days": 0, "evidence": ""}
    nd = NEXT_DAY.search(narration)
    start = 0
    if nd:
        out.update(days=1, evidence=nd.group(0), time="morning" if MORNING_WORD.search(nd.group(0)) else None)
        start = nd.end()
    last = None
    for name, pat in PERIOD_CUES:
        for m in pat.finditer(narration, start):
            if last is None or m.start() > last[1].start():
                last = (name, m)
    if last is None:
        return out
    name, m = last
    new_rank, cur_rank = PERIODS.index(name) + 1, period_rank(scene.get("time"))
    slept = bool(SLEEP.search(player_turn or "") or SLEEP.search(narration))
    if not out["days"] and new_rank <= 2 and (cur_rank >= 4 or (slept and cur_rank >= 2)):
        out["days"] = 1  # from the afternoon, evening or night (or after a night's sleep) to dawn or morning: a new day
    if out["days"] or new_rank > cur_rank:
        out["time"], out["evidence"] = name, out["evidence"] or m.group(0)
        if out["days"] and not nd:
            out["evidence"] = m.group(0)
    return out


# Test 2: most moves were never reported by the analysis (cut by the next reply, or silent about the place): the
# scene stayed in the "Pure White Space" for 15 turns. A clear arrival in the narration ("you step into the dining
# hall", "she leads you into a large bedchamber", "you find yourself in an opulent throne room") sets the place when
# the analysis gives none. Narration only; a short noun phrase; never a place someone talks about.
_ARTICLE = r"(?:the|a|an|his|her|their|your|its)"
ARRIVAL = re.compile(
    r"\b(?:(?:you|vous)\s+(?:step|walk|stride|wander|ride|head|go)\s+(?:in|into|out\s+into|through\s+into)|"
    r"(?:you|vous)\s+(?:to\s+)?(?:enter|arrive\s+(?:at|in)|reach|emerge\s+into|make\s+your\s+way\s+(?:down\s+|up\s+|back\s+)?(?:to|into))|"
    r"(?:you|vous)\s+find\s+yourself\s+(?:standing\s+|sitting\s+|lying\s+)?(?:in|at|inside)(?:\s+the\s+(?:middle|center|centre)\s+of)?|"
    r"leads?\s+you\s+(?:\w+\s+){0,9}?(?:into|to|out\s+into)|emerging\s+into)\s+"
    rf"(?:{_ARTICLE}\s+)?((?:[A-Za-zÀ-ÿ'’-]+\s+){{0,4}}?[A-Za-zÀ-ÿ'’-]+)"
    r"(?=\s*(?:[,.;:!?]|$|\s+(?:for|with|where|as|and|to|of|that|which|while|at|in|on|beyond|behind|before|after|"
    r"under|near|filled|lined|surrounded|dominated|tomorrow|today|tonight|now|again|once|later|soon|alone)\b))", re.I)
ASKED = re.compile(r"\b(?:tells?|asks?|orders?|wants?|urges?|invites?|begs?|expects?|needs?|commands?)\s+you\s+to\b", re.I)
PLACE_STOP = {"view", "silence", "light", "darkness", "hand", "arms", "embrace", "eyes", "conversation", "room", "door",
              "doorway", "doors", "it", "them", "him", "her", "place", "fray", "fight"}
LEAD_ADJ = re.compile(r"^(?:large|small|vast|grand|huge|massive|opulent|spacious|dimly\s+lit|quiet|busy|crowded|"
                      r"lavish|ornate|cozy|cosy|narrow|wide|long|bright|dark)\s+", re.I)


def place_cue(reply: str, scene: dict[str, Any]) -> tuple[str, str] | None:
    """(place, quote) of the last clear arrival in the narration, when it differs from the current place."""
    from .scene_cast import same_place
    narration = SPEECH_SPANS.sub(lambda m: " " * len(m.group(0)), reply or "")
    hits = [m for m in ARRIVAL.finditer(narration)
            if not ASKED.search(narration[max(0, m.start() - 30):m.start() + 10])]  # "tells you to enter": not a move
    for m in reversed(hits):
        place = LEAD_ADJ.sub("", m.group(1).strip()).strip()
        words = place.split()
        if not words or len(place) < 3 or (len(words) == 1 and words[0].casefold() in PLACE_STOP) \
                or len(place) > MAX_LEN["location"]:
            continue
        if scene.get("location") and same_place(scene.get("location"), place):
            return None
        return place, m.group(0).strip()[:160]
    return None


def with_cues(update: dict[str, Any], reply: str, scene: dict[str, Any], year_start: str = "January",
              player_turn: str = "") -> dict[str, Any]:
    """Complete a validated update with the narration's time cues when the analysis set no time and no new day."""
    update = update or {"changes": {}, "days_passed": 0, "evidence": {}, "dropped": []}
    update.setdefault("changes", {})
    update.setdefault("evidence", {})
    changes = update["changes"]
    if "location" not in changes:
        hit = place_cue(reply, scene)
        if hit:
            changes["location"], update["evidence"]["location"] = hit
            update["cues"] = True
    if changes.get("time") and changes["time"] != "":
        return update
    cue = time_cues(reply, scene, player_turn)
    if update.get("days_passed"):  # the analysis counted the day: only the time of day may still be missing
        if cue["time"] and changes.get("time") == "":
            changes["time"], update["evidence"]["time"] = cue["time"], cue["evidence"]
        return update
    if cue["days"]:
        update["days_passed"] = 1
        update["evidence"]["days_passed"] = cue["evidence"]
        for k, v in advance(scene, 1, year_start).items():
            changes.setdefault(k, v)
        changes["time"] = cue["time"] or ""
        if cue["time"]:
            update["evidence"]["time"] = cue["evidence"]
        update["cues"] = True
    elif cue["time"] and cue["time"] != scene.get("time"):
        changes["time"], update["evidence"]["time"] = cue["time"], cue["evidence"]
        update["cues"] = True
    return update


def apply_from_analysis(db: Session, story: Story, branch: MessageBranch, message_id: str, update: dict[str, Any],
                        index: EntityIndex, *, first_reply: bool = False) -> dict[str, Any] | None:
    """Apply a validated update for the branch head (idempotent: an earlier update from the same reply is reverted
    first). Returns the history entry, or None when nothing changed.

    ``first_reply``: this is the story's first narrated reply, so its day is D1 even when it establishes nothing else
    (v1.5.1 — before, D1 was recorded only together with another change, so a story could stay "untracked"). A story
    that already had replies before day tracking keeps an unknown day instead of being told it is D1."""
    revert_message(db, story, branch, {message_id}, "the reply was analysed again")
    update = update or {}
    if not update.get("changes") and not update.get("days_passed") and not first_reply:
        return None
    update.setdefault("changes", {})
    update.setdefault("evidence", {})
    row = state_service.current(db, branch.id)
    state = state_service.normalize(json.loads(json.dumps(row.state_json)) if row else {})
    sc = state["scene"]
    changes: dict[str, list[Any]] = {}
    for f, v in update["changes"].items():
        if sc.get(f) != v:
            changes[f] = [sc.get(f), v]
            sc[f] = v
            sc.setdefault("established", {})[f] = {"message_id": message_id, "evidence": (update["evidence"].get(f) or "")[:160]}
    if "location" in changes:
        lid = index.resolve(sc["location"])
        sc["location_id"] = lid if lid and index.entities[lid].category == "location" else None
    days = int(update.get("days_passed") or 0)
    before = sc.get("story_day")
    if days and (before is not None or first_reply):
        sc["story_day"] = (before or 1) + days
        changes["story_day"] = [before, sc["story_day"]]  # a revert restores exactly this
    elif before is None and first_reply:
        sc["story_day"] = 1  # the first narrated reply of a story is D1
        changes["story_day"] = [None, 1]
    if not changes:
        return None
    entry = {"message_id": message_id, "at": now_iso(), "auto": True, "changes": changes, "days_passed": days,
             "evidence": {k: (v or "")[:160] for k, v in update.get("evidence", {}).items()}}
    sc["world_history"] = [*(sc.get("world_history") or []), entry][-60:]
    summary = "World: " + ", ".join(f"{k} {fmt(o)} → {fmt(n)}" for k, (o, n) in changes.items())
    state_service.save(db, story.id, branch.id, state, source="analysis_auto", summary=summary[:2000], message_id=message_id)
    return entry


def fmt(v: Any) -> str:
    return NOT_ESTABLISHED if v in (None, "") else str(v)


def revert_message(db: Session, story: Story, branch: MessageBranch, message_ids: set[str], why: str) -> int:
    row = state_service.current(db, branch.id)
    if row is None:
        return 0
    state = state_service.normalize(json.loads(json.dumps(row.state_json)))
    sc = state["scene"]
    n = 0
    for e in reversed(sc.get("world_history") or []):  # newest first, so each field returns to its previous value
        if e.get("message_id") not in message_ids or e.get("reverted_at"):
            continue
        kept = []
        for f, (old, new) in (e.get("changes") or {}).items():
            if sc.get(f) == new:  # still this reply's value (not replaced by a later reply or a manual edit)
                sc[f] = old
                if (sc.get("established") or {}).get(f, {}).get("message_id") == e["message_id"]:
                    sc["established"].pop(f, None)
            else:
                kept.append(f)
        e["reverted_at"], e["revert_reason"] = now_iso(), why
        if kept:
            e["revert_kept"] = kept
        n += 1
    if n:
        state_service.save(db, story.id, branch.id, state, source="analysis_revert", summary=f"World state: reverted {n} update(s): {why}")
    return n


def reconcile(db: Session, story: Story, branch: MessageBranch, also: set[str] | None = None) -> int:
    live = story_tree.live_path_ids(db, branch)
    row = state_service.current(db, branch.id)
    if row is None:
        return 0
    hist = ((row.state_json or {}).get("scene") or {}).get("world_history") or []
    stale = {e["message_id"] for e in hist if e.get("message_id") and not e.get("reverted_at")
             and (e["message_id"] not in live or e["message_id"] in (also or set()))}
    return revert_message(db, story, branch, stale, "its source reply was changed or is no longer part of the story") if stale else 0


def calendar_text(sc: dict[str, Any], year_label: str = "Year") -> str | None:
    parts = [sc.get("weekday") or "", " ".join(str(x) for x in (sc.get("day"), sc.get("month")) if x not in (None, ""))]
    date = ", ".join(p for p in parts if p)
    if sc.get("year") not in (None, ""):
        date = f"{date}, {year_label} {sc['year']}" if date else f"{year_label} {sc['year']}"
    return date or (sc.get("date") or None)  # the free-text date a player typed earlier still counts


def render_for_narrator(sc: dict[str, Any], year_label: str = "Year") -> str:
    """Scene lines for the narrator: every field, 'not established' when unknown, plus the consistency rule.
    ``year_label``: the world's name for its years (pack.json → calendar), e.g. "Imperial Calendar 1301"."""
    lines = [f"In-story day: D{sc.get('story_day') or 1} (story-world time, not the real date)",
             f"Calendar: {calendar_text(sc, year_label) or NOT_ESTABLISHED}",
             f"Time of day: {fmt(sc.get('time'))}", f"Location: {fmt(sc.get('location'))}", f"Weather: {fmt(sc.get('weather'))}",
             "Keep these consistent; change them only when the story moves on, visibly in the narration. When a lesson, "
             "a meeting or a clock makes it natural, state the hour once."]
    missing = [label for label, v in (("time of day", sc.get("time")), ("weather", sc.get("weather"))) if not v]
    if missing:
        # v1.5: in the owner's 120-message story the weather was almost never stated, so the bar showed "not established"
        # for most of the session; the narrator is now asked to establish it — naturally, never as an invented clock
        lines.append(f"Not yet established: {' and '.join(missing)}. When a scene begins or moves, or time passes, "
                     "establish them in one brief natural detail (light, sky, bells, rain); an approximate time is enough.")
    if not calendar_text(sc):
        lines.append("Calendar date: not established; invent a precise date only if the story calls for one.")
    # v1.5.1: the app shows a day/date/time/weather/place header above each reply from these values
    lines.append("Never write a date/time/location header line (the app shows one).")
    return "\n".join(lines)


def calendar_of(db: Session, world_id: str | None) -> dict[str, Any]:
    """The world's calendar conventions, from its pack (``pack.json`` → ``calendar``; never invented):
    ``year_start`` (month on which the year number changes), ``year_label`` (e.g. "Imperial Year"), ``provenance`` and,
    for a pack with the ``school`` module, ``first_year_start`` (day 1 of the year's first month, the intake date that
    may be *offered* to a new story). Without a calendar: January, "Year"."""
    out = {"year_start": "January", "year_label": "Year", "provenance": None, "first_year_start": None}
    from . import world_pack

    pack = world_pack.of(db, world_id)
    cal = pack.get("calendar")
    if cal:
        out.update(year_start=cal["year_start"], year_label=cal["year_label"], provenance="pack.json calendar")
        if world_pack.has_module(pack, "school"):
            out["first_year_start"] = {"month": cal["year_start"], "day": 1}
    return out


FIRST_YEAR_RE = re.compile(r"\b(first[- ]years?|1st[- ]years?|entrance (?:evaluation|exam|ceremony)|intake|new students?|"
                           r"enrol(?:l|ls|led|ment)?s?|first day (?:at|of) (?:the )?academy|transfer students?)\b", re.I)


def date_suggestion(db: Session, story: Story, sc: dict[str, Any]) -> dict[str, Any] | None:
    """A suggested start date to *offer* (never applied automatically): only for a new story (at most one narrated
    reply) with no date established at all, whose world calendar names the start of the year and whose own setup is a
    first-year intake. Day 1 of the year's
    first month; no year and no weekday (the lore gives no anchor for either)."""
    if calendar_text(sc) or (sc.get("story_day") or 1) > 1:
        return None
    cal = calendar_of(db, story.world_id)
    if not cal["first_year_start"]:
        return None
    s = story.settings_json or {}
    setup = " ".join(str(s.get(k) or "") for k in ("starter_blueprint", "starter_id"))
    from ..models import Message
    from sqlalchemy import select
    replies = db.scalars(select(Message.id).where(Message.story_id == story.id, Message.deleted_at.is_(None),
                                                  Message.role == "assistant", Message.kind == "story").limit(2)).all()
    if len(replies) > 1:
        return None  # only offered to a new story (an ongoing story keeps whatever it has established)
    first = db.scalars(select(Message).where(Message.story_id == story.id, Message.deleted_at.is_(None))
                       .order_by(Message.seq).limit(2)).all()
    setup += " " + " ".join((m.content or "")[:1500] for m in first) + " " + (story.title or "")
    if not FIRST_YEAR_RE.search(setup):
        return None
    fy = cal["first_year_start"]
    return {"month": fy["month"], "day": fy["day"], "label": f"{fy['day']} {fy['month']}",
            "reason": "Start of the academic year for first-year students (entrance evaluation in the first week of "
                      f"{fy['month']}).", "provenance": cal["provenance"]}


ANALYSIS_SHAPE = ('"world_state": {"changes": [{"field": "location|time|weather|weekday|day|month|year", "value": str, '
                  '"evidence": "exact short quote"}], "days_passed": 0, "days_evidence": ""},')
ANALYSIS_RULE = ("- world_state: only what the REPLY or PLAYER TURN explicitly establishes or changes (place, time of day, "
                 "weather, calendar) compared with CURRENT WORLD STATE. location: only where the protagonist now IS (they "
                 "went or arrived there in the narration); a place someone only talks about, plans or remembers is not a "
                 "change. Each change with an exact short quote. days_passed: "
                 "in-story days passing in this reply (sleeping until morning = 1), with a quote; else 0. Weather from a "
                 "concrete description (\"rain drummed on the windows\" -> rain), time of day from light or bells. An hour "
                 "stated in the text (\"at eight thirty\", \"20h15\") as 24-hour HH:MM; anything vaguer stays a time of day "
                 "(\"late morning\"): never work out an hour from light or bells. Never put the day counter in the time, "
                 "never guess a date or weather. Nothing changes: [].\n")


def analysis_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {
        "changes": {"type": "array", "maxItems": len(FIELDS), "items": {"type": "object", "properties": {
            "field": {"type": "string", "enum": list(FIELDS)}, "value": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["field", "value", "evidence"]}},
        "days_passed": {"type": "integer", "minimum": 0, "maximum": MAX_DAYS_PASSED}, "days_evidence": {"type": "string"}},
        "required": ["changes", "days_passed", "days_evidence"]}


def prompt_state(sc: dict[str, Any]) -> str:
    return (f"CURRENT WORLD STATE (before this reply): D{sc.get('story_day') or 1}; calendar: {calendar_text(sc) or NOT_ESTABLISHED}; "
            f"time: {fmt(sc.get('time'))}; location: {fmt(sc.get('location'))}; weather: {fmt(sc.get('weather'))}")


def display(sc: dict[str, Any]) -> dict[str, Any]:
    """What the story header shows (frontend formats it; unknown parts are explicit)."""
    return {"story_day": sc.get("story_day") or 1, "weekday": sc.get("weekday") or None, "day": sc.get("day"),
            "month": sc.get("month") or None, "year": sc.get("year"), "date_text": sc.get("date") or None,
            "time": sc.get("time") or None, "location": sc.get("location") or None, "weather": sc.get("weather") or None,
            "established": {k: v.get("message_id") for k, v in (sc.get("established") or {}).items()}}
