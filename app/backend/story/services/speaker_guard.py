"""Who may get a portrait in a reply (v0.6, test report "30 tours": B6, B7, B10). No model call.

Seen in a 30-turn game with a local 12B model:

* B6: two maids, a refugee and Captain Elric (none of them lore characters) spoke with the portrait of Sylvia or
  Seria: a quote with no name next to it was given to the last character named, even several paragraphs earlier, or
  to the only lore character named in a paragraph about someone else. Now an unattributed line shows no portrait
  ("unknown") rather than a wrong one: only the paragraph just before counts, and never when the narration around the
  line is about an unnamed or unknown person ("one of the maids", "the old woman", "Elric nods").
* B7: a maid called "Lily" got the portrait of the goddess Lily Lumina. A first name alone (a tag ``[Lily:2]``, a
  name in the analysis) only means a lore character who is already in the scene; the full name always does.
* B10: Diana was marked present while she never appeared (the analysis gave a maid's line as her evidence). A
  character the scene did not have needs to be named in the narration of the reply (or by their full name, or by a
  clear reference such as "the Empress") before they get a portrait or a place in the scene.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .entities import EntityIndex, norm

SPEECH = re.compile(r'"[^"]*"|“[^”]*”|«[^»]*»')

# unnamed people, as they look after entities.norm (lower case, no accents)
PERSON = re.compile(
    r"\b(?:maids?|maidservants?|servants?|guards?|soldiers?|captain|knights?|man|men|woman|women|girl|girls|boy|boys|"
    r"child|children|elder|elderly|refugees?|villagers?|merchants?|strangers?|voice|someone|somebody|figure|priests?|"
    r"priestess|nobleman|noblewoman|butler|attendants?|messenger|scouts?|officer|innkeeper|waiter|waitress|crowd|"
    r"servantes?|domestiques?|gardes?|soldats?|capitaine|chevaliers?|homme|hommes|femme|femmes|fille|filles|garcon|"
    r"garcons|enfants?|vieillard|vieille|refugies?|refugiees?|villageois|villageoise|marchands?|marchandes?|inconnus?|"
    r"inconnues?|voix|quelqu un|silhouette|pretres?|pretresse|majordome|messager|eclaireurs?|officier|aubergiste|"
    r"serveuses?|serveurs?|foule|"
    # v0.6.2 (Kurio's DeepSeek test: "un étudiant de deuxième année" spoke with Lilia's portrait): school people
    r"students?|classmates?|pupils?|teachers?|professors?|instructors?|upperclassm[ae]n|freshm[ae]n|seniors?|juniors?|"
    r"first years?|second years?|third years?|boys?|lads?|etudiants?|etudiantes?|eleves?|camarades?|professeurs?|"
    r"professeures?|enseignants?|enseignantes?|surveillants?|surveillantes?|premiere annee|deuxieme annee|"
    r"troisieme annee|seconde annee|aines?|aine|ainees?|nouveaux|nouvelles?|novices?|apprentis?|apprenties?|jeune)\b")

# capitalised words that are not names (sentence openers, titles, pronouns), lower case
NOT_NAMES = set("""i a an the as when while with his her he she they it its you your yours we our their them this that
these those then but and or so yet just before after now still even here there what who why how where which yes no
well oh ah please sir lady lord princess prince emperor empress king queen majesty highness god goddess hero heroine
captain commander general knight saint holy imperial empire kingdom realm demon demons dragon guild church tower mage
academy council legion first second third chapter day night morning evening
vous tu il elle ils elles on je nous le la les un une des du de au aux ce cet cette ces son sa ses leur leurs mon ma mes
ton ta tes et mais ou donc or ni car puis alors quand lorsque tandis comme si oui non bien ici voici voila pourquoi
comment qui que quoi dans sur sous avec sans pendant apres avant depuis enfin soudain seigneur dame sire princesse
empereur imperatrice roi reine heros heroine capitaine commandant chevalier deesse dieu majeste altesse empire royaume
""".split())
SUBJECT_PRONOUN = re.compile(r"(?:^|[.!?…]\s+|\n)\s*(he|she|they|il|elle|ils|elles)\b")
CAPITAL = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ'’]{2,}\b")


def narration(text: str) -> str:
    """The text with every quoted line blanked out."""
    return SPEECH.sub(lambda m: " " * len(m.group(0)), text or "")


def named_in_narration(index: EntityIndex, text: str) -> set[str]:
    return set(index.find_mentions(narration(text), ("character",)))


def full_name_in(index: EntityIndex, cid: str, text: str) -> bool:
    full = norm(index.name(cid))
    return len(full.split()) > 1 and re.search(rf"\b{re.escape(full)}\b", norm(text or "")) is not None


def first_name_only(index: EntityIndex, name: str, cid: str) -> bool:
    """``name`` is only part of the character's full name ("Lily" for "Lily Lumina")."""
    full = norm(index.name(cid))
    return len(full.split()) > 1 and norm(name) != full and norm(name) not in {norm(a) for a in index.entities[cid].aliases}


def name_may_mean(index: EntityIndex, name: str, cid: str, present: Iterable[str], text: str = "") -> bool:
    """B7: a first name alone means this lore character only when they are already in the scene (or named in full)."""
    return not first_name_only(index, name, cid) or cid in set(present or []) or full_name_in(index, cid, text)


def unknown_person(index: EntityIndex, narration_text: str, protagonist: Iterable[str] = ()) -> bool:
    """The narration is about someone the lore does not name: an unnamed person ("one of the maids") or a capitalised
    name that is no lore entity ("Elric nods"), written before any lore character ("Princess Seria listens to the
    refugee" is still about Seria; "The maid glances at Seria" is about the maid)."""
    t = norm(narration_text)
    me = {norm(p) for n in protagonist or [] if n for p in [n, *n.split()]}
    spots = [m.start() for m in PERSON.finditer(t)]
    # test 2: "He addresses Seria with a nod" is about him, not her: a pronoun opening a sentence before any lore
    # name is someone else (a speaker the narration does not name)
    spots += [m.start(1) for m in SUBJECT_PRONOUN.finditer(t)]
    for w in CAPITAL.finditer(narration_text or ""):
        k = norm(w.group(0)).strip("'’")
        if k in NOT_NAMES or k in me or k in index.alias_map:
            continue
        hit = re.search(rf"\b{re.escape(k)}\b", t)
        spots.append(hit.start() if hit else 0)
    if not spots:
        return False
    pat = index._pattern()
    lore = [m.start() for m in pat.finditer(t)
            if index.entities[next(iter(index.alias_map[m.group(1)]))].category == "character"
            and m.group(1) not in me] if pat else []
    return not lore or min(spots) < min(lore)


def named_here(index: EntityIndex, reply: str, refs: Iterable[str] = ()) -> set[str]:
    """Characters this reply itself names: in its narration, by full name, or by a clear reference ("the Empress")."""
    ok = named_in_narration(index, reply) | set(refs or [])
    ok |= {cid for cid, e in index.entities.items() if e.category == "character" and full_name_in(index, cid, reply)}
    return ok


def may_appear(index: EntityIndex, reply: str, present_before: Iterable[str], refs: Iterable[str] = ()) -> set[str]:
    """B10: the characters who may be shown in this reply: already in the scene, or named by the reply itself."""
    return set(present_before or []) | named_here(index, reply, refs)


def filter_result(result: dict[str, Any], allowed: set[str], named: set[str] | None = None) -> list[str]:
    """Remove from an analysis result the characters who may not appear (portraits, speakers, presence). Returns the
    removed ids (kept in the diagnostics).

    ``named`` (test 2): a SILENT presence (no line, no visible reaction) also needs the reply to name the character:
    the goddess of the opening stayed "also present" in a village 25 turns later, because she was still in the scene."""
    gone: set[str] = set()
    if named is not None:
        active = {b.get("character_id") for b in result.get("beats") or [] if b.get("beat") in ("speaking", "reacting")}
        silent = {b.get("character_id") for b in result.get("beats") or []
                  if b.get("beat") == "present" and b.get("character_id") not in active and b.get("character_id") not in named}
        if silent:
            gone |= silent
            result["beats"] = [b for b in result.get("beats") or []
                               if not (b.get("beat") == "present" and b.get("character_id") in silent)]
            cast = result.get("cast") or {}
            if "present" in cast:
                cast["present"] = [c for c in cast["present"] if c not in silent]

    def keep(cid: Any) -> bool:
        if cid in allowed:
            return True
        gone.add(cid)
        return False

    result["beats"] = [b for b in result.get("beats") or [] if b.get("beat") not in ("speaking", "reacting", "present")
                       or keep(b.get("character_id"))]
    result["speakers"] = [s for s in result.get("speakers") or [] if keep(s.get("character_id"))]
    result["dialogue"] = [d for d in result.get("dialogue") or [] if keep(d.get("character_id"))]
    if result.get("active_speaker_id") and result["active_speaker_id"] not in allowed:
        result["active_speaker_id"] = result["speakers"][-1]["character_id"] if result["speakers"] else None
    cast = result.get("cast") or {}
    for k in ("present", "speaking"):
        if k in cast:
            cast[k] = [c for c in cast[k] if keep(c)]
    return sorted(c for c in gone if c)
