"""Planned events (v0.6, 19/11): scenes the pack's author decides in advance, played by the narrator its own way.

A pack lists them in ``pack.json`` → ``events`` (and the player choices they depend on in ``choices``, e.g. the academy
wing). Before each reply the app picks at most one *due* event (no model call) and hands it to the narrator in the
turn's context: what must happen, never how. The narrator marks the reply where it happens with a hidden ``[Event:id]``
(removed from the text like the music and portrait tags, services/portrait_tags.TagFilter) and a player choice once it is
clear with ``[Choice:wing=knight]``.

Everything is read from the replies on the story's current path (``generation_metadata_json``), so another branch, a
regenerated or deleted reply has its own progress and nothing is stored elsewhere:

* ``event_tags`` / ``choice_tags``  — what the narrator marked in that reply;
* ``context.planned_event``         — the event the app asked for in that reply (counts the reminders).

An event the narrator was asked for ``firm_after`` times is asked for firmly (start it now, adapted to where the
protagonist is); after ``give_up_after`` reminders without its tag it is considered played (a small model may play it
and forget the tag; no event is asked for forever). A choice may also come from the player's own words (an option's
``keywords``), when exactly one option matches.
"""
from __future__ import annotations

import re
from typing import Any

from ..models import Message
from .world_state import MONTHS

EVENT_TAG = re.compile(r"\[\s*(?:event|[ée]v[ée]nement)\s*[:|]\s*([A-Za-z0-9_\-]{1,40})\s*\]", re.IGNORECASE)
CHOICE_TAG = re.compile(r"\[\s*(?:choice|choix)\s*[:|]\s*([A-Za-z0-9_\-]{1,40})\s*=\s*([A-Za-z0-9_\-]{1,40})\s*\]",
                        re.IGNORECASE)
FIRM_AFTER = 2
GIVE_UP_AFTER = 6


def events_of(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in pack.get("events") or [] if isinstance(e, dict) and e.get("id")]


def choices_of(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in pack.get("choices") or [] if isinstance(c, dict) and c.get("id")]


def text_of(v: Any, lang: str = "en") -> str:
    """A text given once or per language ({"en": ..., "fr": ...})."""
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("en") or v.get("default") or next(iter(v.values()), "") or "")
    return str(v or "")


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def choice_from_words(choice: dict[str, Any], text: str) -> str | None:
    """The one option whose keywords appear in the player's words (None when none or several do)."""
    t = _norm(text)
    hits = [o["id"] for o in choice.get("options") or []
            if any(re.search(rf"(?<!\w){re.escape(_norm(k))}(?!\w)", t) for k in o.get("keywords") or [] if k)]
    return hits[0] if len(hits) == 1 else None


def progress(pack: dict[str, Any], path: list[Message]) -> dict[str, Any]:
    """What happened on this path: played events (and the player turn when), reminders, choices, player turns."""
    events = {e["id"]: e for e in events_of(pack)}
    choices = {c["id"]: c for c in choices_of(pack)}
    options = {cid: {o["id"] for o in c.get("options") or []} for cid, c in choices.items()}
    done: dict[str, int] = {}      # event id -> player turn when it was played (or given up)
    how: dict[str, str] = {}       # event id -> "tag" | "given_up"
    noted: dict[str, int] = {}     # event id -> replies that were asked for it
    chosen: dict[str, str] = {}
    chosen_at: dict[str, int] = {}
    turns = 0
    for m in path:
        if m.deleted_at or m.kind != "story":
            continue
        if m.role == "user":
            if m.command_json:
                # v0.7.4: an opening whose prologue already plays planned events (pack.json starter "events_played")
                if m.command_json.get("name") == "start":
                    for eid in m.command_json.get("events_played") or []:
                        if eid in events and eid not in done:
                            done[eid], how[eid] = 0, "opening"
                continue
            turns += 1
            for cid, c in choices.items():
                if cid not in chosen:
                    v = choice_from_words(c, m.content or "")
                    if v:
                        chosen[cid], chosen_at[cid] = v, turns
            continue
        if m.role != "assistant" or m.status not in ("complete", "partial"):
            continue
        md = m.generation_metadata_json or {}
        for t in md.get("choice_tags") or []:
            cid, v = t.get("choice"), t.get("value")
            if cid in options and v in options[cid]:
                if chosen.get(cid) != v:
                    chosen_at[cid] = turns
                chosen[cid] = v  # the narrator's mark wins over the player's words
        for eid in md.get("event_tags") or []:
            if eid in events and eid not in done:
                done[eid], how[eid] = turns, "tag"
        asked = ((md.get("context") or {}).get("planned_event") or {}).get("id")
        if asked in events and asked not in done:
            noted[asked] = noted.get(asked, 0) + 1
            limit = int(events[asked].get("give_up_after") or GIVE_UP_AFTER)
            if noted[asked] >= limit:
                done[asked], how[asked] = turns, "given_up"
    return {"done": done, "how": how, "noted": noted, "choices": chosen, "chosen_at": chosen_at, "turns": turns}


def _date_reached(want: dict[str, Any], scene: dict[str, Any], year_start: str) -> bool:
    """A month/day in the story's year (the year starts on the world's new-year month): reached or not."""
    month = want.get("month")
    if isinstance(month, int) and 1 <= month <= 12:
        month = MONTHS[month - 1]
    cur_m, cur_d = scene.get("month"), scene.get("day")
    if month not in MONTHS or cur_m not in MONTHS or not isinstance(cur_d, int):
        return False  # an unknown date never triggers a dated event
    start = MONTHS.index(year_start) if year_start in MONTHS else 0
    key = lambda m, d: ((MONTHS.index(m) - start) % 12, d)  # noqa: E731
    return key(cur_m, cur_d) >= key(month, int(want.get("day") or 1))


def due(pack: dict[str, Any], prog: dict[str, Any], scene: dict[str, Any] | None,
        year_start: str = "January") -> dict[str, Any] | None:
    """The first event (in the pack's order) whose conditions are met and that is not played yet:
    {"event": ..., "firm": bool, "variant": text | None, "choice": (choice, option) | None}."""
    scene = scene or {}
    done, chosen, turns = prog["done"], prog["choices"], prog["turns"]
    resolved = dict(done)
    for ev in events_of(pack):  # an event skipped because its choice is already known counts as resolved
        cid = ev.get("skip_if_choice")
        if cid and cid in chosen and ev["id"] not in resolved:
            resolved[ev["id"]] = prog["chosen_at"].get(cid, 0)
    for ev in events_of(pack):
        if ev["id"] in resolved:
            continue
        after = [a for a in ev.get("after") or [] if isinstance(a, str)]
        if any(a not in resolved for a in after):
            continue
        since = max([resolved[a] for a in after], default=0)
        if turns - since < int(ev.get("delay_turns") or 0):
            continue
        if turns < int(ev.get("from_turn") or 0):
            continue
        day = ev.get("from_story_day")
        if day and int(scene.get("story_day") or 1) < int(day):
            continue
        if isinstance(ev.get("from_date"), dict) and not _date_reached(ev["from_date"], scene, year_start):
            continue
        need = ev.get("needs_choice")
        if need and need not in chosen:
            continue  # waits for the choice (another event, or the player, settles it)
        variant, picked = None, None
        variants = ev.get("variants") or {}
        if need or variants:
            cid = need or next((c["id"] for c in choices_of(pack) if any(o["id"] in variants for o in c.get("options") or [])), None)
            if cid and cid in chosen:
                picked = (cid, chosen[cid])
                variant = variants.get(chosen[cid])
        firm = prog["noted"].get(ev["id"], 0) >= int(ev.get("firm_after") or FIRM_AFTER)
        return {"event": ev, "firm": firm, "variant": variant, "choice": picked}
    return None


def narrator_note(d: dict[str, Any], pack: dict[str, Any], name_of, protagonist: str) -> str:
    """The turn's note for the narrator (English, like every instruction)."""
    ev = d["event"]
    lines = [text_of(ev.get("brief"))]
    if d["variant"]:
        c = next((c for c in choices_of(pack) if c["id"] == d["choice"][0]), {})
        o = next((o for o in c.get("options") or [] if o["id"] == d["choice"][1]), {})
        lines.append(f"For {protagonist}'s {text_of(c.get('name')) or d['choice'][0]} "
                     f"({text_of(o.get('name')) or d['choice'][1]}): {d['variant']}")
    names = [name_of(cid) for cid in ev.get("characters") or [] if isinstance(cid, str)]
    if names:
        lines.append("Characters involved: " + ", ".join(n for n in names if n) + ".")
    if d["firm"]:
        lines.append(f"It is overdue: start it in this reply, adapted to where {protagonist} is and what is happening "
                     "(a summons, a messenger, a bell, an announcement...).")
    else:
        lines.append("Bring it in within the next replies, at a natural moment. How it happens, where and what is said are "
                     f"yours to decide; never decide {protagonist}'s words or choices.")
    lines.append(f"In the reply where it takes place, write [Event:{ev['id']}] on its own line (the app removes it).")
    return "\n".join(x for x in lines if x)


def choice_rule(pack: dict[str, Any], chosen: dict[str, str], protagonist: str) -> str:
    """Narrator rule for the choices not known yet (stable: it changes only when a choice is settled)."""
    out = []
    for c in choices_of(pack):
        if c["id"] in chosen:
            continue
        opts = ", ".join(f"{o['id']} ({text_of(o.get('name')) or o['id']})" for o in c.get("options") or [])
        out.append(f"When {protagonist}'s {text_of(c.get('name')) or c['id']} becomes clear (the player states it, or it is "
                   f"settled in the story), write [Choice:{c['id']}=option] once, on its own line, with one of: {opts}.")
    return " ".join(out)


def played(pack: dict[str, Any], prog: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    """Played events for the Journal (title in the interface language), in the order they happened."""
    events = {e["id"]: e for e in events_of(pack)}
    rows = [{"id": eid, "title": text_of(events[eid].get("title"), lang) or eid, "turn": t, "how": prog["how"][eid]}
            for eid, t in prog["done"].items() if eid in events]
    return sorted(rows, key=lambda r: r["turn"])
