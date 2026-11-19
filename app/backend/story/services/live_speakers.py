"""Portraits while the reply is being written (v0.6, phase "portraits").

Small local models (Rocinante 12B...) rarely write the portrait tags ``[Name:N]`` (services/portrait_tags.py), so the
portrait used to wait for the scene analysis, several seconds after the reply. This module finds the speaker of each
paragraph *during* the stream, without any model call:

* a portrait tag that the narrator did write (it wins for its paragraph);
* otherwise the name next to the quotation marks: ``« … », dit Lily`` / ``"…," Lily said`` / ``Lily sourit : « … »``;
* otherwise, once a paragraph is finished, the one character named in its narration, or (for ``« … », dit-elle``)
  the one named in the paragraph just before.

Each change is sent to the screen at once (a ``portraits`` stream event). When the reply ends, what was found is stored
in the reply's metadata (``live_speakers``): ``portrait_tags.apply`` shows those portraits right away when the narrator
wrote no tag, and the same positions put tags back into the history sent to the model, so it learns the format.
The scene analysis still runs afterwards and corrects a wrong guess.
"""
from __future__ import annotations

import re
from typing import Any

from .entities import EntityIndex, norm
from .turn_analysis import PROTAGONIST_SPEAKS, SPEECH

QUOTE_CHARS = "\"“”«»"
_QUOTE_RE = re.compile(r'["“”«»]')
# speech verbs, French and English, as they look after entities.norm (lower case, no accents, hyphens become spaces)
VERBS = (r"(?:dit|dis|demande|demanda|repond|repondit|murmure|murmura|chuchote|chuchota|souffle|souffla|lance|lanca|ajoute|"
         r"ajouta|reprend|reprit|poursuit|poursuivit|retorque|retorqua|crie|cria|s ecrie|s ecria|s exclame|s exclama|soupire|"
         r"soupira|rit|bafouille|balbutie|balbutia|declare|declara|explique|expliqua|insiste|insista|glisse|glissa|marmonne|"
         r"marmonna|grogne|grogna|siffle|siffla|annonce|annonca|repete|repeta|continue|continua|conclut|hesite|hesita|"
         r"sourit|souriait|lache|lacha|precise|precisa|interroge|interrogea|ordonne|ordonna|confie|confia|avoue|avoua|"
         r"said|says|asked|asks|replied|replies|answered|whispered|murmured|muttered|shouted|called|snapped|added|"
         r"continued|retorted|declared|hissed|laughed|sighed|stammered|smiled|explained|mumbled|breathed)")
AFTER_QUOTE = re.compile(rf'"\s*[,.!?…]*\s*(?:{VERBS})(?:\s+[a-z]+){{0,2}}\s*$')  # « … », dit (doucement) Lily
NAME_THEN_VERB_AFTER_QUOTE = re.compile(rf'^\s+(?:{VERBS})\b')                       # "…," Lily said
BEFORE_QUOTE = re.compile(r'^[^".!?]{0,80}?[:,]?\s*"')                                # Lily sourit : « … »
FR_PROTAGONIST_SPEAKS = re.compile(
    r"\b(?:vous|tu)\b[^\"]{0,30}\b(?:dites|dis|repondez|reponds|demandez|demandes|murmurez|murmures|ajoutez|ajoutes|"
    r"lancez|lances|soufflez|souffles|chuchotez|chuchotes)\b|\b(?:dites|repondez|demandez|murmurez|ajoutez|lancez|"
    r"soufflez|chuchotez) vous\b")


# the protagonist's own line ("…," you call out / « … », répondez-vous / You smile: "…"), on normalised text
YOU_AFTER = re.compile(r'^\s*[,.!?…]*\s*(?:you|vous|tu)\b|^\s*[,.!?…]*\s*[a-z]+ez vous\b')
YOU_BEFORE = re.compile(r'(?:^|[.!?]\s+|"\s*)(?:you|vous|tu)\b[^".!?]{0,60}[:,]?\s*$')


def paragraphs(text: str) -> list[tuple[int, int]]:
    """(start, end) of the non-empty blank-line-separated paragraphs (the same split as the screen and turn_analysis)."""
    out, pos = [], 0
    for part in re.split(r"(\n\s*\n)", text):
        if part and not re.fullmatch(r"\n\s*\n", part) and part.strip():
            out.append((pos, pos + len(part)))
        pos += len(part)
    return out


def paragraph_at(paras: list[tuple[int, int]], pos: int) -> int:
    """Index of the paragraph holding ``pos`` (a position between two paragraphs belongs to the next one)."""
    for k, (a, b) in enumerate(paras):
        if pos < b:
            return k
    return len(paras)


def _protagonist_speaks(narration: str) -> bool:
    return bool(PROTAGONIST_SPEAKS.search(narration) or FR_PROTAGONIST_SPEAKS.search(norm(narration)))


class LiveSpeakers:
    """Follows one streamed reply. ``feed`` returns the new beat list when it changed (else ``None``)."""

    def __init__(self, index: EntityIndex, *, protagonist: set[str], portraits: dict[str, dict[int, str]],
                 held: dict[str, dict[str, Any]], auto_expressions: bool = True) -> None:
        self.index = index
        self.me = {n.casefold() for n in protagonist if n}
        self.me_ids = {cid for n in protagonist if n for cid in [index.resolve(n)] if cid}
        self.portraits = portraits
        self.held = held
        self.auto = auto_expressions
        self.beats: list[dict[str, Any]] = []
        self._cache: dict[str, list[tuple[str, int, float]]] = {}  # finished paragraph text -> speakers found

    # ------------------------------------------------------------------ helpers
    def _is_character(self, cid: str | None) -> bool:
        return bool(cid) and cid in self.index.entities and self.index.entities[cid].category == "character" \
            and cid not in self.me_ids

    def _held_slot(self, cid: str) -> int:
        return int((self.held.get(cid) or {}).get("slot") or 1)

    def _slot(self, cid: str, wanted: int) -> int:
        h = self.held.get(cid) or {}
        return self._held_slot(cid) if (h.get("locked") or not self.auto) else wanted

    def _mentions(self, t: str) -> list[tuple[str, int, int]]:
        """(character id, start, end) of each character named in an already normalised text."""
        pat = self.index._pattern()
        out = []
        for m in pat.finditer(t) if pat else []:
            ids = self.index.alias_map.get(m.group(1)) or set()
            cid = next(iter(ids)) if len(ids) == 1 else None
            if self._is_character(cid) and m.group(1) not in self.me:
                out.append((cid, m.start(), m.end()))
        return out

    def _names(self, narration: str) -> list[str]:
        return list(dict.fromkeys(c for c, _, _ in self._mentions(norm(narration))))

    @staticmethod
    def _flat(para: str) -> str:
        t = norm(para)
        for ch in "“”«»":
            t = t.replace(ch, '"')
        return t

    def _protagonist_quotes(self, t: str) -> set[int]:
        """Numbers of the quotes that the protagonist says (never a portrait)."""
        marks = [i for i, ch in enumerate(t) if ch == '"']
        out = set()
        for q in range(len(marks) // 2):
            a, b = marks[2 * q], marks[2 * q + 1]
            if YOU_AFTER.match(t[b + 1:b + 60]) or YOU_BEFORE.search(t[max(0, a - 80):a]):
                out.add(q)
        return out

    def _strong(self, para: str) -> list[tuple[str, int]]:
        """Speakers named right next to the quotation marks: (character id, number of the quote in the paragraph)."""
        t = self._flat(para)
        mine = self._protagonist_quotes(t)
        found: list[tuple[str, int]] = []
        ments = self._mentions(t)
        for k, (cid, a, b) in enumerate(ments):
            before, after = t[:a], t[b:]
            q_before = before.count('"')
            if q_before % 2 == 0 and q_before and (AFTER_QUOTE.search(before) or
                                                 (re.search(r'"\s*[,.!?…]*\s*$', before) and NAME_THEN_VERB_AFTER_QUOTE.match(after))):
                found.append((cid, q_before // 2 - 1))
                continue
            if q_before % 2 == 0:  # outside the speech: is a quote opening just after the name (same sentence)?
                m = BEFORE_QUOTE.match(after)
                nxt = ments[k + 1][1] if k + 1 < len(ments) else None
                if m and (nxt is None or nxt >= b + m.end()) and '"' in t[b + m.end():]:
                    found.append((cid, q_before // 2))
        out, seen = [], set()
        for cid, q in found:  # one speaker per quote, the first rule that named one
            if q not in seen and q not in mine:
                seen.add(q)
                out.append((cid, q))
        return out

    def _quote_pos(self, para: str, start: int, q: int) -> int:
        quotes = list(SPEECH.finditer(para))
        if not quotes:
            return start
        return start + quotes[min(max(q, 0), len(quotes) - 1)].start()

    def _detect(self, text: str, paras: list[tuple[int, int]], k: int, closed: bool,
                prev_names: list[str]) -> list[tuple[str, int, float]]:
        """(character id, position of its quote, confidence) for paragraph k."""
        a, b = paras[k]
        para = text[a:b]
        if not _QUOTE_RE.search(para):
            return []
        if closed and para in self._cache:
            return self._cache[para]
        out = [(cid, self._quote_pos(para, a, q), 0.8) for cid, q in self._strong(para)]
        flat = self._flat(para)
        quotes = flat.count('"') // 2
        if not out and closed and quotes and len(self._protagonist_quotes(flat)) >= quotes:
            out = []  # every line here is the protagonist's
        elif not out and closed:
            narration = SPEECH.sub(" ", para)
            names = self._names(narration)
            if len(names) == 1:
                out = [(names[0], self._quote_pos(para, a, 0), 0.6)]
            elif not names and not _protagonist_speaks(narration) and len(prev_names) == 1:
                out = [(prev_names[0], self._quote_pos(para, a, 0), 0.5)]
        if closed:
            self._cache[para] = out
        return out

    # ------------------------------------------------------------------ stream
    def compute(self, text: str, tags: list[dict[str, Any]], *, final: bool = False) -> list[dict[str, Any]]:
        paras = paragraphs(text)
        open_last = not final and not re.search(r"\n\s*\n\s*$", text)
        tagged: dict[int, list[dict[str, Any]]] = {}
        for t in tags:
            name = t.get("name") or ""
            cid = self.index.resolve(name) or self.index.resolve(name.split(" ")[0])
            if not self._is_character(cid) or name.casefold() in self.me:
                continue
            off = int(t.get("offset") or 0)
            k = paragraph_at(paras, off)
            pos = paras[k][0] if k < len(paras) and off < paras[k][0] else off
            lst = [x for x in tagged.setdefault(k, []) if x["character_id"] != cid]  # the later tag wins
            tagged[k] = lst + [{"character_id": cid, "slot": self._slot(cid, int(t.get("slot") or 1)), "paragraph": k,
                                "pos": pos, "source": "tag", "confidence": 1.0}]
        beats: list[dict[str, Any]] = []
        prev: list[str] = []
        for k in range(len(paras)):
            closed = not (open_last and k == len(paras) - 1)
            if k in tagged:
                beats.extend(tagged[k])
            else:
                for cid, pos, conf in self._detect(text, paras, k, closed, prev):
                    if not any(x["character_id"] == cid and x["paragraph"] == k for x in beats):
                        beats.append({"character_id": cid, "slot": self._held_slot(cid), "paragraph": k, "pos": pos,
                                      "source": "detected", "confidence": conf})
            a, b = paras[k]
            names = self._names(SPEECH.sub(" ", text[a:b]))
            if names:
                prev = names
        for k, lst in tagged.items():  # a tag at the very end, before its paragraph has any text
            if k >= len(paras):
                beats.extend(lst)
        return beats

    def feed(self, text: str, tags: list[dict[str, Any]], *, final: bool = False) -> list[dict[str, Any]] | None:
        beats = self.compute(text, tags, final=final)
        key = [(x["character_id"], x["paragraph"], x["slot"]) for x in beats]
        if key == [(x["character_id"], x["paragraph"], x["slot"]) for x in self.beats]:
            return None
        self.beats = beats
        return self.view()

    def view(self) -> list[dict[str, Any]]:
        """What the screen needs: name, expression and portrait file of each beat (asset ids only, never paths)."""
        from .assets import resolve_expression
        out = []
        for x in self.beats:
            asset_id, used, fallback = resolve_expression(self.portraits.get(x["character_id"], {}), x["slot"])
            out.append({"character_id": x["character_id"], "name": self.index.name(x["character_id"]),
                        "expression": x["slot"], "beat": "speaking", "paragraph": x["paragraph"], "asset_id": asset_id,
                        "slot_used": used, "is_fallback": fallback, "source": x["source"]})
        return out

    def found(self) -> list[dict[str, Any]]:
        """Stored with the reply (``live_speakers``)."""
        return [{k: x[k] for k in ("character_id", "slot", "paragraph", "pos", "source", "confidence")} for x in self.beats]


def for_story(db, story, branch_id: str) -> LiveSpeakers | None:
    """The follower for one reply of a story (``None`` without a lore pack: no known characters to show)."""
    if not story.world_id:
        return None
    from ..models import Avatar
    from . import assets, settings_service, state_service
    from .entities import build_index

    st_row = state_service.current(db, branch_id)
    state = state_service.normalize(st_row.state_json if st_row else {})
    index = build_index(db, story.world_id, state)
    av = db.get(Avatar, story.active_avatar_id) if story.active_avatar_id else None
    me = {av.name if av else "", str((story.avatar_snapshot_json or {}).get("name") or ""),
          str((state.get("player") or {}).get("name") or "")}
    held = ((story.settings_json or {}).get("expressions") or {}).get(branch_id) or {}
    auto = bool(settings_service.get(db, "auto_apply_expression_suggestions"))
    return LiveSpeakers(index, protagonist=me, portraits=assets.portrait_map(db, story.world_id), held=held,
                        auto_expressions=auto)
