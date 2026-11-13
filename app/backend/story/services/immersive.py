"""Optional immersive interleaving (v1.5, spec §2B): NPC reactions between the player's own quoted lines.

Contract — the player's text is canonical and never rewritten:
* The stored user message is unchanged. ``segment`` only *describes* it: contiguous parts (exact character offsets that
  concatenate back to the original text), each ending with one quoted utterance and the rest of its line.
* The narrator is asked to write reaction blocks introduced by ``[[after:P<n>]]`` markers and to never repeat, quote or
  continue the protagonist. ``MarkerFilter`` removes the markers from the stream (they never reach the database, the
  screen or later context) and records where each block starts.
* ``finalize`` validates the result (known ids, increasing order, no text before the first marker, no reproduced player
  line). Anything else falls back to the classic presentation with the reason recorded — the reply text is kept, and
  the player's message is shown as it always was.
* The composite view is assembled at read time by slicing the stored user message and the stored reply by offsets, after
  checking both texts are unchanged (hashes). An edited message therefore shows classically; nothing is duplicated in
  storage, context, memory capture or export (the reply contains only the other characters' reactions).

Eligibility is deliberately narrow: at least two clearly quoted utterances; no slash command, OOC note, code block,
unbalanced quotes or long quoted documents. Everything else uses the classic path unchanged.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

MODES = ("classic", "immersive")
MAX_TEXT = 2000
MAX_PARTS = 8
MAX_QUOTE = 400  # a longer "quotation" is pasted lore or a document, not a spoken line
SPEECH = re.compile(r"«[^«»]{1,%d}»|“[^“”]{1,%d}”|\"[^\"\n]{1,%d}\"" % (MAX_QUOTE, MAX_QUOTE, MAX_QUOTE))
MARK = re.compile(r"\[\[\s*after\s*:\s*(P\d{1,2})\s*\]\]", re.I)


def text_hash(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:16]


def segment(text: str) -> dict[str, Any]:
    """{"eligible": bool, "reason": str, "parts": [{"id", "start", "end", "speech": [start, end]}]} — offsets into
    ``text``; the parts are contiguous and cover the whole text exactly."""
    t = text or ""
    s = t.strip()

    def no(reason: str) -> dict[str, Any]:
        return {"eligible": False, "reason": reason, "parts": []}

    if not s:
        return no("empty")
    if s.startswith("/") or s.lower().startswith(("(ooc", "ooc:", "[ooc", "((")):
        return no("command or out-of-character note")
    if "```" in t or len(t) > MAX_TEXT:
        return no("code block or very long text")
    if t.count('"') % 2 or t.count("«") != t.count("»") or t.count("“") != t.count("”"):
        return no("quotation marks are not balanced")
    spans = [m.span() for m in SPEECH.finditer(t)]
    if len(spans) < 2:
        return no("fewer than two quoted lines")
    if len(spans) > MAX_PARTS:
        return no("too many quoted lines for one turn")
    parts: list[dict[str, Any]] = []
    start = 0
    for i, (a, b) in enumerate(spans):
        end = t.find("\n", b)
        end = len(t) if end < 0 else end
        nxt = spans[i + 1][0] if i + 1 < len(spans) else None
        if nxt is not None and nxt < end:
            end = nxt  # two quotes on one line: split just before the next one (connecting words stay with the first)
        parts.append({"id": f"P{i + 1}", "start": start, "end": end, "speech": [a, b]})
        start = end
    parts[-1]["end"] = len(t)  # trailing action text belongs to the last part
    assert "".join(t[p["start"]:p["end"]] for p in parts) == t  # exact coverage: nothing invented, nothing lost
    return {"eligible": True, "reason": "", "parts": parts}


def instruction(text: str, seg: dict[str, Any], protagonist: str) -> str:
    """Extra narrator instruction for an eligible turn (sent with the request only; never stored in the transcript)."""
    lines = []
    for p in seg["parts"]:
        a, b = p["speech"]
        line = re.sub(r"\s+", " ", text[a:b])
        lines.append(f"[{p['id']}] ends with the line {line[:120]}{'…' if len(line) > 120 else ''}")
    n = len(seg["parts"])
    return (f"Immersive dialogue mode for this turn. The player's turn above has {n} parts, in this order:\n"
            + "\n".join(lines) + "\n"
            "Write only the other characters' and the world's reactions, placed BETWEEN the player's parts. Begin each "
            "reaction block with a line containing only a marker naming the part it follows, e.g. [[after:P1]]. Use the "
            "markers in increasing order, each at most once; skip a part when nothing would naturally happen after it; "
            f"the last block must follow P{n}, and a reaction to a line goes after that line, never before it. Write "
            "nothing before the first marker. Never repeat, quote or "
            f"paraphrase the player's words, and never write anything for {protagonist} — no words, actions, glances, "
            "thoughts or feelings; they are already written by the player.")


class MarkerFilter:
    """Removes ``[[after:Pn]]`` markers from a token stream (markers may be split across chunks) and records the clean
    offset where each block starts. Only ids in ``valid`` are markers; anything else passes through as text."""

    def __init__(self, seg: dict[str, Any], user_text: str, user_message_id: str | None):
        self.seg, self.user_text, self.user_message_id = seg, user_text, user_message_id
        self.buf = ""
        self.clean = ""
        self.marks: list[tuple[str, int]] = []

    def feed(self, piece: str) -> str:
        self.buf += piece
        out = ""
        while self.buf:
            i = self.buf.find("[[")
            if i < 0:
                keep = 1 if self.buf.endswith("[") else 0
                out += self.buf[:len(self.buf) - keep]
                self.buf = self.buf[len(self.buf) - keep:]
                break
            out += self.buf[:i]
            rest = self.buf[i:]
            j = rest.find("]]")
            if j < 0:
                if len(rest) > 24:  # not a marker after all
                    out += rest[:2]
                    self.buf = rest[2:]
                    continue
                self.buf = rest
                break
            m = MARK.fullmatch(rest[:j + 2])
            if m:
                self.clean += out
                out = ""
                self.marks.append((m.group(1).upper(), len(self.clean)))
                self.buf = rest[j + 2:]
            else:
                out += rest[:2]
                self.buf = rest[2:]
        self.clean += out
        return out

    def flush(self) -> str:
        tail, self.buf = self.buf, ""
        self.clean += tail
        return tail

    def finalize(self, complete: bool) -> tuple[str, dict[str, Any]]:
        """(content to store, metadata). Content is always marker-free; ``status`` ok or fallback with a reason."""
        ids = [p["id"] for p in self.seg["parts"]]
        meta: dict[str, Any] = {"mode": "immersive", "user_message_id": self.user_message_id,
                                "user_hash": text_hash(self.user_text),
                                "parts": [{"id": p["id"], "start": p["start"], "end": p["end"]} for p in self.seg["parts"]]}
        pre = self.clean[: self.marks[0][1]] if self.marks else self.clean
        blocks = [(mid, self.clean[pos: self.marks[k + 1][1] if k + 1 < len(self.marks) else len(self.clean)])
                  for k, (mid, pos) in enumerate(self.marks)]
        reason = ""
        order = [ids.index(m) if m in ids else -1 for m, _ in self.marks]
        if not complete:
            reason = "the reply did not finish"
        elif not self.marks:
            reason = "the model did not mark where its reactions go"
        elif pre.strip():
            reason = "the model wrote text before the first reaction marker"
        elif -1 in order:
            reason = "the model referred to a part that does not exist"
        elif order != sorted(order) or len(set(order)) != len(order):
            reason = "the reaction markers were out of order or repeated"
        elif any(not b.strip() for _, b in blocks):
            reason = "a reaction block was empty"
        elif order[-1] != len(ids) - 1:
            # live GLM-5 (v1.5 request 19): the whole reaction, including the answer to the player's last line, was
            # placed after P1 — shown that way, the player's final words would follow the reply to them
            reason = "the last reaction did not follow the player's final part"
        else:
            body = _norm(self.clean)
            for p in self.seg["parts"]:
                a, b = p["speech"]
                said = _norm(self.user_text[a + 1:b - 1])
                if len(said) >= 12 and said in body:
                    reason = "the reply repeated the player's own line"
                    break
        if reason:
            # classic presentation: the reply's own text in order, markers removed, nothing reordered or dropped
            content = "\n\n".join(x.strip() for x in [pre, *(b for _, b in blocks)] if x.strip())
            return content, {**meta, "status": "fallback", "reason": reason}
        content, out_blocks = "", []
        for mid, b in blocks:
            text = b.strip()
            if content:
                content += "\n\n"
            out_blocks.append({"after": mid, "start": len(content), "end": len(content) + len(text)})
            content += text
        return content, {**meta, "status": "ok", "reason": "", "blocks": out_blocks, "reply_hash": text_hash(content)}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[«»“”\"]", "", s or "")).strip().casefold()


def composite(user_text: str, reply_text: str, meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Read-time composite for the UI, or None (classic) when anything does not match exactly."""
    if not meta or meta.get("status") != "ok" or meta.get("user_hash") != text_hash(user_text) \
            or meta.get("reply_hash") != text_hash(reply_text):
        return None
    parts = {p["id"]: user_text[p["start"]:p["end"]] for p in meta.get("parts") or []}
    after = {b["after"]: reply_text[b["start"]:b["end"]] for b in meta.get("blocks") or []}
    items: list[dict[str, Any]] = []
    for pid, text in parts.items():
        items.append({"source": "player_authored", "part": pid, "text": text.strip("\n")})
        if pid in after:
            items.append({"source": "ai_generated", "after": pid, "text": after[pid]})
    return {"items": items}
