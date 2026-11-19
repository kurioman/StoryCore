"""Optional post-turn analysis: who spoke (with a 1–6 expression), three suggested next actions, character discoveries.

One small JSON request after a reply completes, through the provider-neutral ``complete`` interface. It never touches
the visible transcript and its failure never affects the finished reply. Results are tied to the assistant message
(hence to its branch/alternative). Consent: ``local_only`` (default) skips cloud models so no cost is incurred silently.
"""
from __future__ import annotations

import logging
import time
import re
from typing import Any

from sqlalchemy import select

from ..models import Avatar, Message, Story, TurnAnalysis, now_iso
from ..providers import ChatMessage, ProviderError
from . import discovery, settings_service, state_service, story_tree, suggestions as suggestions_svc, world_state
from . import usage as usage_svc
from .assets import EXPRESSIONS
from .entities import EntityIndex, build_index
from .runtime import AppContext, ConsentRequired, NoModelConfigured

log = logging.getLogger(__name__)

EXPRESSION_KEYS = {**{"smiling": 2, "sobbing": 3, "aggressive": 4, "stern": 4, "disgust": 5, "disgusted": 5,
                      "shy": 6, "embarrassed": 6}, **{e["key"]: e["slot"] for e in EXPRESSIONS}}
EXPRESSION_GUIDE = ", ".join(f"{e['slot']} {e['name'].lower()}" for e in EXPRESSIONS)
WEAK_EVIDENCE = 0.4  # below this confidence an expression falls back to neutral (01)
# The analysis has its own output budget (the story's reply limit can be too small for the JSON; observed: mistral-nemo
# repeating speaker entries until cut off at 700 tokens) and bounded arrays in the schema.
PINNED_CHECK = 8  # pinned memories sent to the analysis for the contradiction check (v0.5 phase 7.6)
LIGHT_SKIP_CHARS = 700
LIGHT_SKIP_REASON = "Nothing to analyse in this short reply (no character in the scene)."
ANALYSIS_MAX_TOKENS = 1800  # v1.6: three written drafts instead of three 14-word labels
RETRY_MAX_TOKENS = 3000  # the one automatic repair attempt gets more room (a cut-off answer is the commonest failure)
MAX_ITEMS = 8
SCHEMA_VERSION = 4  # v1.6: suggestions are player-ready drafts (v1.5: present/left, separate from speaking and mentions)
REACTION_MIN_CONFIDENCE = 0.6  # a silent reaction changes a portrait only when the emotion is clear
SUGGESTION_KINDS = ("action", "dialogue", "observation", "social", "strategy")
# provider failures worth one automatic retry; auth/network/rate limits are not retried here (Retry stays manual)
RETRYABLE = {"truncated", "empty_output", "invalid_response"}

# v0.6 (phase 9): the same rules in about a third fewer words (this prompt is sent after every reply)
RULES = """You annotate one turn of an interactive story for the app. You never write story text.
Return ONLY one JSON object with exactly these keys:
{"schema_version": 4,
 "speakers": [{"character": id, "expression": 1-6, "line": "their first spoken words, copied from the REPLY", "evidence": "short quote", "confidence": 0-1}],
 "active_speaker": id or null,
 "reactions": [{"character": id, "expression": 1-6, "anchor": "short quote showing the reaction", "confidence": 0-1}],
 "present": [{"character": id, "evidence": "short quote showing them in the scene"}],
 "left": [{"character": id, "evidence": "short quote"}],
 %s
 "discoveries": [{"character": id, "status": "rumored|encountered|known", "evidence": "short quote"}],
 %s
 %s
 "warnings": []}
Expressions: %s.
Rules:
- speakers: listed characters who speak in the REPLY, in order. Expression from their own words and actions, not the
  overall mood; 1 when unsure. 5 anger/outrage/disgust, 4 stern focus or defiance, 3 sadness/compassion, 6 embarrassment
  or romantic tenderness (never romance without clear evidence).
- active_speaker: whose dialogue the reply ends on or centres on; null if nobody speaks.
- reactions: present listed characters who visibly react WITHOUT speaking (a look, a gesture, a flush); not mere
  bystanders, never a speaker; omit unclear emotions.
- present: every listed character physically in the protagonist's scene in this REPLY (speakers, silent onlookers,
  arrivals), also when described without their name ("the Headmaster", "a girl with silver hair": use the list's hints);
  NOT someone only mentioned, remembered, written to or speaking from elsewhere. left: those who clearly leave. Unsure: omit.
%s- discoveries: "encountered" = physically present or acting in the scene; "known" = introduced to the protagonist (name
  or role) or in a real exchange WITH them (being named while watching is still "encountered"); "rumored" = only mentioned.
  Never the protagonist; a name existing in lore is not a discovery.
%s%s- Quotes ("line", "anchor", "evidence") are copied exactly from the REPLY.
- Use ONLY ids from the character list. Never invent characters."""

RELATIONSHIP_SHAPE = '''"relationship_changes": [{"source": id, "target": id or "protagonist", "dimension": "%s", "delta": integer, "impact": "minor|major", "evidence": "short exact quote from the REPLY", "confidence": 0-1}],'''
RELATIONSHIP_RULE = """- relationship_changes: only when THIS reply clearly changes how one character sees another. "source" is
  whose view changes (never the protagonist). Directional: no mirror change. Pick the dimension the evidence shows (not
  trust by default): trust = reliability/safety; affection = warmth (not romance); respect = esteem for competence or
  integrity; familiarity = knowing each other better through real time together; rivalry = competitive tension; fear =
  feeling threatened. Courtesy, routine answers, small talk, following instructions: no change; a misunderstanding: none
  or -1. Ordinary moments: delta -3..3, "minor"; up to 10 only for a major event (confession, betrayal, rescue, cruelty,
  humiliation, reconciliation), "major". Feelings can diverge (betrayal: trust falls, affection may stay). Neutral: [].
"""

SUGGESTION_SHAPE = ('"suggestions": [{"text": "the message itself, as the player would send it", "approach": "tone in one or two words", '
                    '"kind": "action|dialogue|observation|social|strategy"}],')


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[“”«»„]", '"', re.sub(r"[‘’]", "'", s or ""))).strip().casefold()


def locate(reply: str, quote: Any, min_len: int = 6) -> tuple[str, int] | None:
    """Where a model-supplied quote occurs in the reply: (the exact text as written, paragraph index), or None when it
    is too short or not really there (anchors are never trusted unverified)."""
    q = _norm(str(quote or "").strip().strip('"'))
    if len(q) < min_len:
        return None
    paras = [p for p in re.split(r"\n\s*\n", reply or "") if p.strip()]
    for i, p in enumerate(paras):
        np_ = _norm(p)
        k = np_.find(q)
        if k < 0:
            continue
        # map the normalised hit back to the original paragraph text (same characters, collapsed whitespace)
        words = q.split(" ")
        pat = r"\s+".join(re.escape(w).replace("'", "['‘’]").replace('"', '["“”«»„]') for w in words)
        m = re.search(pat, p, re.I)
        return (m.group(0) if m else p.strip()[:len(q)], i)
    return None


def _expression(v: Any) -> int:
    if isinstance(v, str):
        v = v.strip().lower()
        if v in EXPRESSION_KEYS:
            return EXPRESSION_KEYS[v]
        m = re.match(r"^0*([1-6])\b", v)
        return int(m.group(1)) if m else 1
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 1
    return n if 1 <= n <= 6 else 1


def _conf(v: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default


def _character(index: EntityIndex, allowed: set[str], v: Any) -> str | None:
    if not isinstance(v, str) or not v.strip():
        return None
    cid = v if v in index.entities else index.resolve(v)
    if cid is None or cid not in allowed or index.entities[cid].category != "character":
        return None
    return cid


def _list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


QUOTES = re.compile(r'["“”«»]')
SPEECH = re.compile(r'"[^"]*"|“[^”]*”|«[^»]*»')  # a quoted stretch of speech (straight, curly or guillemets)
PROTAGONIST_SPEAKS = re.compile(r"\byou (?:\w+ )?(?:say|said|reply|replied|respond|responded|answer|answered|ask|asked|"
                                r"add|added|murmur|murmured|whisper|whispered|tell|told|explain|explained|offer|offered)\b", re.I)


SAY = (r"(?:said|says|say|asked|asks|replied|replies|answered|answers|added|adds|continued|continues|whispered|whispers|"
       r"murmured|murmurs|muttered|mutters|snapped|snaps|called|calls|shouted|shouts|told|tells|explained|explains|remarked|"
       r"remarks|admitted|admits|repeated|repeats|dit|demande|demanda|répond|répondit|murmure|murmura|ajoute|ajouta|lance|lança)")
SAY_WORD = re.compile(rf"\b{SAY}\b", re.I)
SUBJECT_PRONOUN = re.compile(r"(?:she|he|they|elle|il|elles|ils)\b", re.I)
PLAYER_AFTER = re.compile(rf"you\b(?:\s+\w+)?\s+{SAY}\b", re.I)
PLAYER_BEFORE = re.compile(rf"\byou\b(?:\s+\w+)?\s+{SAY}[,:]?\s*$", re.I)
SAY_LEADS_IN = re.compile(rf"\b{SAY}[,:]?\s*$", re.I)
WRITTEN = re.compile(r"\b(?:reads?|wrote|written|titled|entitled|labell?ed|inscribed|engraved|signed|so-called|known as|called|"
                     r"named|intitul[ée]e?s?)\b[\s:,]*$", re.I)


def _quotes(reply: str, player_turn: str) -> list[dict[str, Any]]:
    """Each quoted stretch that reads as someone speaking, with the clause on either side of it. Written text, scare quotes
    and the player's own words repeated back are left out."""
    out: list[dict[str, Any]] = []
    said = _norm(player_turn)
    for i, p in enumerate(x for x in re.split(r"\n\s*\n", reply or "") if x.strip()):
        for m in SPEECH.finditer(p):
            inner = m.group(0)[1:-1].strip()
            head = p[:m.start()].rstrip()
            before = SPEECH.sub(" ", re.split(r"(?<=[.!?…])\s+", head)[-1]).strip() if head else ""
            after = re.match(r"[^.!?…\"“”«»]*", p[m.end():].lstrip(" ,—–-")).group(0).strip()
            if WRITTEN.search(head) or (len(inner) >= 12 and _norm(inner) in said):
                continue
            if len(inner.split()) > 3 or re.search(r"[.!?…,;:]", inner) or SAY_WORD.search(after) or SAY_LEADS_IN.search(before):
                out.append({"paragraph": i, "text": m.group(0), "before": before, "after": after})
    return out


def _voice_of(q: dict[str, Any], named) -> str | None:
    """Who the words around a quote say spoke it: a character id, "protagonist", "other" (someone not on the list: 'the
    porter said') or None when they do not say ('she said', or no attribution at all)."""
    after, before = q["after"], q["before"]
    if PLAYER_AFTER.match(after) or PLAYER_BEFORE.search(before):
        return "protagonist"
    if SUBJECT_PRONOUN.match(after):
        return None
    if SAY_WORD.search(after):
        ids = named(after)
        return ids[0] if ids else "other"
    if before and not SUBJECT_PRONOUN.match(before):
        ids = named(" ".join(before.split()[:3]))  # the subject of the sentence right before the quote
        if ids:
            return ids[0]
        if SAY_WORD.search(before):
            return "other"
    return None


def promote_speakers(base: dict[str, Any], raw: dict[str, Any], reply: str, index: EntityIndex, allowed: set[str], named,
                     scene_present: list[str] | None, player_turn: str, current_expressions: dict[str, int] | None) -> None:
    """v1.6.2: someone clearly talking must not stay "present". ``dialogue_candidates`` only knows names written in this
    reply, so '"Not here," she said' in a running conversation discarded a correct speaker, and the character was shown as
    merely present. Only the analysis' own verified lines and evidence are used here; ambiguity changes nothing.

    * The model named the speaker: accepted when its line is a real quote nobody else owns, the words around the quote do not
      give it to someone else, and the speaker is the only one here, was addressed by the player, or is in narrative focus.
    * The model named nobody: an unclaimed quote goes to the one character it can belong to, if the text points at them.
    """
    find = named or (lambda t: index.find_mentions(t, ("character",)))
    quotes = _quotes(reply, player_turn)
    if not quotes:
        return
    paras = [p for p in re.split(r"\n\s*\n", reply) if p.strip()]
    ok = {s["character_id"] for s in base["speakers"]}
    rows = [s for s in _list(raw.get("speakers")) if isinstance(s, dict)]

    def owner_of(hit: tuple[str, int]) -> dict[str, Any] | None:
        return next((q for q in quotes if q["paragraph"] == hit[1] and _norm(hit[0]) in _norm(q["text"])), None)

    def claimed(s: dict[str, Any]) -> dict[str, Any] | None:
        hit = locate(reply, s.get("line"), 2)
        return owner_of(hit) if hit else None

    taken = [id(q) for s in rows if _character(index, allowed, s.get("character") or s.get("character_id")) in ok
             for q in [claimed(s)] if q]
    seen: list[str] = []
    for key, ev in (("reactions", "anchor"), ("present", "evidence")):
        for r in _list(raw.get(key)):
            cid = _character(index, allowed, r.get("character") or r.get("character_id")) if isinstance(r, dict) else None
            if cid and locate(reply, r.get(ev) or r.get("evidence"), 4) and cid not in seen:
                seen.append(cid)
    gone = {_character(index, allowed, (p or {}).get("character")) for p in _list(raw.get("left")) if isinstance(p, dict)}
    here = [c for c in seen if c not in gone] or [c for c in scene_present or [] if c in allowed and c not in gone]
    addressed = set(find(player_turn)) if player_turn else set()

    def in_focus(cid: str, q: dict[str, Any]) -> bool:
        """The nearest narration naming anyone names them. 'She glanced at Serena.' names who she looked at, not who "she" is,
        so a clause led by a pronoun does not count."""
        own = SPEECH.sub(" ", paras[q["paragraph"]])
        for clause in (q["before"], q["after"]):
            if clause and SUBJECT_PRONOUN.match(clause):
                own = own.replace(clause, " ")
        for p in [own, *(SPEECH.sub(" ", x) for x in reversed(paras[:q["paragraph"]]))]:
            names = find(p)
            if names:
                return cid in names
        return False

    def add(cid: str, q: dict[str, Any], expression: int, confidence: float) -> None:
        base["speakers"].append({"character_id": cid, "expression": expression, "evidence": q["text"][:160],
                                 "confidence": round(confidence, 2), "line": q["text"].strip("\"“”«» "), "paragraph": q["paragraph"]})
        ok.add(cid)
        taken.append(id(q))

    disputed: list[int] = []
    for s in rows:
        cid = _character(index, allowed, s.get("character") or s.get("character_id"))
        q = claimed(s) if cid and cid not in ok else None
        if q is None or id(q) in taken:
            continue
        disputed.append(id(q))
        if _voice_of(q, find) not in (None, "other", cid):
            continue
        if {c for c in here if c != cid} and cid not in addressed and not in_focus(cid, q):
            continue  # another person here could equally have said it: stay conservative
        add(cid, q, _expression(s.get("expression")), _conf(s.get("confidence")))
    if base["speakers"]:
        return
    voiced = dialogue_candidates(reply, index, named) or set()
    for q in quotes:
        who = _voice_of(q, find)
        pool = [c for c in here if c in voiced] or here
        if who in ("protagonist", "other") or len(pool) != 1 or (who is not None and who != pool[0]):
            continue
        cid = pool[0]
        led = [c for c in (q["after"], q["before"]) if SUBJECT_PRONOUN.match(c)]
        if who != cid and (id(q) in disputed or any(cid in find(c) for c in led)):
            continue  # the model gave it to someone else, or "she" is the one looking at this character
        if who == cid or led or cid in addressed or in_focus(cid, q):
            add(cid, q, int((current_expressions or {}).get(cid) or 1), 0.6)
            return


def dialogue_candidates(text: str, index: EntityIndex, named=None) -> set[str] | None:
    """Characters who can plausibly be speaking: named in a paragraph containing quoted dialogue; when that paragraph
    names nobody ('"...," she says'), the characters named in the paragraph just before it. Onlookers described in the
    preceding paragraph do not count when the quote's own paragraph names its speaker (observed live with mistral-nemo).
    ``None`` when the reply has no quoted dialogue (e.g. "Name: line" scripts), so nothing is filtered."""
    paras = [p for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    if not any(QUOTES.search(p) for p in paras):
        return None
    out: set[str] = set()
    last_named: list[str] = []
    for p in paras:
        # v1.4: only the narration outside the quotes attributes a line. Names *inside* the speech are people talked
        # about or addressed (live: Lucia's lines mentioned Anastasia and Kael, so Lucia was rejected as the speaker
        # and the reply got no portraits at all)
        narration = SPEECH.sub(" ", p)
        # v1.5: "the Headmaster said" / "Lucia's sister answered" count as naming (services/identity.py)
        names = named(narration) if named else index.find_mentions(narration, ("character",))
        if QUOTES.search(p):
            if names:
                out.update(names)
            elif not PROTAGONIST_SPEAKS.search(narration):  # '"...," you say' is the protagonist, not the people nearby
                out.update(last_named)  # '"...," she says' after a paragraph (or more) that named her
        if names:
            last_named = names
    return out


def attribute_dialogue(text: str, index: EntityIndex, speakers: set[str], named=None,
                       lines: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Speaker of each paragraph that contains quoted speech (v1.5 reading aid), deterministic and conservative: the one
    analysed speaker named in that paragraph's narration; with no name, the one analysed speaker named in the paragraph(s)
    just before ('"…," she says'); '"…," you say' is the protagonist; anything else is ``None`` (unknown — no label).
    ``lines`` are the analysis' verified spoken lines: a paragraph holding one speaker's line is theirs, whatever it names.
    Paragraph numbers match the client's split (blank-line separated, empty ones dropped)."""
    paras = [p for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    out: list[dict[str, Any]] = []
    last: list[str] = []
    from .speaker_guard import unknown_person
    stranger = lambda narration: unknown_person(index, narration)  # noqa: E731
    for i, p in enumerate(paras):
        narration = SPEECH.sub(" ", p)
        names = named(narration) if named else index.find_mentions(narration, ("character",))
        if SPEECH.search(p):
            here = [c for c in names if c in speakers]
            owners = {d.get("character_id") for d in lines or [] if d.get("text") and d["text"] in p and d.get("character_id") in speakers}
            if len(owners) == 1:
                who: str | None = next(iter(owners))
            elif len(here) == 1:
                who = here[0]
            elif not names and PROTAGONIST_SPEAKS.search(narration):
                who = "protagonist"
            elif not names:
                prev = [c for c in last if c in speakers]
                who = prev[0] if len(prev) == 1 else None
            else:
                who = None
            out.append({"paragraph": i, "character_id": who})
        # test 2 (same fix as B6 for portraits): only the paragraph just before counts, and not when it is about an
        # unnamed or unknown person ("Welcome to the Central Empire" was labelled with a goddess named three
        # paragraphs earlier); a paragraph that names nobody but whose line went to one speaker passes them on
        if stranger(narration):
            last = []
        elif names:
            last = names
        else:
            last = [out[-1]["character_id"]] if out and out[-1]["paragraph"] == i and out[-1]["character_id"] in speakers else []
    return out


def normalize(raw: Any, index: EntityIndex, allowed: set[str], *, want_suggestions: bool = True,
              reply: str | None = None, axes: list[str] | None = None, named=None, mentioned: list[str] | None = None,
              current_expressions: dict[str, int] | None = None, draft_check=None, min_suggestions: int = 3,
              scene_present: list[str] | None = None, player_turn: str = "") -> dict[str, Any]:
    """Validate model output against known characters. Anything malformed is dropped, never repaired by guessing.

    With ``reply``, a listed speaker must also be named next to quoted dialogue: models tend to list onlookers too; quotes
    used as anchors/dialogue/evidence must really occur in the reply. ``named`` resolves names plus contextual references
    (posts, kinship); ``mentioned`` are the characters referred to in this turn (for the present/mentioned split)."""
    raw = raw if isinstance(raw, dict) else {}
    base = _normalize_v1(raw, index, allowed, want_suggestions=want_suggestions, reply=reply, named=named,
                         draft_check=draft_check, min_suggestions=min_suggestions)
    text = reply or ""
    if reply is not None:
        promote_speakers(base, raw, reply, index, allowed, named, scene_present, player_turn, current_expressions)
        ids = [s["character_id"] for s in base["speakers"]]
        if base["active_speaker_id"] not in ids:
            named_active = _character(index, allowed, raw.get("active_speaker"))
            base["active_speaker_id"] = named_active if named_active in ids else (ids[-1] if ids else None)
    beats: list[dict[str, Any]] = []
    dialogue: list[dict[str, Any]] = []
    raw_speakers = {(_character(index, allowed, s.get("character") or s.get("character_id"))): s
                    for s in _list(raw.get("speakers")) if isinstance(s, dict)}
    for sp in base["speakers"]:
        promoted = sp.pop("line", None), sp.pop("paragraph", None)
        line = (promoted if promoted[0] else locate(text, (raw_speakers.get(sp["character_id"]) or {}).get("line"))) if reply is not None else None
        anchor = line or (locate(text, sp.get("evidence")) if reply is not None else None)
        if line:
            dialogue.append({"character_id": sp["character_id"], "text": line[0]})
        beats.append({"character_id": sp["character_id"], "expression": sp["expression"], "beat": "speaking",
                      "anchor": anchor[0] if anchor else None, "paragraph": anchor[1] if anchor else None})
    speaking = {s["character_id"] for s in base["speakers"]}
    for r in _list(raw.get("reactions")):
        if not isinstance(r, dict):
            continue
        cid = _character(index, allowed, r.get("character") or r.get("character_id"))
        conf = _conf(r.get("confidence"))
        anchor = locate(text, r.get("anchor") or r.get("evidence")) if reply is not None else None
        # a silent reaction needs a real place in the text and a clear emotion; it is never a speaker
        if cid is None or cid in speaking or any(b["character_id"] == cid for b in beats) or anchor is None or conf < REACTION_MIN_CONFIDENCE:
            continue
        beats.append({"character_id": cid, "expression": _expression(r.get("expression")), "beat": "reacting",
                      "anchor": anchor[0], "paragraph": anchor[1], "confidence": round(conf, 2)})
    # v1.5 presence: present (with a quote found in the reply) ≠ speaking ≠ only mentioned. Speakers and visible reactions
    # are present by definition; a silent present character gets a small "present" beat (portrait, no expression change)
    present: list[str] = [b["character_id"] for b in beats]
    for p in _list(raw.get("present")):
        if not isinstance(p, dict):
            continue
        cid = _character(index, allowed, p.get("character") or p.get("character_id"))
        if cid is None or cid in present:
            continue
        anchor = locate(text, p.get("evidence") or p.get("anchor"), 4) if reply is not None else None
        if anchor is None:
            continue  # no evidence in the text: not marked present (a mention is not presence)
        present.append(cid)
        beats.append({"character_id": cid, "expression": int((current_expressions or {}).get(cid) or 1), "beat": "present",
                      "anchor": anchor[0], "paragraph": anchor[1]})
    left: list[str] = []
    for p in _list(raw.get("left")):
        cid = _character(index, allowed, (p or {}).get("character") if isinstance(p, dict) else None)
        if cid and cid not in left and (reply is None or locate(text, p.get("evidence"), 4)):
            left.append(cid)
    beats.sort(key=lambda b: (b["paragraph"] if b["paragraph"] is not None else 10_000))
    cast = {"present": present, "speaking": [s["character_id"] for s in base["speakers"]], "left": left,
            "mentioned": [c for c in dict.fromkeys(mentioned or []) if c not in present and c in index.entities]}
    for s in base["suggestions"]:
        kind = str(s.pop("raw_kind", None) or "").strip().lower()
        s["kind"] = kind if kind in SUGGESTION_KINDS else ("dialogue" if QUOTES.search(s["label"]) else "action")
    return {**base, "beats": beats, "dialogue": dialogue, "cast": cast,
            "warnings": [str(w)[:200] for w in _list(raw.get("warnings"))][:5],
            "relationship_changes": _relationship_changes(raw, index, allowed, text if reply is not None else None, axes or [])}


def _relationship_changes(raw: dict[str, Any], index: EntityIndex, allowed: set[str], reply: str | None,
                          axes: list[str]) -> list[dict[str, Any]]:
    from .relationships import MAJOR_MAX_DELTA, AUTO_MAX_DELTA, PROTAGONIST

    out: list[dict[str, Any]] = []
    axis_map = {a.casefold(): a for a in axes}
    for c in _list(raw.get("relationship_changes"))[:MAX_ITEMS]:
        if not isinstance(c, dict):
            continue
        src = _character(index, allowed, c.get("source"))
        tgt_raw = str(c.get("target") or "").strip()
        tgt = PROTAGONIST if tgt_raw.casefold() in ("protagonist", "player") else _character(index, allowed, tgt_raw)
        dim = axis_map.get(str(c.get("dimension") or "").strip().casefold())
        try:
            delta = int(round(float(c.get("delta"))))
        except (TypeError, ValueError):
            continue
        # the protagonist's own feelings are the player's (no source "protagonist"); unknown axes/ids are dropped
        if src is None or tgt is None or src == tgt or dim is None or delta == 0:
            continue
        impact = "major" if str(c.get("impact") or "").lower() == "major" else "minor"
        cap = MAJOR_MAX_DELTA if impact == "major" else AUTO_MAX_DELTA
        delta = max(-cap, min(cap, delta))
        ev = locate(reply, c.get("evidence")) if reply is not None else None
        if any(x["source_id"] == src and x["target_id"] == tgt and x["dimension"] == dim for x in out):
            continue
        out.append({"source_id": src, "target_id": tgt, "dimension": dim, "delta": delta, "impact": impact,
                    "confidence": round(_conf(c.get("confidence")), 2), "evidence": (ev[0] if ev else str(c.get("evidence") or ""))[:200],
                    "evidence_verified": ev is not None})
    return out


def _normalize_v1(raw: dict[str, Any], index: EntityIndex, allowed: set[str], *, want_suggestions: bool = True,
                  reply: str | None = None, named=None, draft_check=None, min_suggestions: int = 3) -> dict[str, Any]:
    voiced = dialogue_candidates(reply, index, named) if reply is not None else None
    speakers: list[dict[str, Any]] = []
    for s in _list(raw.get("speakers")):
        if not isinstance(s, dict):
            continue
        cid = _character(index, allowed, s.get("character") or s.get("character_id"))
        if cid is None or any(x["character_id"] == cid for x in speakers) or (voiced is not None and cid not in voiced):
            continue
        conf = _conf(s.get("confidence"))
        expr = _expression(s.get("expression"))
        speakers.append({"character_id": cid, "expression": expr if conf >= WEAK_EVIDENCE else 1,
                         "evidence": str(s.get("evidence") or "")[:160], "confidence": round(conf, 2)})
    active = _character(index, allowed, raw.get("active_speaker"))
    if active not in {s["character_id"] for s in speakers}:
        active = speakers[-1]["character_id"] if speakers else None
    suggestions: list[dict[str, Any]] = []
    sugg_error = None
    if want_suggestions:
        suggestions, rejected = suggestions_svc.select(_list(raw.get("suggestions")), draft_check)
        if len(suggestions) < min_suggestions:
            why = f" Rejected: {', '.join(sorted(set(rejected)))}." if rejected else ""
            sugg_error = f"The model returned {len(suggestions)} usable suggestion(s) instead of three.{why}"
            suggestions = []
    discoveries: list[dict[str, Any]] = []
    for d in _list(raw.get("discoveries")):
        if not isinstance(d, dict):
            continue
        cid = _character(index, allowed, d.get("character") or d.get("character_id"))
        status = str(d.get("status") or "").strip().lower().replace("rumoured", "rumored")
        if cid is None or status not in discovery.STATUSES or any(x["character_id"] == cid for x in discoveries):
            continue
        discoveries.append({"character_id": cid, "status": status, "evidence": str(d.get("evidence") or "")[:200]})
    return {"speakers": speakers, "active_speaker_id": active, "suggestions": suggestions,
            "suggestions_error": sugg_error, "discoveries": discoveries}


def analysis_schema(character_ids: list[str], want_suggestions: bool = True, axes: list[str] | None = None,
                    want_relationships: bool = True) -> dict[str, Any]:
    """JSON schema (v2) for providers with structured outputs; adapters reduce it to their strict subset. Output is
    still validated by ``normalize`` (ids, anchors, bounds)."""
    cid: dict[str, Any] = {"type": "string", "enum": character_ids} if character_ids else {"type": "string"}
    tgt: dict[str, Any] = {"type": "string", "enum": [*character_ids, "protagonist"]} if character_ids else {"type": "string"}
    expr = {"type": "integer", "minimum": 1, "maximum": 6}
    conf = {"type": "number", "minimum": 0, "maximum": 1}
    sugg_item = {"type": "object", "properties": {"text": {"type": "string"}, "approach": {"type": "string"},
                                                  "kind": {"type": "string", "enum": list(SUGGESTION_KINDS)}},
                 "required": ["text", "approach", "kind"]}
    return {
        "type": "object",
        "properties": {
            "schema_version": {"type": "integer"},
            "speakers": {"type": "array", "items": {"type": "object", "properties": {
                "character": cid, "expression": expr, "line": {"type": "string"}, "evidence": {"type": "string"},
                "confidence": conf}, "required": ["character", "expression", "line", "evidence", "confidence"]}, "maxItems": MAX_ITEMS},
            "active_speaker": {"anyOf": [cid, {"type": "null"}]},
            "reactions": {"type": "array", "items": {"type": "object", "properties": {
                "character": cid, "expression": expr, "anchor": {"type": "string"}, "confidence": conf},
                "required": ["character", "expression", "anchor", "confidence"]}, "maxItems": MAX_ITEMS},
            "present": {"type": "array", "items": {"type": "object", "properties": {
                "character": cid, "evidence": {"type": "string"}}, "required": ["character", "evidence"]}, "maxItems": MAX_ITEMS},
            "left": {"type": "array", "items": {"type": "object", "properties": {
                "character": cid, "evidence": {"type": "string"}}, "required": ["character", "evidence"]}, "maxItems": MAX_ITEMS},
            "suggestions": ({"type": "array", "items": sugg_item, "minItems": 3, "maxItems": 3} if want_suggestions
                            else {"type": "array", "maxItems": 0}),
            "discoveries": {"type": "array", "items": {"type": "object", "properties": {
                "character": cid, "status": {"type": "string", "enum": list(discovery.STATUSES)},
                "evidence": {"type": "string"}}, "required": ["character", "status", "evidence"]}, "maxItems": MAX_ITEMS},
            "relationship_changes": ({"type": "array", "items": {"type": "object", "properties": {
                "source": cid, "target": tgt,
                "dimension": {"type": "string", "enum": axes} if axes else {"type": "string"},
                "delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "impact": {"type": "string", "enum": ["minor", "major"]}, "evidence": {"type": "string"}, "confidence": conf},
                "required": ["source", "target", "dimension", "delta", "impact", "evidence", "confidence"]}, "maxItems": MAX_ITEMS}
                if want_relationships else {"type": "array", "maxItems": 0}),
            "world_state": world_state.analysis_schema(),
            "warnings": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        },
        "required": ["schema_version", "speakers", "active_speaker", "reactions", "present", "left", "suggestions", "discoveries",
                     "relationship_changes", "world_state", "warnings"],
    }


def _get_row(db, m: Message) -> TurnAnalysis:
    row = db.scalar(select(TurnAnalysis).where(TurnAnalysis.message_id == m.id))
    if row is None:
        row = TurnAnalysis(message_id=m.id, story_id=m.story_id, branch_id=m.branch_id, status="pending")
        db.add(row)
        db.flush()
    return row


def skip_reason(mode: str, is_cloud: bool) -> str | None:
    """Why the player's own settings leave a reply unanalysed; None when it should be analysed. This is a choice, not a failure."""
    if mode == "off":
        return "Scene analysis is off in Settings."
    if mode == "local_only" and is_cloud:
        return "Scene analysis is set to Local models only, so replies from this hosted model are not analysed."
    return None


def analysis_is_cloud(ctx: AppContext, db, story: Story, cfg: dict[str, Any]) -> bool:
    """Only "Local models only" needs the answer, so the other modes never resolve a provider."""
    if cfg.get("turn_analysis_mode") != "local_only":
        return False
    try:
        return ctx.resolve(db, ctx.extraction_profile_id(db, story) or ctx.story_profile_id(db, story)).adapter.is_cloud
    except (NoModelConfigured, ConsentRequired):
        return False


def _skip(row: TurnAnalysis, reason: str) -> dict[str, Any]:
    row.status, row.error, row.suggestions_error = "skipped", reason, None
    return {"status": "skipped", "reason": reason}


def _unavailable(row: TurnAnalysis, reason: str) -> dict[str, Any]:
    """A real obstacle, shown to the player with a Retry. Nothing is switched off because of it."""
    row.status, row.error, row.suggestions_error = "failed", reason, reason
    return {"status": "failed", "error": reason}


async def analyse(ctx: AppContext, message_id: str, *, force: bool = False) -> dict[str, Any]:
    """Runs after every completed reply. Whatever goes wrong ends as a visible failure with a Retry, never as an endless spinner:
    a "running" row would also refuse the retry."""
    try:
        return await _analyse(ctx, message_id, force=force)
    except Exception:
        log.exception("turn analysis crashed for %s", message_id)
        msg = "Scene analysis stopped unexpectedly. Your reply is safe; press Retry. Details are in the app log."
        with ctx.db.session() as db:
            row = db.scalar(select(TurnAnalysis).where(TurnAnalysis.message_id == message_id))
            if row is not None:
                row.status, row.error, row.suggestions_error = "failed", msg, msg
        return {"status": "failed", "error": msg}


async def _analyse(ctx: AppContext, message_id: str, *, force: bool = False) -> dict[str, Any]:
    with ctx.db.session() as db:
        m = db.get(Message, message_id)
        if m is None or m.role != "assistant" or m.kind != "story" or m.status != "complete" or not m.content.strip():
            return {"status": "not_applicable"}
        story = db.get(Story, m.story_id)
        row = _get_row(db, m)
        # v1.7 portrait tags: the narrator already said who speaks and how (services/portrait_tags.py). Those portraits
        # stay on screen while this analysis runs and are kept by it; it adds presence, reactions, relationships,
        # the clock and suggestions.
        tagged = bool((m.generation_metadata_json or {}).get("portrait_tags_applied"))
        if tagged and row.status != "succeeded":  # e.g. a Retry reset the row: rebuild the tagged portraits first
            from . import portrait_tags
            tagged = portrait_tags.apply(db, m.id)
            row = _get_row(db, m)
        if row.status in ("succeeded", "running") and not force:
            return {"status": row.status}
        tag_view = {"speakers": list(row.speakers_json or []), "active": row.active_speaker_id,
                    "beats": list(row.beats_json or []), "dialogue": list(row.dialogue_json or [])} if tagged else None

        def keep_tags(result: dict[str, Any]) -> dict[str, Any]:
            if tagged:  # the reply keeps its tagged portraits; the obstacle is only noted
                row.error = result.get("reason") or result.get("error")
                return {"status": "succeeded", "tags_only": True, **result}
            return result
        cfg = settings_service.get_all(db)
        mode = cfg["turn_analysis_mode"]
        if mode == "off":
            return {"status": "succeeded", "tags_only": True} if tagged else _skip(row, skip_reason(mode, False))
        try:
            pid = ctx.extraction_profile_id(db, story) or ctx.story_profile_id(db, story)
            resolved = ctx.resolve(db, pid)
        except NoModelConfigured as e:
            return keep_tags({"error": str(e)}) if tagged else _unavailable(row, str(e))
        except ConsentRequired:
            msg_ = ("The analysis model is a cloud provider that has not been approved for data sharing. "
                    "Approve it in Settings, then retry.")
            return keep_tags({"error": msg_}) if tagged else _unavailable(row, msg_)
        reason = skip_reason(mode, resolved.adapter.is_cloud)
        if reason:
            return {"status": "succeeded", "tags_only": True} if tagged else _skip(row, reason)
        st_row = state_service.current(db, m.branch_id)
        state = state_service.normalize(st_row.state_json if st_row else {})
        index = build_index(db, story.world_id, state)
        user = db.get(Message, m.parent_id) if m.parent_id else None
        user_text = (user.content if user and user.role == "user" else "")[:2000]
        reply = m.content[:8000]
        branch = story_tree.get_branch(db, story, m.branch_id)
        mentioned = index.find_mentions(f"{user_text}\n{reply}", ("character",))
        # v1.5: references by post or kinship ("the Headmaster", "Lucia's sister") resolve to canonical ids
        from . import canon as canon_svc, identity, roles
        registry = roles.build_registry(db, story.world_id, index)
        canon = canon_svc.facts(db, story.world_id, index)
        in_scene = set(mentioned) | set(state["scene"].get("present", []))
        ctx_refs = identity.contextual_refs(f"{user_text}\n\n{reply}", index, registry, canon, in_scene)
        hints: dict[str, str] = {}
        for r in ctx_refs:
            hints.setdefault(r.character_id, f"referred to as “{r.phrase}” in this turn")
            if r.character_id not in mentioned:
                mentioned.append(r.character_id)
        named = identity.resolver(index, registry, canon, set(mentioned) | set(state["scene"].get("present", [])))
        # v0.6 (test report "30 tours", B6/B7/B10): who may be shown at all in this reply
        from . import speaker_guard
        named_now = speaker_guard.named_here(index, reply, {r.character_id for r in ctx_refs})
        may_show = set(state["scene"].get("present") or []) | named_now
        # v0.5 phase 7.5: a short reply with no character, in a scene whose place and time are known, gives the analysis
        # nothing to do (no speaker, reaction, relationship or discovery): no request is spent on it
        if (not tagged and not force and not cfg.get("action_suggestions_enabled", True) and not mentioned
                and not state["scene"].get("present") and len(reply) < LIGHT_SKIP_CHARS
                and state["scene"].get("location") and state["scene"].get("time")):
            return _skip(row, LIGHT_SKIP_REASON)
        candidates = list(dict.fromkeys([*mentioned, *state["scene"].get("present", []),
                                         *discovery.roster(db, story, branch).keys()]))
        allowed = {c for c in candidates if c in index.entities and index.entities[c].category == "character"}
        posts = {r["character_id"]: r["title"] for r in registry["roles"]}
        # a discovery needs evidence in this turn: the character is named in it or already present in the scene
        discoverable = set(mentioned) | set(state["scene"].get("present", []))
        stored_exprs = ((story.settings_json or {}).get("expressions") or {}).get(branch.id) or {}
        cur_exprs = {k: int(v.get("slot") or 1) for k, v in stored_exprs.items()}
        locked = {k for k, v in stored_exprs.items() if v.get("locked")}
        auto_expressions = bool(cfg.get("auto_apply_expression_suggestions", True))
        avatar = db.get(Avatar, story.active_avatar_id) if story.active_avatar_id else None
        protagonist = avatar.name if avatar else (story.avatar_snapshot_json or {}).get("name") or "the player character"
        want = bool(cfg.get("action_suggestions_enabled", True))
        from .relationships import CORE_AXES
        axes = list(dict.fromkeys([*(state.get("relationship_axes") or []), *CORE_AXES]))  # v1.5: + rivalry
        rel_mode = cfg.get("relationship_mode") or "auto_conservative"
        want_rel = rel_mode != "off"
        row.attempts, row.error = (row.attempts or 0) + 1, None
        if not tagged:
            row.status = "running"
        row.provider_id, row.model_id = resolved.provider.id, resolved.profile.model_id
        turns = [p.content for p in story_tree.path_messages(db, m.parent_id, include_deleted=False)
                 if p.role == "user" and p.kind == "story" and not p.command_json][-suggestions_svc.RECENT_TURNS:] if m.parent_id else []
        voice = suggestions_svc.voice(turns, reply, protagonist)
        draft_check = suggestions_svc.checker(voice, index, allowed)
        # what is switched off is not asked for: one request serves every enabled feature, with no tokens spent on the others
        system = RULES % (SUGGESTION_SHAPE if want else '"suggestions": [],',
                          RELATIONSHIP_SHAPE % ("|".join(axes) or "trust") if want_rel else '"relationship_changes": [],',
                          world_state.ANALYSIS_SHAPE, EXPRESSION_GUIDE, suggestions_svc.rule(voice) if want else "",
                          RELATIONSHIP_RULE if want_rel else "", world_state.ANALYSIS_RULE)
        def hint(c: str) -> str:
            parts = [x for x in (posts.get(c), hints.get(c)) if x]
            return f" ({'; '.join(parts)})" if parts else ""
        chars = "\n".join(f"- {c}: {index.name(c)}{hint(c)}" for c in sorted(allowed, key=index.name)) or "(none)"
        # v0.5 phase 7.6: the pinned memories, so that a clear contradiction is reported in "warnings" (same request)
        from .context_builder import visible_facts
        pinned = [f.content for f in visible_facts(db, story, branch, story_tree.path_ids(db, branch))
                  if f.pinned and f.status in ("active", "disputed")][:PINNED_CHECK]
        pinned_text = ("\n\nPINNED MEMORIES (established facts of this story):\n" + "\n".join(f"- {p[:200]}" for p in pinned)
                       + "\nIf the REPLY clearly contradicts one of them, add a short description of it to \"warnings\" "
                         "(\"contradicts: ...\"). Otherwise leave warnings empty.") if pinned else ""
        prompt = (f"Character list (id: name):\n{chars}\n\nProtagonist (never a speaker, discovery or relationship source): "
                  f"{protagonist}\n\n{world_state.prompt_state(state['scene'])}\n\n"
                  f"PLAYER TURN:\n{user_text or '(none)'}\n\nREPLY:\n{reply}{pinned_text}")
        row_id, provider_label = row.id, f"{resolved.provider.provider_type}/{resolved.profile.model_id}"
    from .extraction import parse_json_object  # local import: extraction imports turns, which imports us lazily
    extra = {"json_schema": analysis_schema(sorted(allowed), want, axes, want_rel)} if resolved.adapter.supports_json_schema else {}
    diagnostics: list[dict[str, Any]] = []
    result = None
    msg = ""
    # one normal attempt + at most one automatic repair attempt (bigger budget, told what was wrong); same analysis row,
    # so a retry can never duplicate discoveries, expressions or relationship changes
    for attempt in (1, 2):
        t0 = time.monotonic()
        messages = [ChatMessage("user", prompt)]
        if attempt == 2:
            messages.append(ChatMessage("user", f"Your previous answer could not be used ({msg[:300]}). Return the same "
                                                "analysis again as ONE complete JSON object with exactly the keys above, "
                                                "no prose, no code fence, short quotes."))
        try:
            raw = await resolved.adapter.complete(
                resolved.profile.model_id, system, messages,
                {**resolved.params, "temperature": 0.3, "max_tokens": ANALYSIS_MAX_TOKENS if attempt == 1 else RETRY_MAX_TOKENS},
                json_mode=True, **extra)
            usage_svc.record(ctx, m.story_id, "analysis", resolved.adapter)
            obj = parse_json_object(raw)
            missing = [k for k in ("speakers", "suggestions" if want else "speakers") if not isinstance(obj.get(k), list)]
            if missing:
                raise ValueError(f"required key(s) missing or not a list: {', '.join(dict.fromkeys(missing))}")
            # after the one repair attempt, two good drafts are worth showing; never padded up to three
            result = normalize(obj, index, allowed, want_suggestions=want, reply=reply, axes=axes, named=named,
                               mentioned=[c for c in mentioned if c in allowed], current_expressions=cur_exprs,
                               draft_check=draft_check, min_suggestions=3 if attempt == 1 else 2,
                               scene_present=list(state["scene"].get("present") or []), player_turn=user_text)
            result["world_state_raw"] = obj.get("world_state")  # validated against the scene when it is applied
            hidden = speaker_guard.filter_result(result, may_show, named_now)
            if hidden:
                result["guard_removed"] = hidden
            if want and result["suggestions_error"] and attempt == 1:
                raise ValueError(result["suggestions_error"])  # e.g. two suggestions: worth the one repair attempt
            diagnostics.append({"attempt": attempt, "ok": True, "seconds": round(time.monotonic() - t0, 2), "chars": len(raw),
                                **({"note": result["suggestions_error"]} if result["suggestions_error"] else {})})
            break
        except ProviderError as e:
            msg = e.message
            diagnostics.append({"attempt": attempt, "ok": False, "category": e.category, "reason": e.message[:200],
                                "details": e.details[:200], "seconds": round(time.monotonic() - t0, 2)})
            if e.category not in RETRYABLE:
                break
        except ValueError as e:
            msg = f"Invalid analysis output: {str(e)[:300]}"
            diagnostics.append({"attempt": attempt, "ok": False, "category": "parse", "reason": msg[:200],
                                "seconds": round(time.monotonic() - t0, 2)})
    log.info("turn analysis %s via %s: %s", message_id, provider_label,
             "; ".join(f"#{d['attempt']} {'ok' if d['ok'] else d.get('category')} {d['seconds']}s" for d in diagnostics))
    if result is None:
        tried = f" (after {len(diagnostics)} attempts)" if len(diagnostics) > 1 else ""
        msg = f"{msg}{tried}"
        log.warning("turn analysis failed for %s: %s", message_id, msg)
        with ctx.db.session() as db:
            row = db.get(TurnAnalysis, row_id)
            if row is not None:
                row.status = "succeeded" if tagged else "failed"  # tagged portraits stay; the failure is still shown
                row.error, row.diagnostics_json = msg, [*((row.diagnostics_json or []) if tagged else []), *diagnostics]
                row.suggestions_error = msg if want else None
        return {"status": "failed", "error": msg}
    with ctx.db.session() as db:
        row = db.get(TurnAnalysis, row_id)
        m = db.get(Message, message_id)
        if row is None or m is None:
            return {"status": "gone"}
        story = db.get(Story, m.story_id)
        branch = story_tree.get_branch(db, story, m.branch_id)
        if result.get("guard_removed"):
            diagnostics.append({"source": "speaker_guard", "not_in_scene": result["guard_removed"]})
        if tag_view is not None and result["speakers"] and \
                all(b.get("source") == "detected" for b in tag_view["beats"]):
            # v0.6: the speakers guessed while streaming give way to the analysis' own; a guessed line of someone the
            # analysis confirms as a speaker keeps its portrait (the analysis lists one line per speaker)
            said = {sp["character_id"]: sp["expression"] for sp in result["speakers"]}
            taken = {b.get("paragraph") for b in result["beats"] if b.get("beat") == "speaking"}
            extra = [{**b, "expression": b["expression"] if b.get("mood") else said[b["character_id"]]}
                     for b in tag_view["beats"] if b["character_id"] in said and b.get("paragraph") not in taken]
            result["beats"] = sorted(result["beats"] + extra,
                                     key=lambda b: (b["paragraph"] if b.get("paragraph") is not None else 10_000))
            tag_view = None
        if tag_view is not None:  # the narrator's own tags win for the characters it tagged
            mine = {b["character_id"] for b in tag_view["beats"]}
            result["speakers"], result["active_speaker_id"] = tag_view["speakers"], tag_view["active"]
            result["beats"] = sorted(tag_view["beats"] + [b for b in result["beats"] if b["character_id"] not in mine],
                                     key=lambda b: (b["paragraph"] if b.get("paragraph") is not None else 10_000))
            result["dialogue"] = tag_view["dialogue"] + [d for d in result["dialogue"] if d["character_id"] not in mine]
            result["cast"]["present"] = list(dict.fromkeys([*mine, *result["cast"]["present"]]))
            result["cast"]["speaking"] = list(dict.fromkeys([*mine, *result["cast"]["speaking"]]))
            result["cast"]["mentioned"] = [c for c in result["cast"]["mentioned"] if c not in mine]
            diagnostics.insert(0, {"source": "portrait_tags", "tags": len(tag_view["beats"])})
        # a locked portrait, or any portrait while automatic expressions are off, keeps the expression the player chose
        for item in (*result["speakers"], *result["beats"]):
            if not auto_expressions or item.get("character_id") in locked:
                item["expression"] = cur_exprs.get(item.get("character_id"), 1)
        row.speakers_json, row.active_speaker_id = result["speakers"], result["active_speaker_id"]
        row.suggestions_json, row.suggestions_error = result["suggestions"], result["suggestions_error"]
        row.discoveries_json, row.status, row.updated_at = result["discoveries"], "succeeded", now_iso()
        # mentioned-only and leaving characters are kept with the beats for the record (never shown as portraits)
        row.beats_json = result["beats"] + [{"character_id": c, "beat": "mentioned", "paragraph": None}
                                            for c in result["cast"]["mentioned"]] + \
            [{"character_id": c, "beat": "left", "paragraph": None} for c in result["cast"]["left"]]
        row.dialogue_json, row.schema_version = result["dialogue"], SCHEMA_VERSION
        row.diagnostics_json = diagnostics
        m.speaker_character_id = result["active_speaker_id"] or m.speaker_character_id
        md_now = dict(m.generation_metadata_json or {})
        if tag_view is None and result["speakers"] and not m.edited_at and \
                not any(t.get("source", "tag") == "tag" for t in md_now.get("portrait_tags") or []):
            # v0.6: where the analysis found the speakers, the history sent to the model shows their tags
            from . import portrait_tags
            md_now["portrait_tags"] = portrait_tags.from_beats(m.content, result["beats"], index.name)
            m.generation_metadata_json = md_now
        from . import continuity
        continuity.set_alerts(m, "contradiction", [{"text": w[:200]} for w in result.get("warnings") or []
                                                   if pinned_text and re.search(r"contradict", w, re.I)][:2])
        for d in result["discoveries"]:
            if d["character_id"] not in discoverable:
                continue
            discovery.record(db, story, branch, character_id=d["character_id"], name=index.name(d["character_id"]),
                             status=d["status"], source_message_id=m.id, evidence=d["evidence"], method="analysis")
        # portraits follow the speakers and the clearly visible silent reactions, only while this reply is the live
        # head of its branch; characters without a beat keep their current expression
        is_head = branch.head_message_id == m.id
        expressive = [b for b in result["beats"] if b["beat"] in ("speaking", "reacting")]
        if auto_expressions and is_head and expressive:
            from .turns import apply_expressions
            apply_expressions(story, branch.id, [{"character_id": b["character_id"], "slot": b["expression"],
                                                  "evidence": b.get("anchor") or ""} for b in expressive],
                              source="analysis", message_id=m.id)
        # relationships: only for a reply that is part of the branch's story (an older alternative never changes state)
        if m.id in story_tree.live_path_ids(db, branch):
            from . import relationships
            row.relationships_json = relationships.apply_from_analysis(db, story, branch, m.id, result["relationship_changes"],
                                                                       index, rel_mode)
        else:
            row.relationships_json = [{**c, "status": "dropped", "reason": "reply is not on the active story path"}
                                      for c in result["relationship_changes"]]
        # in-story time/place/weather (v1.4): only the live head moves the clock (an older reply re-analysed must not
        # set the world back); every value needs a quote found in the reply or the player's turn
        if is_head:
            # this reply's own earlier clock update (the time cues applied right after it was written) is undone first,
            # so the analysis compares with the scene as it was before the reply
            world_state.revert_message(db, story, branch, {m.id}, "the reply was analysed")
            st_now = state_service.current(db, branch.id)
            scene_now = state_service.normalize(st_now.state_json if st_now else {})["scene"]
            year_start = world_state.calendar_of(db, story.world_id)["year_start"]
            update = world_state.validate(result.get("world_state_raw"), m.content, user_text, scene_now, year_start)
            update = world_state.with_cues(update, m.content, scene_now, year_start, user_text)  # B3: plain cues
            went_back = ("time" in update["changes"] and not update["days_passed"] and "story_day" not in update["changes"]
                         and continuity.time_went_back(scene_now.get("time"), update["changes"]["time"]))
            continuity.set_alerts(m, "time_back", [{"from": scene_now.get("time"), "to": update["changes"]["time"]}]
                                  if went_back else [])
            if update["dropped"]:
                log.info("world state for %s: dropped %s", message_id, update["dropped"])
            from . import chrono
            from_start = m.kind == "story" and chrono.tracked_from_start(db, m)
            from . import scene_cast
            moved = "location" in update["changes"] and not scene_cast.same_place(scene_now.get("location"), update["changes"]["location"])
            world_state.apply_from_analysis(db, story, branch, m.id, update, index, first_reply=from_start)
            if m.kind == "story":  # v1.5.1: this reply's header now shows what it established
                chrono.record_current(db, m, branch, "analysis")
            # v1.5: who is physically here (never mentions); a move to a new place replaces the previous cast
            scene_cast.apply_from_analysis(db, story, branch, m.id, result["cast"]["present"], result["cast"]["left"],
                                           index, location_changed=moved,
                                           named_here=speaker_guard.named_in_narration(index, m.content))
    return {"status": "succeeded", **{k: result[k] for k in ("speakers", "active_speaker_id", "suggestions")}}


PORTRAIT_BEATS = ("speaking", "reacting", "present")


def visible_beats(beats: list[Any] | None) -> list[dict[str, Any]]:
    """Beats shown as portraits: speaking, reacting and silent-present characters — never mentions or departures."""
    return [b for b in beats or [] if isinstance(b, dict) and b.get("beat") in PORTRAIT_BEATS]


def cast_of(beats: list[Any] | None) -> dict[str, list[str]]:
    """Present / speaking / mentioned / left for one analysed reply (from its stored beats)."""
    out: dict[str, list[str]] = {"present": [], "speaking": [], "mentioned": [], "left": []}
    for b in beats or []:
        if not isinstance(b, dict) or not b.get("character_id"):
            continue
        kind = b.get("beat")
        if kind in PORTRAIT_BEATS:
            out["present"].append(b["character_id"])
            if kind == "speaking":
                out["speaking"].append(b["character_id"])
        elif kind in ("mentioned", "left"):
            out[kind].append(b["character_id"])
    return out


def scene_for(db, story: Story, message: Message | None) -> dict[str, Any]:
    """Speakers/suggestions for one assistant message, falling back to the offline heuristics when not analysed."""
    if message is None:
        return {"message_id": None, "status": "none", "speakers": [], "active_speaker_id": None, "suggestions": [],
                "suggestions_error": None, "error": None, "source": "none", "beats": [], "dialogue": [],
                "relationship_changes": [], "cast": None}
    row = db.scalar(select(TurnAnalysis).where(TurnAnalysis.message_id == message.id))
    out = {"message_id": message.id, "branch_id": message.branch_id, "status": row.status if row else "none",
           "error": row.error if row else None, "suggestions": row.suggestions_json if row else [],
           "suggestions_error": row.suggestions_error if row else None, "speakers": [], "active_speaker_id": None,
           "source": "analysis", "beats": visible_beats(row.beats_json) if row else [],
           "cast": cast_of(row.beats_json) if row else None, "dialogue": (row.dialogue_json or []) if row else [],
           "relationship_changes": [c for c in ((row.relationships_json or []) if row else []) if c.get("status") in ("applied", "proposed")]}
    if row and message.edited_at and (row.updated_at or "") < message.edited_at:
        # the reply text changed after it was analysed: old speakers/options describe text that no longer exists
        out.update(status="stale", suggestions=[], speakers=[], active_speaker_id=None, source="none", beats=[], dialogue=[],
                   suggestions_error="The reply was edited after these suggestions were made; refresh them.")
        return out
    if row and row.status == "succeeded" and row.speakers_json:
        out["speakers"], out["active_speaker_id"] = row.speakers_json, row.active_speaker_id
        return out
    # heuristic fallback (rule-based, offline): one attributed speaker plus keyword moods
    md = message.generation_metadata_json or {}
    moods = {s["character_id"]: s for s in md.get("mood_suggestions") or []}
    sp = message.speaker_character_id
    if sp:
        mood = moods.get(sp) or {}
        if not settings_service.get(db, "auto_apply_expression_suggestions"):  # the keyword guess must not override the player
            held = (((story.settings_json or {}).get("expressions") or {}).get(message.branch_id) or {}).get(sp) or {}
            mood = {"slot": held.get("slot")}
        out["speakers"] = [{"character_id": sp, "expression": int(mood.get("slot") or 1), "evidence": mood.get("evidence") or "",
                            "confidence": float(mood.get("confidence") or 0.3)}]
        out["active_speaker_id"] = sp
        out["source"] = "heuristic"
    return out
