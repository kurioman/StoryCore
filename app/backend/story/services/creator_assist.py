"""World creator, "Suggest with AI" (Phase 8.3): one short request to the player's model turns an idea into a draft.

The draft is only returned, never saved: the player reads it, changes it and saves it in the creator. The request knows
the world (its name, the start of its presentation and the names already used) so the draft fits it.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..providers.base import ChatMessage
from . import pack_editor, settings_service
from .runtime import AppContext

LANGS = {"fr": "French", "en": "English"}
PREMISE_CHARS = 1800
MAX_TOKENS = 1100

FIELDS = {
    "character": ('{"name": "...", "type": "role in the story (e.g. Captain, Student, Merchant)", "race": "species or '
                  'origin, if it matters", "title": "", "affiliation": "group or family", "appearance": "2-3 sentences",'
                  ' "personality_traits": ["4 to 6 short words"], "speech": "how they talk, one sentence", '
                  '"notes": "who they are, 2-3 sentences", "background": "their past, 2-4 sentences", '
                  '"goals": "what they want", "hidden": ["1-2 secrets known only to the narrator"]}'),
    "location": ('{"name": "...", "type": "City, Tavern, Forest, Ship...", "description": "3-5 sentences: look, mood, '
                 'who is found there", "location": "the larger place it is in, if any", '
                 '"hidden": ["1 secret about the place, known only to the narrator"]}'),
    "group": ('{"name": "...", "type": "Guild, Family, Nation, Gang, Order...", "description": "3-4 sentences", '
              '"goals": "what the group wants", "hidden": ["1 secret about the group, known only to the narrator"]}'),
    "starter": ('{"name": "short title", "purpose": "one sentence for the player: who they are and where it starts", '
                '"blueprint": "instructions to the narrator for the opening scene: where, when, who is there, what '
                'happens, one immediate choice for the player; never decide the protagonist\'s actions", '
                '"scene": {"location": "...", "time": "HH:MM"}}'),
    # v0.6 planned events: the author decides what happens, the narrator how
    "event": ('{"title": "short title", "brief": "for the narrator, 2-4 sentences: what must happen, where, who is '
              'involved and what is at stake; never how the protagonist reacts or what they decide"}'),
}
TEXTS = {
    "premise": ("the world's presentation in Markdown: a title line '# Name', then short sections (## The world, "
                "## Places, ## Powers or technology, ## Society, ## Conflicts) with a few lines each"),
    "narrator": ("the narrator's rules for this world in Markdown, as short bullet points: tone and genre, what the "
                 "narrator must respect (powers, society, technology), what to avoid, how to end a reply; at most 15 "
                 "bullets. Never decide the protagonist's words, feelings or actions"),
}
KINDS = set(FIELDS) | set(TEXTS)


def _world_brief(doc: dict[str, Any]) -> str:
    names = {
        "Characters": [c.get("name") for c in doc.get("characters") or []],
        "Places": [x.get("name") for x in doc.get("locations") or []],
        "Groups": [g.get("name") for g in doc.get("groups") or []],
        "Planned events": [e.get("title") if isinstance(e.get("title"), str) else e.get("id")
                           for e in doc.get("events") or []],
    }
    lines = [f"World: {doc.get('name', '')}"]
    if doc.get("summary"):
        lines.append(f"Pitch: {doc['summary']}")
    if (doc.get("premise") or "").strip():
        lines.append("Presentation (start):\n" + doc["premise"].strip()[:PREMISE_CHARS])
    for label, items in names.items():
        items = [n for n in items if n][:40]
        if items:
            lines.append(f"{label} already in the world: {', '.join(items)}")
    return "\n\n".join(lines)


def build_prompt(doc: dict[str, Any], kind: str, idea: str, lang: str) -> tuple[str, str]:
    language = LANGS.get(lang, "English")
    system = ("You help a player build a world for an interactive story game. Be inventive but coherent with what "
              "the world already contains. Never reuse a name that is already used for something else. Write in "
              f"{language}.")
    if kind in FIELDS:
        task = (f"Write ONE {kind} for this world from the player's idea. Answer with a single JSON object and nothing "
                f"else, with these keys (leave a value empty if it does not fit):\n{FIELDS[kind]}")
    else:
        task = f"Write {TEXTS[kind]}. Answer with the Markdown text only."
    prompt = f"{_world_brief(doc)}\n\nThe player's idea: {idea.strip() or '(no idea given: surprise the player)'}\n\n{task}"
    return system, prompt


def parse_json_object(text: str) -> dict[str, Any]:
    """The first JSON object in a model's answer (code fences, text around it and trailing commas are tolerated)."""
    t = re.sub(r"```(?:json)?", "", text or "")
    start = t.find("{")
    if start < 0:
        raise ValueError("no object")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(t[start:], start):
        if in_str:
            esc = ch == "\\" and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = re.sub(r",\s*([}\]])", r"\1", t[start:i + 1])
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    return obj
                break
    raise ValueError("no complete object")


def clean_draft(kind: str, obj: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(v, str):
            v = v.strip()
        elif isinstance(v, list):
            v = [str(x).strip() for x in v if str(x).strip()]
        elif isinstance(v, dict):
            v = {a: str(b).strip() for a, b in v.items() if str(b).strip()}
        if v not in (None, "", [], {}):
            out[str(k)] = v
    if kind == "starter" and "blueprint" not in out:
        raise ValueError("no blueprint")
    if kind == "event" and not (out.get("brief") and out.get("title")):
        raise ValueError("no brief")
    if kind not in ("starter", "event") and not out.get("name"):
        raise ValueError("no name")
    return out


async def suggest(ctx: AppContext, pid: str, kind: str, idea: str, lang: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise pack_editor.EditorError("Unknown kind of suggestion.")
    doc = pack_editor.read(ctx.settings.project_root, pid)
    with ctx.db.session() as db:
        resolved = ctx.resolve(db, settings_service.get(db, "default_model_profile_id"))
    system, prompt = build_prompt(doc, kind, idea[:1500], lang)
    text = await resolved.adapter.complete(resolved.profile.model_id, system, [ChatMessage("user", prompt)],
                                           {**resolved.params, "temperature": 0.8, "max_tokens": MAX_TOKENS})
    if kind in TEXTS:
        body = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", (text or "").strip())
        if not body:
            raise pack_editor.EditorError("The AI gave an empty answer. Try again, or with another idea.")
        return {"kind": kind, "text": body}
    try:
        return {"kind": kind, "draft": clean_draft(kind, parse_json_object(text))}
    except ValueError:
        raise pack_editor.EditorError("The AI's answer could not be read as a card. Try again (a larger model helps).")
