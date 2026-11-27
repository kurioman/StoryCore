"""Budgeted context construction with a manifest for the Context Inspector.

Order: core prompt + preset → global note → story note → avatar + player state → scene/cast/relationships →
pinned memories → relevant events/facts → lore + local canon → rolling recap → recent messages.
Token counts are approximations (≈ chars/4) and are labelled as such in the UI.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from ..models import (Avatar, EntityFact, LocalCanon, LoreChunk, LoreEntity, Message, MessageBranch, Recap, Story,
                      StoryEvent, UserNote, World)
from ..providers.base import ChatMessage
from . import music as music_svc
from . import narration_language, portrait_tags, settings_service, state_service, story_events, story_tree, world_pack
from .entities import EntityIndex, build_index
from .lore_import import is_empty_mark

STOPWORDS = set("""the and that with this from have what your their there they them then than into about would could should
which while where when were been being just like some more most other over only very also will shall must does did done
make made take took give gave know knew said says tell told look looked turn turned back still even ever every each
ooc""".split())

FACT_LABELS = {
    "established": "", "witnessed": "WITNESSED", "claim": "CLAIM (said by a character; may be false)",
    "rumour": "RUMOUR (unconfirmed)", "belief": "BELIEF", "plan": "PLAN (not yet happened)",
    "hypothetical": "HYPOTHETICAL (did not happen)", "dream_vision": "DREAM/VISION (not literal fact)", "secret": "SECRET",
}


LORE_BUDGET_MAX = 700  # phase 2: places, groups and terms only (characters have their short card)


def est_tokens(s: str) -> int:
    return math.ceil(len(s or "") / 4)


@dataclass
class Section:
    key: str
    title: str
    text: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return est_tokens(self.text)


@dataclass
class BuiltContext:
    system: str
    messages: list[ChatMessage]
    manifest: dict[str, Any]
    secrets: list[str] = field(default_factory=list)  # narrator-only text inside `system`; redact before showing it
    # v0.5 phase 7.3 ("stable" layout): the per-turn sections, sent at the top of the player's last message
    turn_context: str = ""

    @property
    def instructions(self) -> str:
        """Everything the narrator is told, wherever it is placed (for side requests that send only a system prompt)."""
        return self.system + (f"\n\n{self.turn_context}" if self.turn_context else "")


def fts_query(text_: str, limit_terms: int = 12) -> str:
    words = re.findall(r"[^\W\d_]{4,}", text_.lower())
    seen: list[str] = []
    for w in words:
        if w not in STOPWORDS and w not in seen:
            seen.append(w)
    return " OR ".join(f'"{w}"' for w in seen[-limit_terms:])


def _visible(rec_sources: list[str], rec_branch: str | None, path_ids: set[str], lineage: list[str]) -> bool:
    if rec_sources:
        return all(s in path_ids for s in rec_sources)
    return rec_branch is None or rec_branch in lineage


def visible_events(db: Session, story: Story, branch: MessageBranch, path_ids: set[str]) -> list[StoryEvent]:
    lineage = story_tree.lineage_branch_ids(db, branch)
    rows = db.scalars(select(StoryEvent).where(StoryEvent.story_id == story.id))
    return [e for e in rows if _visible(e.source_message_ids_json or [], e.branch_id, path_ids, lineage)]


def visible_facts(db: Session, story: Story, branch: MessageBranch, path_ids: set[str]) -> list[EntityFact]:
    lineage = story_tree.lineage_branch_ids(db, branch)
    rows = db.scalars(select(EntityFact).where(or_(EntityFact.story_id == story.id, EntityFact.story_id.is_(None))))
    return [f for f in rows if f.story_id is None or _visible(f.source_message_ids_json or [], f.branch_id, path_ids, lineage)]


def render_fact(f: EntityFact, index: EntityIndex) -> str:
    label = FACT_LABELS.get(f.fact_kind, "")
    if f.fact_kind == "belief" and f.belief_holder_id:
        label = f"BELIEF held by {index.name(f.belief_holder_id)} (may be false)"
    if f.status == "disputed":
        label = ("DISPUTED " + label).strip()
    subj = index.name(f.subject_entity_id) if f.subject_entity_id else (f.subject_label or "")
    k = f.knowledge_json or {}
    know = ""
    if k.get("known_by"):
        know += " Known by: " + ", ".join(index.name(x) if x != "player" else "the protagonist" for x in k["known_by"]) + "."
    if k.get("hidden_from"):
        know += " NOT known by: " + ", ".join(index.name(x) if x != "player" else "the protagonist" for x in k["hidden_from"]) + \
                " — these characters must not act on it."
    return f"- {('[' + label + '] ') if label else ''}{(subj + ': ') if subj else ''}{f.content}{know}"


def render_avatar(av: dict[str, Any]) -> str:
    p = av.get("profile") or av
    fields = [("Name", p.get("display_name") or av.get("name")), ("Called by NPCs", p.get("called_name")),
              ("Age", p.get("age")), ("Pronouns", p.get("pronouns")), ("Gender", p.get("gender")),
              ("Occupation", p.get("occupation")), ("Social status", p.get("social_status")),
              ("Affiliations", p.get("affiliations"))]
    lines = [f"{k}: {v}" for k, v in fields if v not in (None, "", [])]
    ap = p.get("appearance") or {}
    if not isinstance(ap, dict):  # free-text appearance (older/imported avatars) must not break avatar rendering
        ap = {"description": str(ap)}
    struct = ap.get("structured") if isinstance(ap.get("structured"), dict) else {}
    app_struct = ", ".join(f"{k}: {v}" for k, v in struct.items() if v)
    if ap.get("description") or app_struct:
        lines.append("Appearance: " + " ".join(x for x in [ap.get("description", ""), f"({app_struct})" if app_struct else ""] if x))
    for k in ("backstory", "personality", "goals", "motivations", "fears", "values", "skills", "powers", "weaknesses",
              "secrets", "speech_style", "additional_info"):
        if p.get(k):
            lines.append(f"{k.replace('_', ' ').capitalize()}: {p[k]}")
    # the simple avatar (services/avatar_profile.py): abilities, then the player's own note, kept up to date in play
    if p.get("abilities"):
        ab = str(p["abilities"])
        lines.append(f"Abilities:\n{ab}" if "\n" in ab else f"Abilities: {ab}")
    if p.get("user_note"):
        lines.append("Player's note about this character (current, overrides older details):\n" + str(p["user_note"]))
    return "\n".join(lines)


def render_state(st: dict[str, Any], index: EntityIndex, year_label: str = "Year") -> tuple[str, str]:
    stats = ", ".join(
        f"{s['label']} {s.get('value')}" + (f"/{s['max']}" if s.get("type") == "current_max" and s.get("max") is not None else "")
        + (f" {s['unit']}" if s.get("unit") else "") for s in st.get("stats", []) if not s.get("hidden"))
    pl = st.get("player") or {}
    lines = []
    if pl.get("title"):
        lines.append(f"Title: {pl['title']}")
    if pl.get("condition"):
        lines.append(f"Condition: {pl['condition']}")
    if stats:
        lines.append(f"Stats: {stats}")
    if st.get("conditions"):
        lines.append("Status effects: " + "; ".join(f"{c['label']} ({c.get('severity', '')})" + (f" — {c['note']}" if c.get("note") else "") for c in st["conditions"]))
    if st.get("inventory"):
        lines.append("Inventory: " + ", ".join(f"{i['name']}" + (f" ×{i['qty']}" if (i.get("qty") or 1) != 1 else "") + (" (equipped)" if i.get("equipped") else "") for i in st["inventory"]))
    q = [q for q in st.get("quests", []) if q.get("status") == "active"]
    if q:
        lines.append("Active quests: " + "; ".join(q_["title"] + (" — next: " + next((o["text"] for o in q_.get("objectives", []) if not o.get("done")), "")) for q_ in q))
    for key, title in (("goals", "Immediate goals"), ("promises", "Pending promises"), ("mysteries", "Unresolved mysteries"), ("clues", "Known clues")):
        open_ = [x["text"] for x in st.get(key, []) if not x.get("resolved")]
        if open_:
            lines.append(f"{title}: " + "; ".join(open_))
    sc = st.get("scene") or {}
    from .world_state import render_for_narrator  # every clock field, "not established" when unknown (v1.4)
    scene_lines = [render_for_narrator(sc, year_label)] + [f"{k.capitalize()}: {sc[k]}" for k in ("chapter", "mood", "status") if sc.get(k)]
    if sc.get("present"):
        scene_lines.append("Present: " + ", ".join(index.name(c) for c in sc["present"]))
    scene_lines += render_relationships(st.get("relationships", []), index, focus=set(sc.get("present") or []))
    return "\n".join(lines), "\n".join(scene_lines)


# Phase 2 (step 3): lore records are sent without their bookkeeping (confidence, sources, ids...): it told the model
# that the lore was uncertain, and cost tokens without helping to write.
# Kurio (24/11): story functions, factions, notes and relationships are written for the narrator (when and how to use a
# character, who she is tied to): they are sent now; only the bookkeeping is left out
META_KEYS = re.compile(r"^\s*-?\s*(?:id|_index_type|confidence|canon_status|source_ids|term|schema_version|aliases)"
                       r"\s*:", re.I)


def compact_record(body: str) -> str:
    """A lore record without its bookkeeping lines and "[confidence: x]" marks."""
    out = []
    skipping = False
    for line in body.split("\n"):
        if META_KEYS.match(line):
            skipping = line.rstrip().endswith(":")  # a block ("relationship_notes:") goes with its indented lines
            continue
        if skipping and (line.startswith("  ") or line.lstrip().startswith("- target_id")):
            continue
        skipping = False
        line = re.sub(r"\s*\[(?:confidence|source confidence)[^\]]*\]", "", line)
        line = re.sub(r";?\s*confidence:\s*\w+", "", line)
        if line.strip():
            out.append(line.rstrip())
    return "\n".join(out)


SCHEDULE_WORDS = re.compile(
    r"\b(?:exams?|evaluations?|tests?|tournaments?|ceremon(?:y|ies)|festivals?|holidays?|vacations?|breaks?|schedules?|"
    r"timetables?|calendar|semesters?|terms?|deadlines?|galas?|graduation|enrol(?:l)?ment|dates?|months?|"
    r"january|february|march|april|june|july|august|september|october|november|december)\b", re.I)


DEPARTMENTS = {"knight_department": "Knight", "magic_department": "Magic", "theology_department": "Theology"}


def character_card(le, post: str | None = None) -> str:
    """Phase 2 (step 3): one compact line per character: name (gender; role): traits; looks."""
    d = le.data_json or {}
    gender = ", ".join(x for x in (str(d.get("gender") or "").strip(), str(d.get("pronouns") or "").strip()) if x)
    own = str(d.get("role") or "").strip()  # the pack's own words first (Kurio's 12-category records)
    # Kurio (24/11): the post alone ("First imperial princess") hid the rest of the role (year, wing, council...)
    role = own if own and (not post or post.casefold() in own.casefold()) else "; ".join(x for x in (post, own) if x)
    if not role:
        dept = DEPARTMENTS.get(str(d.get("department_id") or ""), str(d.get("department_id") or "").replace("_", " "))
        year = d.get("year")
        if le.entity_type == "student" or d.get("type") == "student":
            nth = {1: "1st", 2: "2nd", 3: "3rd"}.get(year, f"{year}th") if isinstance(year, int) else ""
            role = " ".join(x for x in (f"{nth}-year" if nth else "", dept, "student") if x)
        else:
            role = str(d.get("role") or d.get("occupation") or le.entity_type or "").replace("_", " ")
    status = str(d.get("social_status") or "").split(";")[0].strip()
    head = "; ".join(x for x in (gender, role, status) if x)
    traits = ", ".join((d.get("personality_traits") or [])[:6]) or (le.summary or "")[:120]
    looks = looks_of(d)
    return f"- {le.name}" + (f" ({head})" if head else "") + (f": {traits}" if traits else "") + (f"; looks: {looks}" if looks else "")


def _words(v: Any) -> str:
    """A lore value as one short line ("imperial_family" reads "imperial family")."""
    if isinstance(v, list):
        items = [_words(x) for x in v if x not in (None, "", [], {})]
        return " ".join(items) if all(i.endswith((".", "!", "?")) for i in items) else "; ".join(items)
    if isinstance(v, dict):
        return "; ".join(f"{k.replace('_', ' ')}: {_words(x)}" for k, x in v.items() if x not in (None, "", [], {}))
    s = str(v).strip()
    return s.replace("_", " ") if re.fullmatch(r"[a-z0-9_]+", s) else s


def character_play_card(le, post: str | None = None, names: dict[str, str] | None = None) -> str:
    """Kurio (24/11/2026): for a character in the scene, her whole record in a few lines (the 12 categories of the
    pack model), so the narrator plays her with her own voice, aims and limits. Until then only the one-line card
    above reached the model, and motivation, notes, story functions, "never" and relationships were never sent."""
    d = le.data_json or {}
    lines = [character_card(le, post)]
    ap = d.get("appearance")
    if isinstance(ap, dict):
        extra = {k: v for k, v in ap.items() if k not in ("hair", "eyes") and v}
        if extra:
            lines.append("  Looks: " + _words(extra))
    pw = d.get("power")
    if isinstance(pw, dict) and any(pw.values()):
        lines.append("  Power: " + _words(pw))
    for key, label in (("motivation", "Motivation"), ("notes", "Voice & notes"), ("story_functions", "In the story"),
                       ("never", "Never")):
        v = d.get(key)
        text = _words(v) if v not in (None, "", [], {}) and not is_empty_mark(v) else ""
        if text:
            lines.append(f"  {label}: {text}")
    ties = []
    for r in (d.get("relationships") or []) + (d.get("relationship_notes") or []):
        if isinstance(r, dict) and r.get("target_id"):
            who = (names or {}).get(r["target_id"], str(r["target_id"]).replace("_", " "))
            ties.append(f"{who} ({_words(r.get('type') or '')}" + (f", {r['note']}" if r.get("note") else "") + ")")
    if ties:
        lines.append("  Ties: " + "; ".join(ties))
    if d.get("faction_ids"):
        lines.append("  Factions: " + _words(d["faction_ids"]))
    return "\n".join(lines)


def looks_of(data: dict[str, Any] | None) -> str:
    """Hair and eyes from a lore record ("red hair, green eyes"), or "" when lore says nothing."""
    ap = (data or {}).get("appearance")
    if not isinstance(ap, dict):
        return ""
    return ", ".join(f"{ap[k]} {k}" for k in ("hair", "eyes") if ap.get(k))


def relationship_memories(r: dict[str, Any], n: int = 2) -> list[str]:
    """v0.6.2: why this relationship is where it is: its biggest change and its latest one ("defended her during the
    duel"), oldest first. Reverted and reasonless changes are skipped."""
    valid = []
    for i, h in enumerate(r.get("history") or []):
        why = str(h.get("reason") or "").strip().strip('"“”«» ')
        try:
            delta = abs(float(h.get("delta") or 0))
        except (TypeError, ValueError):
            delta = 0.0
        if why and delta and why.casefold() != "info table" and not h.get("reverts") \
                and h.get("source") != "analysis_revert":
            valid.append((i, delta, why[:90]))
    if not valid:
        return []
    picked = {max(valid, key=lambda x: (x[1], x[0]))[0], valid[-1][0]}
    out = []
    for i, _, why in valid:
        if i in picked and why not in out:
            out.append(why)
    return out[-n:]


def render_relationships(rels: list[dict[str, Any]], index: EntityIndex, focus: set[str] | None = None) -> list[str]:
    """Directional, as stored (v1.3 decision 6): a record without ``source_id`` is that character's view of the
    protagonist; with ``source_id`` it is one character's view of another (or the player's own stance). v1.4 fix: these
    were all labelled "protagonist → NPC" and character-to-character records lost their source.

    v0.6.2 (Kurio: a close friend met again 50 messages later must still be a close friend): each line also gives the
    stage in words ("Close / trusted"), and for the characters in the scene (``focus``) the last reasons the
    relationship moved, so the narrator knows why, not only how much."""
    from .relationships import tier

    def line(r: dict[str, Any], who: str) -> str:
        axes = ", ".join(f"{k} {v}" for k, v in (r.get("axes") or {}).items() if v)
        stage = tier(r.get("axes") or {})["tier"] if any((r.get("axes") or {}).values()) else ""
        label = r.get("label", "") or ""
        head = " / ".join(x for x in (label, stage) if x and x != "Acquaintance") or label or stage
        out = f"- {who}: {head}" + (f" ({axes})" if axes else "") + (f" — {r['note']}" if r.get("note") else "")
        ids = {r.get("target_id"), r.get("source_id")}
        mem = relationship_memories(r) if focus and ids & focus else []
        return out + (f" — remembered: {'; '.join(mem)}" if mem else "")

    name = lambda r, k: r.get(f"{k}_name") or index.name(r.get(f"{k}_id") or "")  # noqa: E731
    towards = [line(r, f"{name(r, 'target')} → protagonist") for r in rels if not r.get("source_id")]
    own = [line(r, f"protagonist → {name(r, 'target')}") for r in rels if r.get("source_id") == "protagonist"]
    between = [line(r, f"{name(r, 'source')} → {name(r, 'target')}") for r in rels
               if r.get("source_id") and r.get("source_id") != "protagonist"]
    out = []
    if towards:
        out += ["How characters regard the protagonist (axes −100..100; directional, story-evolved):", *towards]
    if own:
        out += ["The protagonist's own stance (set by the player only):", *own]
    if between:
        out += ["Between characters (directional; A → B is A's view of B; story-evolved):", *between]
    return out


AGENCY_RULES = (
    "Player agency rules: you control the world, NPCs, consequences and outside events; the user alone controls the "
    "protagonist. Never write the protagonist's dialogue, deliberate actions, decisions, commitments, emotional "
    "conclusions or consent unless the user stated them, and never pick an option on their behalf or skip past a major "
    "decision. You may describe what the protagonist perceives and the visible results of actions the user already "
    "specified, without turning an inferred feeling or impulse into a choice. NPCs act only on what they plausibly know. "
    "Keep established setting, abilities, relationships and consequences; not every scene needs combat, romance or high "
    "drama. Stop at a meaningful point for the player when appropriate. Do not end with a numbered menu of options: the "
    "app offers suggested actions separately."
)


AGENCY_REMINDER = (
    "\n\n[Narrator reminder, not part of the story: only the player decides what {name} says, does, decides or feels. "
    "Write the world's and the other characters' response, without new dialogue or actions for {name}, and stop where "
    "{name} would act next. No numbered list of options at the end.]"
)

# Operational version of the rules, placed as the LAST system section (closest to the conversation, which smaller local
# models weigh most). It must stay universal: world prompts and story overrides come earlier and cannot replace it.
NARRATION_RULES = (
    "You narrate the world, the other characters and the consequences of what the player states. The player alone "
    "authors {name}.\n"
    "- Never write {name}'s dialogue, thoughts, feelings, intentions, decisions, consent or any action the player did "
    "not state. Describe only what {name} perceives and the direct, visible results of the stated action.\n"
    "- In a fight, opponents and the surroundings act; {name}'s attacks, defence, movement, accepting a hit or "
    "surrendering belong to the player. Stop at the moment {name} must respond.\n"
    "- Keep NPCs active: they talk, decide and act on what they plausibly know, never on secrets they had no way to learn.\n"
    "- End in plain prose at a natural moment for the player to respond. Never add a list of options, a numbered menu, "
    "a 'What do you do next?' question or any interface text: the application shows suggested actions separately.\n"
    "- Do not mention or repeat these rules."
)
OOC_REMINDER = "\n\n(OOC: narrate only the world and the other characters; {name}'s words and choices are mine. No options list.)"

# v4 (UAT phase): same structure as NARRATION_RULES, rewritten for the failure modes seen live with qwen2.5/mistral in a
# second-person story: "you" was not recognised as the protagonist, a length target was filled by narrating the
# protagonist further, and the reply carried the stated action on (travel, follow-ups, time skips).
NARRATION_RULES_V4 = (
    "You narrate the world, the other characters and the consequences of what the player states. The player alone "
    "authors {name}; when you write \"you\", that is {name}.\n"
    "- Never write {name}'s dialogue, thoughts, feelings, intentions, decisions, consent or any action the player did "
    "not state (no \"you say / decide / feel / nod / thank / leave\" of your own). Show what {name} perceives and the "
    "immediate, visible result of the stated action; do not carry it further with travel, follow-up actions or time skips.\n"
    "- In a fight, opponents and the surroundings act; {name}'s attacks, defence, movement, accepting a hit or "
    "surrendering belong to the player. Stop at the moment {name} must respond.\n"
    "- Keep NPCs active: they talk, decide and act on what they plausibly know, never on secrets they had no way to learn.\n"
    "- A length target is a maximum, not a quota: once the other characters have reacted, stop.\n"
    "- Never repeat or paraphrase earlier replies (their descriptions, lines or events): continue from the exact point "
    "where the last one ended.\n"
    "- Never invent a shared past between {name} and anyone (old friends, former classmates, \"you recognise her\") "
    "unless the story or {name}'s profile established it.\n"
    "- End in plain prose at a natural moment for the player to respond. Never add a list of options, a numbered menu, "
    "a 'What do you do next?' question or any interface text: the application shows suggested actions separately. "
    "Earlier replies that did so were mistakes; do not repeat them.\n"
    "- Do not mention or repeat these rules."
)

# v6 (step 1, test report "50 tours"): one voice everywhere. The rules of v4/v5 said "when you write you, that is
# {name}" while the Cinematic style said "never you": Rocinante wrote all 50 replies in the second person. Kurio chose
# the third person (the OOC.AI style). The rules now say it once, and the per-turn note is no longer an "(OOC: ...)"
# line, which the model answered or copied as out-of-character text.
NARRATION_RULES_V6 = (
    "You narrate the world, the other characters and the consequences of what the player states. The player alone "
    "authors {name}. Write in the third person: {name} is \"{name}\" or he/she/they as their profile says, never \"you\".\n"
    "- Never write {name}'s dialogue, thoughts, feelings, intentions, decisions or any action the player did not "
    "state, and never tell the player's action again: start with what it causes. Show what {name} perceives and the "
    "immediate, visible result; do not carry it further with travel, follow-up actions or time skips.\n"
    "- In a fight, opponents and the surroundings act; {name}'s attacks, defence and movement belong to the player. "
    "Stop at the moment {name} must respond.\n"
    "- Keep the other characters active: they talk, decide and act on what they plausibly know.\n"
    "- A length target is a maximum, not a quota. Never repeat or paraphrase earlier replies: continue from the exact "
    "point where the last one ended.\n"
    "- Never invent a shared past between {name} and anyone unless the story or {name}'s profile established it.\n"
    # Kurio (24/11/2026): DeepSeek "invents quite a lot of lore"; the cards and lore are the canon, the rest stays open
    "- The lore and the character cards are the canon. Never invent an important fact about an established character, "
    "place, group or the world's history (family, past, powers, titles, secrets, relationships, events): only small "
    "details (gestures, sounds, food, weather, unnamed extras). When something is not established, keep it vague or "
    "let the character not know, dodge or keep it to herself.\n"
    "- Write story only: no title or header line, no code block, no note to the player, no list of options and no "
    "question such as 'What do you do?'.\n"
    "- When sources disagree: fixed truths and canon facts first, then the player's corrections, the scene now, the "
    "recaps, and last the older messages."
)
AGENCY_NOTE_V6 = ("\n\n<narrator-note>Story only, in the third person. {name}'s words, actions and feelings are the "
                  "player's: write what the world and the other characters do next.</narrator-note>")

# Send-time history hygiene (profile flag, opt-in): a trailing "What would you like to do…?" question, optionally followed
# by its option list, is left out of earlier replies *as sent to the model* so the model stops imitating it. The stored
# transcript is never changed, a plain list without such a question is kept, and the context inspector reports it.
MENU_QUESTION = re.compile(r"^\s*(?:\*\*)?(?:so,?\s+|now,?\s+)?(?:what (?:would|will|do|should|shall) you (?:like to |want to |wish to )?"
                           r"(?:do|say|choose)|what(?:'s| is) your (?:next )?(?:move|choice|decision)|how (?:would|will|do) you "
                           r"(?:like to )?(?:respond|proceed|react))\b[^\n]{0,80}\?(?:\*\*)?\s*$", re.I)
MENU_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+\S")


def strip_trailing_menu(text_: str) -> tuple[str, bool]:
    lines = text_.rstrip().split("\n")
    i = len(lines)
    items = 0
    while i > 0 and (not lines[i - 1].strip() or MENU_ITEM.match(lines[i - 1])):
        items += bool(lines[i - 1].strip())
        i -= 1
    if i == 0 or not MENU_QUESTION.match(lines[i - 1]) or items == 1:
        return text_, False  # no question addressed to the player at the end: not an options menu, keep everything
    kept = "\n".join(lines[: i - 1]).rstrip()
    return (kept, True) if kept.strip() else (text_, False)

# Versioned, opt-in narrator prompt profiles (story setting / app setting ``narrator_prompt_profile``), compared with
# scripts/eval_models.py on the same fixtures. See MODEL_EVALUATION_REPORT.md for the evidence behind the default.
PROMPT_PROFILES: dict[str, dict[str, Any]] = {
    "v1_inline_reminder": {"label": "v1 — rules in core prompt + bracketed reminder after the player's turn",
                           "core_rules": True, "final_rules": False, "reminder": AGENCY_REMINDER},
    "v2_rules_last": {"label": "v2 — operational rules as the last system section, no per-turn text",
                      "core_rules": False, "final_rules": True, "reminder": None},
    "v3_rules_last_ooc": {"label": "v3 — v2 plus a short OOC note after the player's turn",
                          "core_rules": False, "final_rules": True, "reminder": OOC_REMINDER},
    "v4_second_person": {"label": "v4 — v3 with rules naming \"you\" as the protagonist and length as a maximum",
                         "core_rules": False, "final_rules": True, "reminder": OOC_REMINDER, "rules": NARRATION_RULES_V4},
    "v5_history_hygiene": {"label": "v5 — v4 plus leaving trailing option menus out of earlier replies sent to the model",
                           "core_rules": False, "final_rules": True, "reminder": OOC_REMINDER, "rules": NARRATION_RULES_V4,
                           "history_hygiene": True},
    "v6_third_person": {"label": "v6 — one voice (third person), story-only rules, a tagged note instead of (OOC: ...)",
                        "core_rules": False, "final_rules": True, "reminder": AGENCY_NOTE_V6, "rules": NARRATION_RULES_V6,
                        "history_hygiene": True},
}
DEFAULT_PROMPT_PROFILE = "v6_third_person"  # step 1 (test report "50 tours"); v5 before: MODEL_EVALUATION_REPORT.md


def prompt_profile(cfg: dict[str, Any], story_settings: dict[str, Any]) -> str:
    p = story_settings.get("narrator_prompt_profile") or cfg.get("narrator_prompt_profile") or DEFAULT_PROMPT_PROFILE
    return p if p in PROMPT_PROFILES else DEFAULT_PROMPT_PROFILE


SAFETY_MARGIN = 0.9  # the chars/4 estimate can undercount real tokens; never plan closer than this to a hard window
# dropped first -> last when the budget cannot hold the fixed sections plus the minimum recent messages; core rules,
# notes, protagonist, scene/world state, established posts, pinned memories and the narration rules are never dropped
# v1.6: lore first. Encounters were first until the owner's story showed a ~100-token section dropped ahead of a
# ~1,400-token one: 0 of 84 replies ever carried it.
# trimmed in this order when space runs out; the automatic summaries go last (they replace whole scenes)
# v0.5 phase 7.3 "stable" layout: these stay in the system prompt (they rarely change, so its beginning can be cached);
# every other section goes with the player's latest message, under TURN_OPEN (narration rules last)
# phase 2: "known" (characters already met) is not here any more: it changes each time the protagonist meets someone,
# and in the system prompt that made the whole request miss the provider's cache for that turn
STABLE_SECTIONS = {"core", "global_note", "story_note", "avatar", "roles", "recap", "scene_summaries",
                   "portrait_tags", "music_tags", "narration_language", "choice_tags", "info_table"}
# step 1 (test report "50 tours"): the closing label used to be "[The player's turn]"; Rocinante copied it at the top of
# its replies, then wrote the player's action again after it. A pair of tags around the app's notes is not a line a
# narrator wants to write, and the player's message simply follows it.
TURN_OPEN = "<context note=\"written by the app for the narrator; not part of the story\">"
TURN_CLOSE = "</context>"
OPTIONAL_SECTIONS = ("repetition", "lore", "encounters", "events", "facts", "recalled", "character_memory", "recap", "threads",
                     "scene_summaries")
MIN_MESSAGES_HARD = 2  # below the configured minimum only when the model window leaves no other choice


def effective_window(context_limit: int | None, params: dict[str, Any] | None) -> int | None:
    """The real input+output window of a request: the profile's model limit, or Ollama's ``context_size`` (num_ctx) when
    set lower (owner's mistral-nemo profile: limit 1,024,000 but num_ctx 8,192 — Ollama silently cut the prompt's start)."""
    vals = [int(v) for v in (context_limit, (params or {}).get("context_size")) if v]
    return min(vals) if vals else None


def build(db: Session, story: Story, branch: MessageBranch, *, context_limit: int | None = None,
          params: dict[str, Any] | None = None, exclude_message_ids: set[str] | None = None,
          extra_instruction: str | None = None) -> BuiltContext:
    cfg = settings_service.get_all(db)
    ssettings = story.settings_json or {}
    from . import info_table as info_svc
    from . import summaries as summaries_svc
    info_on = info_svc.enabled(db)
    # phase 2 (step 6): with the automatic recaps, the story so far comes from them; the journal and the facts of memory
    # capture are not sent, and the messages a recap covers are not sent word for word (at least the minimum stays)
    recap_on = summaries_svc.recap_mode(db)
    exclusions = set(ssettings.get("context_exclusions") or [])
    budget_cfg = int(ssettings.get("context_budget_tokens") or cfg["context_budget_tokens"])
    reply_tokens = int((params or {}).get("max_tokens") or 0)
    window = effective_window(context_limit, params)
    if window and cfg.get("context_budget_auto", True) and not ssettings.get("context_budget_tokens"):
        # v0.6 (phase 9): use the model's window (it was capped at 10,000 tokens even for a 32k model); the stable layout
        # keeps the start of the request identical, so a local server reuses its cache and a long history stays cheap
        budget_cfg = max(budget_cfg, min(window, settings_service.AUTO_BUDGET_CAP))
    # v1.6.2: with a known window the hard limit below already leaves room for the whole reply, so a high output ceiling does
    # not also come out of the story's context budget. With no known window the reply must fit inside the budget.
    reserve = int(cfg["reserve_output_tokens"]) if window else max(int(cfg["reserve_output_tokens"]), reply_tokens)
    hard_input = int((window - max(reply_tokens, 1)) * SAFETY_MARGIN) if window else None
    budget = min(budget_cfg, window or budget_cfg) - reserve
    if hard_input is not None:
        budget = min(budget, hard_input)
    # v0.5 phase 7.5: sizes are estimated (characters / 4); the provider's real counts correct them per story
    from .usage import ratio_of
    token_ratio = ratio_of(ssettings)
    if token_ratio != 1.0:
        budget = int(budget / token_ratio)
        hard_input = int(hard_input / token_ratio) if hard_input is not None else None
    warnings: list[str] = []

    world = db.get(World, story.world_id) if story.world_id else None
    st_row = state_service.current(db, branch.id)
    state = state_service.normalize(st_row.state_json if st_row else {})
    index = build_index(db, story.world_id, state)
    path = story_tree.path_messages(db, branch.head_message_id)
    path_ids = {m.id for m in path}
    exclude_message_ids = exclude_message_ids or set()
    convo = [m for m in path if m.id not in exclude_message_ids and m.kind != "utility"
             and not (m.role == "assistant" and m.status in ("streaming", "failed") and not m.content)]

    sections: list[Section] = []
    # 1. core prompt
    av = story.avatar_snapshot_json
    if story.active_avatar_id:
        a = db.get(Avatar, story.active_avatar_id)
        if a:
            av = {"name": a.name, "profile": a.profile_json}
    presets = {p["id"]: p for p in settings_service.NARRATION_PRESETS}  # built-in ones always exist...
    presets.update({p["id"]: p for p in cfg["narration_presets"] if isinstance(p, dict) and p.get("id")})  # ...edits win
    preset = presets.get(ssettings.get("preset_id") or "balanced")
    core = (world.system_prompt.strip() if world and world.system_prompt and ssettings.get("use_world_prompt", True)
            else cfg["default_system_prompt"])
    if ssettings.get("system_prompt_override"):
        core = ssettings["system_prompt_override"]
    parts = [core]
    if preset:
        instructions = str(preset.get("instructions") or "").replace("{name}", (av or {}).get("name") or "the protagonist")
        parts.append(f"Style preset — {preset['name']}: {instructions}")
    if ssettings.get("tone"):
        parts.append(f"Desired tone: {ssettings['tone']}")
    if ssettings.get("pacing"):
        parts.append(f"Narrative pacing: {ssettings['pacing']}")
    if ssettings.get("output_length"):
        target = ssettings["output_length"]
        if preset and preset.get("length_in_words"):  # many one-line paragraphs: a paragraph count means nothing here
            target = settings_service.WORD_TARGETS.get(str(target).split(" ")[0].lower(), target)
        parts.append(f"Target response length: {target}")
    if ssettings.get("agency_policy"):
        parts.append(f"Player agency: {ssettings['agency_policy']}")
    cp = ssettings.get("content_prefs") or {}
    cp_lines = [f"{k.replace('_', ' ')}: {v}" for k, v in cp.items() if v not in (None, "", False) and k != "adult_profile_enabled"]
    cp_lines.append("Never depict sexual content involving minors or characters of unclear adult age. Respect the "
                    "provider's usage policies.")
    if cp.get("adult_profile_enabled"):
        cp_lines.append("Adult profile is enabled by the user: romance may be more mature only between clearly adult characters.")
    parts.append("Content preferences — " + "; ".join(cp_lines))
    profile_id = prompt_profile(cfg, ssettings)
    profile = PROMPT_PROFILES[profile_id]
    if profile["core_rules"]:
        parts.append(AGENCY_RULES)
    if extra_instruction:
        parts.append(extra_instruction)
    sections.append(Section("core", "Core instructions", "\n\n".join(parts),
                            [{"type": "prompt", "label": "World narrative prompt" if world and world.system_prompt else "Default narrator prompt"},
                             {"type": "preset", "label": preset["name"] if preset else "none"}]))

    # 2–3. notes
    g = db.scalar(select(UserNote).where(UserNote.scope == "global"))
    if g and g.enabled and g.content.strip() and not ssettings.get("disable_global_note"):
        sections.append(Section("global_note", "Global user note", g.content.strip(), [{"type": "note", "id": g.id, "label": "Global note (active)"}]))
    elif g and g.content.strip():
        warnings.append("Global user note exists but is disabled" + (" for this story." if ssettings.get("disable_global_note") else "."))
    sn = db.scalar(select(UserNote).where(UserNote.scope == "story", UserNote.story_id == story.id))
    if sn and sn.enabled and sn.content.strip():
        sections.append(Section("story_note", "Story note from the player (overrides lore)",
                                sn.content.strip(), [{"type": "note", "id": sn.id, "label": "Story note (active)"}]))

    # 4. avatar + player state (av is read before the core prompt: a preset may name the protagonist)
    from .world_state import calendar_of
    player_text, scene_text = render_state(state, index, calendar_of(db, story.world_id)["year_label"])
    if av:  # v0.5: the profile (stable) and the current state (changes every turn) are separate sections
        sections.append(Section("avatar", "Protagonist (played by the player)",
                                render_avatar(av), [{"type": "avatar", "label": av.get("name") or "Avatar"}]))
    if player_text:
        sections.append(Section("player_state", "Protagonist's current state", player_text,
                                [{"type": "state", "label": "Player state"}]))

    # 5. scene + cast lore summaries
    present = list((state.get("scene") or {}).get("present") or [])
    recent_text = " ".join(m.content for m in convo[-4:])
    mentioned = index.find_mentions(recent_text)
    focus_entities = list(dict.fromkeys(present + mentioned))
    from . import canon as canon_svc
    canon = canon_svc.facts(db, story.world_id, index)
    scene_now = state.get("scene") or {}
    active_class = canon_svc.detect_class(f"{scene_now.get('location') or ''} {recent_text}", canon, present)
    # v1.6: appearance rides with the cast, because the full lore entry is the first thing trimmed (54 of 84 replies in the
    # owner's story) and a character written without it gets someone else's hair. The usual class joins so a student who
    # is first noticed in this reply is described correctly too.
    classmates = [s["character_id"] for s in active_class["students"] if s["character_id"]] if active_class else []
    cast_lines = []
    from . import roles as roles_svc
    registry = roles_svc.build_registry(db, story.world_id, index)
    post_of = {}
    for r in registry["roles"]:
        post_of.setdefault(r["character_id"], r["title"])
    carded: set[str] = set()
    # Kurio (24/11): the characters in the scene get their whole record (play card); those only named, the one line.
    # Without a "present" list yet, the ones named in the last exchange count as present. At most 5 play cards.
    on_stage = [c for c in present if c in index.entities] or \
        index.find_mentions(" ".join(m.content for m in convo[-2:]))
    on_stage = [c for c in dict.fromkeys(on_stage) if index.entities[c].category == "character"][:5]
    char_names = {cid: e.name for cid, e in index.entities.items() if e.category == "character"}
    for cid in dict.fromkeys([*on_stage, *focus_entities[:8], *classmates]):
        le = db.scalar(select(LoreEntity).where(LoreEntity.world_id == story.world_id, LoreEntity.entity_id == cid)) if story.world_id else None
        if le and le.category == "character":
            cast_lines.append(character_play_card(le, post_of.get(cid), char_names) if cid in on_stage
                              else character_card(le, post_of.get(cid)))
            carded.add(cid)
    # lore background between the characters in focus (v1.4): initial relationships, below the story-evolved values
    from .relationships import lore_relationships
    focus_set = set(focus_entities[:8])
    lore_rel = [f"- {r['source_name']} → {r['target_name']}: {r['type']}" for r in lore_relationships(db, story.world_id, focus_set)
                if r["source_id"] in focus_set and r["target_id"] in focus_set
               and r["source_id"] not in on_stage][:8]  # a play card already lists its ties
    sc_text = "\n".join(x for x in [scene_text, ("Characters here or named (cards are canon: keep each one's gender, "
                                                 "role and looks; play each one by her card: her voice, aims, ties "
                                                 "and what she never does):\n" + "\n".join(cast_lines)) if cast_lines else "",
                                    ("Lore background between these characters (initial; story-evolved values above take "
                                     "precedence):\n" + "\n".join(lore_rel)) if lore_rel else ""] if x)
    if sc_text:
        sections.append(Section("scene", "Scene now", sc_text,
                                [{"type": "entity", "id": c, "label": index.name(c)} for c in focus_entities[:8]]))
    # 5b. established posts and closed groups (v1.4): lore holds them, the narrator invented replacements without them.
    # Narrator-only knowledge: building context never records a discovery for the protagonist.
    roles_text = roles_svc.render_block(registry, index, present)
    if roles_text:
        sections.append(Section("roles", "Established characters and posts", roles_text,
                                [{"type": "role", "id": r["role_id"], "label": f"{r['title']}: {r['character_name']}"}
                                 for r in registry["roles"]]))
    # 5c. v1.5: who the protagonist already knows (read-only use of discoveries — the v1.4 posts block alone said "may
    # not know these people yet", and the Headmaster stayed nameless long after the protagonist had met Emily)
    from . import discovery, encounters, scene_cast
    known = {cid: r for cid, r in discovery.roster(db, story, branch).items()
             if r.status in ("encountered", "known") and cid in index.entities}
    if known:
        posts = {r["character_id"]: r["title"] for r in registry["roles"]}
        sections.append(Section("known", "Characters the protagonist has already met",
                                "Use their names naturally when they appear (no need to repeat them every sentence): "
                                + "; ".join(f"{index.name(c)}" + (f" ({posts[c]})" if c in posts else "")
                                            + (" — introduced" if r.status == "known" else " — seen")
                                            for c, r in known.items()) + ".",
                                [{"type": "entity", "id": c, "label": index.name(c)} for c in known]))
    # 5d. v1.5: structured canon (kinship, family branches, class rosters) relevant to this scene
    canon_text = canon_svc.render_block(canon, index, set(focus_entities[:8]), active_class)
    if canon_text:
        sections.append(Section("canon", "Canon facts (never contradict)", canon_text,
                                [{"type": "canon_fact", "label": active_class["class_id"] if active_class else "family ties"}]))
    # 5e. v1.6: a group scene is told who is in the room and who has been quiet (never trimmed; a few lines at most)
    group_text = scene_cast.group_scene(db, state, index, convo, active_class, set(known), recent_text)
    if group_text:
        sections.append(Section("group_scene", "Group scene (natural attention, no taking turns)", group_text,
                                [{"type": "scene", "label": active_class["class_id"] if active_class else "several characters"}]))
    # 5f. v1.5: optional encounter hints (established characters plausible here; never a script)
    last_user = next((m.content for m in reversed(convo) if m.role == "user"), "")
    enc = encounters.candidates(db, story.world_id, index, state, convo, canon, set(known), player_turn=last_user,
                                setup=str(ssettings.get("starter_blueprint") or ""))
    enc_text = encounters.render(enc, index)
    if enc_text:
        sections.append(Section("encounters", "Possible encounters (optional)", enc_text,
                                [{"type": "entity", "id": h["character_id"], "label": h["name"]} for h in enc["hints"]]))

    # 6–7. memories, events, facts
    facts = [f for f in visible_facts(db, story, branch, path_ids) if f.status in ("active", "disputed") and f"fact:{f.id}" not in exclusions]
    pinned = [f for f in facts if f.pinned]
    if pinned:
        sections.append(Section("pinned", "Pinned memories (established for this campaign)",
                                "\n".join(render_fact(f, index) for f in pinned),
                                [{"type": "fact", "id": f.id, "label": f.content[:80]} for f in pinned]))
    fts_q = fts_query(recent_text)
    fts_fact_ids: set[str] = set()
    fts_event_ids: set[str] = set()
    if fts_q:
        try:
            fts_fact_ids = {r[0] for r in db.execute(text("SELECT id FROM facts_fts WHERE facts_fts MATCH :q AND story_id = :s LIMIT 40"), {"q": fts_q, "s": story.id})}
            fts_event_ids = {r[0] for r in db.execute(text("SELECT id FROM events_fts WHERE events_fts MATCH :q AND story_id = :s LIMIT 40"), {"q": fts_q, "s": story.id})}
        except Exception:
            warnings.append("Full-text search failed for this query; falling back to entity/recency retrieval.")
    focus = set(focus_entities)

    def score_fact(f: EntityFact) -> float:
        return (3 if f.subject_entity_id in focus else 0) + (2 if f.id in fts_fact_ids else 0) + f.importance * 0.5 + (1 if f.fact_kind == "secret" else 0)

    rel_facts = sorted((f for f in facts if not f.pinned and (f.subject_entity_id in focus or f.id in fts_fact_ids or f.importance >= 4)),
                       key=score_fact, reverse=True)
    events = [e for e in visible_events(db, story, branch, path_ids)
              if e.verification_status not in ("rejected", "candidate") and not e.superseded_by_event_id and f"event:{e.id}" not in exclusions]
    events.sort(key=lambda e: (e.branch_sequence, e.created_at))

    def score_event(e: StoryEvent) -> float:
        overlap = len(focus & set(e.entity_ids_json or []))
        return overlap * 2 + (2 if e.id in fts_event_ids else 0) + e.importance * 0.6 + (2 if e.pinned else 0)

    digest = events[-6:]
    relevant = sorted((e for e in events if e not in digest), key=score_event, reverse=True)[:8]
    ev_items, ev_lines = [], []
    for e in sorted(set(digest) | set(relevant), key=lambda e: (e.branch_sequence, e.created_at)):
        tag = "" if e.evidence_kind in ("witnessed", "confirmed") else f" [{e.evidence_kind}]"
        ev_lines.append(f"- #{e.branch_sequence} {e.title}: {e.summary}{tag}" + (" (STALE: source message was edited)" if e.stale else ""))
        ev_items.append({"type": "event", "id": e.id, "label": e.title})
    mem_budget = max(400, int(budget * 0.18))
    fact_lines, fact_items, used = [], [], 0
    for f in rel_facts:
        line = render_fact(f, index)
        if used + est_tokens(line) > mem_budget:
            break
        fact_lines.append(line)
        fact_items.append({"type": "fact", "id": f.id, "label": f.content[:80]})
        used += est_tokens(line)
    if ev_lines and not recap_on:
        sections.append(Section("events", "Story so far (journal)",
                                "\n".join(ev_lines), ev_items))
    if fact_lines and not recap_on:
        sections.append(Section("facts", "Relevant facts and memories (respect who knows what)", "\n".join(fact_lines), fact_items))
    contradictions = [f for f in facts if f.contradicts_fact_ids_json]
    if contradictions:
        warnings.append(f"{len(contradictions)} fact(s) are marked as contradicting other records — review them in Journal & Memory.")

    # 8. lore + local canon
    lore_lines, lore_items = [], []
    if story.world_id:
        # v0.6: capped, so a bigger window holds more of the story itself rather than more reference lore
        lore_budget = max(500, min(int(budget * 0.2), LORE_BUDGET_MAX))
        used = 0
        pins = list(ssettings.get("pinned_lore_ids") or [])
        chunks: list[LoreChunk] = [c for c in (db.get(LoreChunk, i) for i in pins) if c]
        if focus:
            chunks += list(db.scalars(select(LoreChunk).where(LoreChunk.world_id == story.world_id, LoreChunk.entity_id.in_(focus))))
        if fts_q:
            try:
                ids = [r[0] for r in db.execute(text("SELECT id FROM lore_fts WHERE lore_fts MATCH :q AND world_id = :w ORDER BY rank LIMIT 6"),
                                                {"q": fts_q, "w": story.world_id})]
                # phase 2: a word match brings places, groups and terms, never a character the scene does not have
                # (the test of 19/11 sent Anastasia twice and Rena at a breakfast with Lilia alone)
                found = [c for c in (db.get(LoreChunk, i) for i in ids) if c]
                chunks += [c for c in found if not (c.entity_id and c.entity_id in index.entities
                                                    and index.entities[c.entity_id].category == "character")
                           and not (c.category == "premise" or c.title.lower().startswith("premise"))][:2]
            except Exception:
                pass
        seen = set()
        canon_rows = list(db.scalars(select(LocalCanon).where(LocalCanon.status == "approved",
                                                              or_(LocalCanon.story_id == story.id, LocalCanon.scope.in_(("local", "global_draft"))),
                                                              or_(LocalCanon.world_id == story.world_id, LocalCanon.world_id.is_(None)))))
        overridden = {lc.overrides_entity_id for lc in canon_rows if lc.overrides_entity_id}
        # v0.5 phase 7.3: a character's full lore entry is sent when they come into the scene; while they stay (already
        # named in the recent messages before this exchange) the cast notes above (traits, looks) are their short card
        short_cards = cfg.get("lore_short_cards", True) is not False
        staying = set(index.find_mentions(" ".join(m.content for m in convo[-12:-2]))) if short_cards else set()
        # Kurio (24/11/2026): less noise. One record per name (a pack can describe the same thing as a faction, a club
        # and a glossary term: the Blue Knights came three times), and calendar dates only when the last exchange
        # is about dates, exams or events (a word match sent "final evaluations" to a greeting in a hallway).
        titles: set[str] = set()
        about_dates = bool(SCHEDULE_WORDS.search(" ".join(m.content for m in convo[-2:])))
        for c in chunks:
            if c.id in seen or f"lore:{c.id}" in exclusions:
                continue
            seen.add(c.id)
            if c.id not in pins and c.title.casefold() in titles:
                lore_items.append({"type": "lore", "id": c.id, "label": c.title, "included": False, "reason": "same name"})
                continue
            if c.id not in pins and c.category == "calendar" and not about_dates:
                lore_items.append({"type": "lore", "id": c.id, "label": c.title, "included": False,
                                   "reason": "calendar, not about dates"})
                continue
            if c.entity_id in carded and c.id not in pins and (short_cards or c.entity_id in staying):
                lore_items.append({"type": "lore", "id": c.id, "label": c.title, "included": False,
                                   "reason": "short card"})
                continue
            if c.entity_id in overridden and c.id not in pins:
                continue
            body = compact_record(c.content)
            body = body if len(body) < 2400 else body[:2400] + " …"
            t = est_tokens(body)
            if used + t > lore_budget and c.id not in pins:
                lore_items.append({"type": "lore", "id": c.id, "label": c.title, "included": False, "reason": "lore budget"})
                continue
            lore_lines.append(f"## {c.title}\n{body}")
            titles.add(c.title.casefold())
            lore_items.append({"type": "lore", "id": c.id, "label": c.title, "confidence": c.confidence, "canon_status": c.canon_status})
            used += t
        for lc in canon_rows:
            if f"canon:{lc.id}" in exclusions:
                continue
            if lc.entity_ids_json and not (set(lc.entity_ids_json) & focus) and lc.overrides_entity_id not in focus and len(canon_rows) > 12:
                continue
            if lc.overrides_entity_id and (lc.overrides_entity_id in carded or lc.overrides_entity_id not in focus):
                continue  # phase 2: only for what the scene has, and a character's short card is enough
            lore_lines.append(f"## {lc.title} (campaign canon)\n{compact_record(lc.content)}")
            lore_items.append({"type": "canon", "id": lc.id, "label": lc.title})
    if lore_lines:
        sections.append(Section("lore", "Lore", "\n\n".join(lore_lines), lore_items))

    # 8b. narrator-only secrets of the records in play (pack "hidden" fields; never shown to the player)
    secret_texts: list[str] = []
    hidden = ((world.data_json or {}).get("hidden") or {}) if world else {}
    if hidden:
        in_play = set(focus) | {i["id"] for i in lore_items if i.get("type") == "lore" and i.get("included", True)}
        in_play |= {c.entity_id for c in (db.get(LoreChunk, i) for i in in_play) if c is not None and c.entity_id}
        names = {e.entity_id: e.name for e in db.scalars(select(LoreEntity).where(LoreEntity.world_id == story.world_id))}
        secret_lines = [f"- {names.get(key.split(':', 1)[1], key.split(':', 1)[1])}: {note}"
                        for key, notes in hidden.items() if key.split(":", 1)[1] in in_play for note in notes]
        if secret_lines:
            text_ = ("These facts are TRUE but SECRET. The player must not learn them unless the story reveals them "
                     "through events, clues or a character's own choice. Never state them in narration, never hint at "
                     "them out of nowhere, and never record them as something the protagonist knows. A character knows "
                     "a secret only if it is their own or they would plausibly know it. Let secrets quietly shape "
                     "motives, behaviour and consequences.\n" + "\n".join(secret_lines))
            secret_texts.append(text_)
            sections.append(Section("secrets", "Narrator-only secrets (hidden from the player)", text_,
                                    [{"type": "secret", "label": f"{len(secret_lines)} hidden note(s)"}]))

    # 9. rolling recap
    recap = db.scalar(select(Recap).where(Recap.branch_id == branch.id, Recap.status == "active", Recap.kind == "rolling")
                      .order_by(Recap.version.desc()).limit(1))
    if recap:
        sections.append(Section("recap", f"Story so far (rolling recap v{recap.version}, covers messages up to #{recap.end_seq})",
                                recap.content, [{"type": "recap", "id": recap.id, "label": f"Recap v{recap.version}"}]))
    # 9b. v0.5 phase 7: the automatic memory (services/summaries.py), in layers: the story so far, chapters, then the
    # scenes no longer sent word for word. Prepared before the recent messages are picked (so their size counts), then
    # narrowed to what was really left out.
    from . import summaries as summaries_svc
    recap_end = recap.end_seq if recap and recap.end_seq is not None else -1
    summ_rows = [r for r in summaries_svc.visible(db, story.id, path_ids, ("story", "chapter", "scene"))
                 if r.end_seq > recap_end]
    summ_section = None
    if summ_rows:
        summ_section = Section("scene_summaries", "Story so far (recaps, oldest first; the recent messages follow)"
                               if recap_on else "Earlier in the story (automatic memory of what is no longer shown word "
                                                "for word; oldest first)", "", [])
        sections.append(summ_section)

    def fill_summaries(before_seq: int | None) -> None:
        """The story so far always; then the newest chapters and scenes within their share of the budget, shown oldest
        first; only parts that start before the oldest message sent word for word."""
        if summ_section is None:
            return
        cap, used_, keep = max(600, int(budget * 0.15)), 0, []
        for r in [r for r in summ_rows if r.level == "story"][-1:]:
            keep.append((r, f"- {'Global recap' if recap_on else 'Story so far'} (#{r.start_seq}–#{r.end_seq}): {r.content}"))
            used_ += est_tokens(keep[-1][1])
        for r in reversed([r for r in summ_rows if r.level != "story"]):
            if before_seq is not None and r.start_seq >= before_seq:
                continue
            line = f"- {'Chapter' if r.level == 'chapter' else 'Recap' if recap_on else 'Scene'} #{r.start_seq}–#{r.end_seq}: {r.content}"
            if keep and used_ + est_tokens(line) > cap:
                break
            keep.append((r, line))
            used_ += est_tokens(line)
        keep.sort(key=lambda x: (x[0].start_seq, x[0].end_seq))
        summ_section.text = "\n".join(line for _, line in keep)
        summ_section.items = [{"type": "summary", "id": r.id, "label": f"{r.level} #{r.start_seq}–#{r.end_seq}: "
                                                                       f"{r.content[:60]}"} for r, _ in keep]

    # 9c. older scenes that come back (names or places of the recent turns found in a merged scene: its detail)
    all_scenes = summaries_svc.scenes(db, story.id, path_ids)
    if fts_q and all_scenes:
        absorbed = {r.id: r for r in all_scenes if r.status == "superseded"}
        try:
            hits = [r[0] for r in db.execute(text("SELECT id FROM summaries_fts WHERE summaries_fts MATCH :q AND "
                                                  "story_id = :s ORDER BY rank LIMIT 20"), {"q": fts_q, "s": story.id})]
        except Exception:
            hits = []
        recalled = [absorbed[i] for i in hits if i in absorbed][:2]
        if recalled:
            sections.append(Section("recalled", "Recalled details of older scenes (they may matter now)",
                                    "\n".join(f"- Scene #{r.start_seq}–#{r.end_seq}: {r.content}" for r in recalled),
                                    [{"type": "summary", "id": r.id, "label": f"recalled #{r.start_seq}–#{r.end_seq}"}
                                     for r in recalled]))
    # 9d. what happened before with the characters in focus, and the threads still open
    char_mem = summaries_svc.character_memory(all_scenes, list(focus_entities[:8]), recent_text)
    if char_mem:
        sections.append(Section("character_memory", "Memory of these characters (what happened with them before, newest "
                                                    "first)",
                                "\n".join(f"- {name}: " + " | ".join(lines) for name, lines in char_mem),
                                [{"type": "memory", "label": name} for name, _ in char_mem]))
    threads = summaries_svc.open_threads(all_scenes, summaries_svc.closed_by_player(story))[-summaries_svc.MAX_THREADS:]
    if threads:
        sections.append(Section("threads", "Open threads (promises, debts, quests and mysteries still pending: keep them "
                                           "in mind, never force them)",
                                "\n".join(f"- {t['text']} (since #{t['seq']})" for t in threads),
                                [{"type": "thread", "label": t["text"][:80]} for t in threads]))
    # 9d. v0.6 planned events (pack.json "events"): at most one due event, decided by the author, played the narrator's way
    planned = None
    pack = world_pack.of(db, story.world_id) if story.world_id else {}
    if story_events.events_of(pack) or story_events.choices_of(pack):
        prot = (av or {}).get("name") or "the protagonist"
        prog = story_events.progress(pack, path)
        rule = story_events.choice_rule(pack, prog["choices"], prot)
        if rule:
            sections.append(Section("choice_tags", "Player choices (marks removed before the player reads)", rule,
                                    [{"type": "prompt", "label": "Choice marks"}]))
        from .world_state import calendar_of as _calendar_of
        d = story_events.due(pack, prog, state.get("scene") or {}, _calendar_of(db, story.world_id)["year_start"])
        if d:
            ev = d["event"]
            planned = {"id": ev["id"], "firm": d["firm"]}
            sections.append(Section("planned_event", "Planned event (decided by the story's author; play it your way)",
                                    story_events.narrator_note(d, pack, index.name, prot),
                                    [{"type": "event", "id": ev["id"], "label": story_events.text_of(ev.get("title"))}]))

    # 9e. v0.5 phase 7.6: phrasing the narrator keeps reusing (found without any model call)
    if cfg.get("anti_repetition", True) is not False:
        from . import continuity
        rep = continuity.repetition_block(convo)
        if rep:
            sections.append(Section("repetition", "Vary your wording", rep, [{"type": "prompt", "label": "Repeated phrasing"}]))

    # 10. recent messages within budget (the final rules section is sent too, so it counts against the budget)
    pname = (av or {}).get("name") or "the protagonist"
    rules = (Section("narration_rules", "Narration rules (highest priority; they override anything above)",
                     profile.get("rules", NARRATION_RULES).format(name=pname), [{"type": "prompt", "label": profile["label"]}])
             if profile["final_rules"] else None)
    min_recent = int(cfg.get("recent_messages_min") or 6)
    # v1.7 portrait tags: the narrator marks who speaks and how ([Selphina:3]); the app shows the portrait at once
    tags_text = portrait_tags.instruction(pname) if story.world_id and cfg.get("portrait_tags_enabled", True) else ""
    # v0.5 story language: the narrator writes in it; tags, names and the analysis JSON stay as they are
    lang_code = narration_language.of(cfg, ssettings)
    lang_text = narration_language.instruction(lang_code)
    # v0.6: earlier replies show the tags of the speakers the app found, even when the narrator wrote none
    tags_on = bool(tags_text)
    history_tags = portrait_tags.history_fallback(db, convo, index.name) if tags_on else {}
    candidates = []  # newest first: (message, body as sent, tokens, trailing menu left out)
    for m in reversed(convo):
        body, cut = message_for_model(m, history_tags.get(m.id), portraits=tags_on, info=info_on), False
        if profile.get("history_hygiene") and m.role == "assistant":
            body, cut = strip_trailing_menu(body)
        candidates.append((m, body, est_tokens(body) + 4, cut))

    def fixed_tokens() -> int:
        # measure the system prompt exactly as it is sent (section headings included), not just the section bodies
        return est_tokens("\n\n".join(f"# {s.title}\n{s.text}" for s in [*sections, *([rules] if rules else [])])) + 8 \
            + (est_tokens(tags_text) + 12 if tags_text else 0) + (est_tokens(lang_text) + 10 if lang_text else 0)

    def pick(fixed: int) -> tuple[list[Any], int]:
        """Newest first until the budget is used; the minimum recent messages may go over the budget but never over the
        hard window (then at least MIN_MESSAGES_HARD, and always the latest turn)."""
        out, used = [], 0
        for i, (m, body, t, cut) in enumerate(candidates):
            over_soft = fixed + used + t > budget
            over_hard = hard_input is not None and fixed + used + t > hard_input
            if i and ((over_soft and i >= min_recent) or (over_hard and i >= MIN_MESSAGES_HARD)):
                break
            out.append((m, body, t, cut))
            used += t
        return out, used

    # summaries only for scenes older than the minimum recent messages (always sent when the window allows)
    surely_sent = candidates[min(min_recent, len(candidates)) - 1][0].seq if candidates else None
    fill_summaries(surely_sent)
    if summ_section is not None and not summ_section.text:
        sections.remove(summ_section)
        summ_section = None
    # priority trimming (v1.4): retrieved lore, then the event digest, facts and recap give way before recent messages
    trimmed: list[str] = []
    fixed = fixed_tokens()
    picked, used = pick(fixed)
    want = min(min_recent, len(candidates))
    # v1.5: also when the window leaves room for fewer than the minimum recent messages (optional sections yield first)
    while (len(picked) < want or (fixed + used > budget and len(picked) <= want)
           or (hard_input is not None and fixed + used > hard_input)):
        drop = next((s for k in OPTIONAL_SECTIONS for s in sections if s.key == k), None)
        if drop is None:
            break
        sections.remove(drop)
        trimmed.append(drop.title.split(" (")[0].split(" —")[0])
        fixed = fixed_tokens()
        picked, used = pick(fixed)
    if trimmed:
        warnings.append(f"To fit at least the {want} most recent messages, these optional sections were left out this "
                        f"time: {', '.join(trimmed)} ({len(picked)} recent messages sent).")
    layout = cfg.get("context_layout") or "stable"
    recap_cut = False
    if recap_on and summ_rows:
        # phase 2 (step 6): what a recap covers leaves the history in one block of N replies (the beginning of the
        # request then stays the same for N turns: cache), the newest messages always stay
        covered = summaries_svc.covered_ids(summ_rows)
        keep = [x for x in picked if x[0].id not in covered]
        if len(keep) < want:
            keep = picked[:want]
        if len(keep) < len(picked):
            picked, used, recap_cut = keep, sum(t for _, _, t, _ in keep), True
    if layout == "stable" and not recap_cut and len(picked) > want and len(picked) < len(candidates):
        # v0.5 phase 7.3: old messages leave in steps, at the end of a memory summary (or every 8 messages), so the
        # beginning of the request stays identical for several turns (prompt caches: LM Studio, DeepSeek, Claude...)
        pos = {m.id: i for i, m in enumerate(convo)}
        oldest = min(pos[m.id] for m, *_ in picked if m.id in pos) if picked else 0
        ends = {r.end_seq for r in summ_rows} if summ_rows else set()
        steps = [i for i, m in enumerate(convo) if i > 0 and convo[i - 1].seq in ends] or \
                [i for i in range(len(convo)) if i % 8 == 0]
        # where the previous request of this branch started (services/turns.py): kept while it still fits
        prev_seq = ((ssettings.get("window_starts") or {}).get(branch.id))
        prev_i = next((i for i, m in enumerate(convo) if m.seq == prev_seq), None)
        if prev_i is not None and prev_i >= oldest and len(convo) - prev_i >= want:
            step = prev_i
        else:  # a forced move: to a boundary that leaves the minimum, else as far as the minimum allows (then it grows)
            step = next((i for i in steps if i >= oldest and len(convo) - i >= want), None)
            if step is None:
                step = len(convo) - want
                if convo[step].role != "user" and step - 1 >= oldest:
                    step -= 1  # start on the player's turn
                step = max(step, oldest)
        if step is not None and len(convo) - step >= want:
            picked = [x for x in picked if pos.get(x[0].id, 0) >= step]
            used = sum(t for _, _, t, _ in picked)
    chosen = [m for m, *_ in reversed(picked)]
    if summ_section is not None and summ_section in sections and chosen:
        fill_summaries(chosen[0].seq)  # only what was really left out (frees the room of scenes still shown)
        if not summ_section.text:
            sections.remove(summ_section)
        fixed = fixed_tokens()
    remaining = budget - fixed
    bodies = {m.id: body for m, body, *_ in picked}
    menus_omitted = sum(cut for *_, cut in picked)
    if menus_omitted:
        warnings.append(f"History hygiene: a trailing options menu was left out of {menus_omitted} earlier repl"
                        f"{'y' if menus_omitted == 1 else 'ies'} sent to the model (the saved story is unchanged).")
    omitted = len(convo) - len(chosen)
    if omitted:
        sent_ids = {m.id for m in chosen}
        summarised = summaries_svc.covered_ids([r for r in summ_rows if summ_section is not None and summ_section in sections
                                                and any(i.get("id") == r.id for i in summ_section.items)])
        gaps = [m for m in convo if m.id not in sent_ids and m.seq > recap_end and m.id not in summarised
                and m.kind in ("story", "ooc")]
        if gaps:
            warnings.append(f"{len(gaps)} older message(s) no longer fit the context budget and have no summary yet "
                            "(automatic summaries catch up after the next replies; /recap makes one now).")
    if used > remaining and (hard_input is None or fixed + used <= hard_input):
        warnings.append(f"The {len(chosen)} most recent messages go over the budget (≈{fixed + used} of {budget} tokens); "
                        "the model window still has room.")
    if hard_input is not None and fixed + used > hard_input:
        warnings.append(f"Even the essential sections and the latest turn (≈{fixed + used} tokens) are close to or over the "
                        f"model window ({window}); the model may cut the beginning of the prompt. Shorten notes/lore or "
                        "raise the model's context size.")
    msgs = [ChatMessage(m.role if m.role in ("user", "assistant") else "user", bodies[m.id]) for m in chosen]
    # (not after the opening request: its blueprint is the instruction, and a reminder after it was copied into the
    # opening scene by small models)
    opening = (chosen[-1].command_json or {}).get("name") == "start" if chosen else False
    if profile["reminder"] and msgs and msgs[-1].role == "user" and chosen[-1].kind == "story" and not opening:
        # long system prompts and older replies that broke the rule get ignored by smaller models; a short per-request
        # reminder next to the player's turn helps. Sent only, never stored in the transcript.
        reminder = profile["reminder"].format(name=pname)
        if info_svc.enabled(db):
            reminder = (reminder.replace("</narrator-note>", info_svc.REMINDER + "</narrator-note>")
                        if "</narrator-note>" in reminder else reminder + info_svc.REMINDER)
        msgs[-1] = ChatMessage("user", msgs[-1].content + reminder)
    if tags_text and msgs and msgs[-1].role == "user" and chosen[-1].kind == "story" and not opening:
        # v0.6: the portrait-tag note sits right next to the player's message, with a character of this scene as the
        # example (small models follow a per-turn note far better than a rule at the top of the system prompt)
        msgs[-1] = ChatMessage("user", msgs[-1].content + portrait_tags.reminder(_tag_example(index, state, convo, pname),
                                                                                 lang_code))
    if lang_text and msgs and msgs[-1].role == "user" and chosen[-1].kind == "story" and not opening:
        msgs[-1] = ChatMessage("user", msgs[-1].content + narration_language.reminder(lang_code))  # the language note stays last
    if info_on:
        sections.append(Section("info_table", "Info block (read by the app, never part of the story)",
                                info_svc.INSTRUCTION.replace("{name}", pname), [{"type": "prompt", "label": "Info block"}]))
    if tags_text:
        sections.append(Section("portrait_tags", "Portrait tags (removed before the player reads)", tags_text,
                                [{"type": "prompt", "label": "Portrait tags"}]))
    # v0.5 background music: the narrator marks mood / place changes with [Music:tag] (services/music.py)
    music_text = (music_svc.instruction(music_svc.folder())
                  if world is not None and music_svc.pack_settings(world)["enabled"] else "")
    if music_text:
        sections.append(Section("music_tags", "Music tags (removed before the player reads)", music_text,
                                [{"type": "prompt", "label": "Music tags"}]))
    if lang_text:
        sections.append(Section("narration_language", f"Story language: {narration_language.LANGUAGES[lang_code]}", lang_text,
                                [{"type": "prompt", "label": f"Narration in {narration_language.LANGUAGES[lang_code]}"}]))
    if rules:
        sections.append(rules)

    turn_context = ""
    if layout == "stable":
        stable = [s for s in sections if s.key in STABLE_SECTIONS]
        per_turn = [s for s in sections if s.key not in STABLE_SECTIONS]
        if per_turn and msgs and msgs[-1].role == "user" and not opening:
            turn_context = "\n\n".join(f"## {s.title}\n{s.text}" for s in per_turn)
            msgs[-1] = ChatMessage("user", f"{TURN_OPEN}\n\n{turn_context}\n\n{TURN_CLOSE}\n{msgs[-1].content}")
            sections = stable + per_turn  # the manifest lists them in sending order
            system = "\n\n".join(f"# {s.title}\n{s.text}" for s in stable)
        else:
            system = "\n\n".join(f"# {s.title}\n{s.text}" for s in stable + per_turn)
    else:
        system = "\n\n".join(f"# {s.title}\n{s.text}" for s in sections)
    placement = {s.key: ("turn" if turn_context and s.key not in STABLE_SECTIONS else "system") for s in sections}
    total = est_tokens(system) + est_tokens(turn_context) + used
    ratio = total / budget if budget > 0 else 1
    # recent messages fill whatever the fixed sections leave, so a total near 100 % is normal and not a warning (the
    # owner saw "≈96 %" every turn); what deserves one is fixed content crowding out the conversation
    fixed_ratio = fixed / budget if budget > 0 else 1
    if fixed_ratio >= float(cfg["context_warning_ratio"]):
        warnings.append(f"Instructions, notes, lore and memories alone use ≈{int(fixed_ratio * 100)}% of the budget, leaving "
                        "little room for recent messages.")
    manifest = {
        "approximate": True,
        "budget_tokens": budget, "reserved_output_tokens": reserve, "total_tokens": total, "ratio": round(ratio, 3),
        "fixed_tokens": fixed, "message_tokens": used, "reply_max_tokens": reply_tokens or None,
        "effective_window": window, "hard_input_limit": hard_input, "trimmed_sections": trimmed,
        "strategy": ("Fixed sections first (core rules, notes, protagonist, scene and world state, established posts, "
                     "pinned memories, narration rules — never dropped); retrieved lore, events, facts and recap are left "
                     f"out in that order if needed; then recent messages newest first, at least {min_recent} unless the "
                     "model window forbids it."),
        "layout": layout,
        "token_ratio": token_ratio,
        "first_sent_seq": chosen[0].seq if chosen else None,
        "sections": [{"key": s.key, "title": s.title, "tokens": s.tokens, "items": s.items, "placement": placement[s.key]}
                     for s in sections]
                    + [{"key": "messages", "title": "Recent messages", "tokens": used,
                        "items": [{"type": "message", "id": m.id, "label": f"#{m.seq} {m.role}: {m.content[:60]}"} for m in chosen]}],
        "omitted_messages": omitted,
        "warnings": warnings,
        "precedence": "current-turn user instruction > story note/state > global note > imported baseline lore",
        "prompt_profile": profile_id,
        "history_menus_omitted": menus_omitted,
        # model window (when known) and the separate scene-analysis request, which does not use this budget
        "model_context_limit": context_limit,
        "analysis_output_budget": _analysis_budget(),
        # v0.6: the planned event asked for in this request (services/story_events.py counts the reminders from it)
        "planned_event": planned,
    }
    return BuiltContext(system=system, messages=msgs, manifest=manifest, secrets=secret_texts, turn_context=turn_context)


def _analysis_budget() -> int:
    from .turn_analysis import ANALYSIS_MAX_TOKENS  # lazy: avoids an import cycle
    return ANALYSIS_MAX_TOKENS


def _tag_example(index, state: dict[str, Any], convo: list[Message], pname: str) -> str:
    """A character of the current scene for the portrait-tag example: the last speaker, else someone present."""
    def ok(cid: str | None) -> bool:
        return bool(cid) and cid in index.entities and index.entities[cid].category == "character" \
            and index.name(cid).casefold() != (pname or "").casefold()
    last = next((m.speaker_character_id for m in reversed(convo) if m.role == "assistant" and ok(m.speaker_character_id)), None)
    cid = last or next((c for c in (state.get("scene") or {}).get("present") or [] if ok(c)), None)
    return index.name(cid).split(" ")[0] if cid else "Name"


def message_for_model(m: Message, history_tags: list[dict[str, Any]] | None = None, *, portraits: bool = True,
                      info: bool = False) -> str:
    content = m.content
    if m.role == "user" and m.command_json and m.command_json.get("expansion"):
        content = m.command_json["expansion"]
    if m.kind == "ooc":
        content = f"(OOC) {content}"
    if m.role == "assistant" and m.kind == "story":
        # the narrator sees the tags again (never stored in the reply): its own, or where the app found the speaker
        content = portrait_tags.retag(m, content, history_tags, portraits=portraits)
    if m.role == "assistant":
        # step 1: code fences and the app's labels copied into older replies are not sent again (the model copied them
        # from its own history: 53 replies of 55 began with ``` in the test of 19/11)
        from .reply_cleanup import strip_for_history
        content = strip_for_history(content) or content
    if info and m.role == "assistant" and m.kind == "story":
        # phase 2 (step 4): the narrator sees its earlier info blocks again (as the player corrected them), so it keeps
        # writing them; every earlier reply keeps its block, so the start of the request stays the same (cache)
        raw = ((m.generation_metadata_json or {}).get("info_table") or {}).get("raw")
        if raw is not None:
            content = f"{content}\n\n<info>\n{raw.strip()}\n</info>" if raw.strip() else f"{content}\n\n<info></info>"
    return content
