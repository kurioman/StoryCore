"""Slash command library: seeds and template expansion.

Commands are prompt templates and/or local app actions — never shell commands. Expansion happens on the
server at send time so the model always receives the full instructions, not just the chip label.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import SlashCommand

# v1.3: the earlier wording let models move or voice the protagonist when something happened to them during Continue
# (local eval, "being attacked" scene: mistral-nemo "you instinctively step in front of her ... you ask", qwen2.5 "you
# catch Lilia ... a chill runs down your spines"). Stored built-ins still equal to an earlier default are upgraded by seed.
CONTINUE_TEMPLATE_V1 = ("[Continue the scene] Let the world, NPCs and events already in motion carry the scene forward from where it "
                        "stopped. The protagonist takes no new deliberate action, says nothing new and makes no decision. Stop when "
                        "the protagonist needs to act or respond.\n{{input}}")
CONTINUE_TEMPLATE = ("[Continue the scene] Let the world, NPCs and events already in motion carry the scene forward from where it "
                     "stopped. The protagonist takes no new deliberate action, says nothing new, makes no decision and is given no "
                     "new thought or feeling. If something happens to the protagonist (a touch, a fall, an attack), describe it "
                     "reaching them and stop there: how they react (moving, dodging, catching, answering) is the player's choice. "
                     "Stop when the protagonist needs to act or respond.\n{{input}}")
PREVIOUS_DEFAULTS = {"continue": {CONTINUE_TEMPLATE_V1}}

SEEDS: list[dict[str, Any]] = [
    {"name": "recap", "aliases": [], "kind": "hybrid", "action": "recap", "output_target": "utility", "category": "Continuity",
     "description": "Summarise the story so far and save it as a recap candidate you can accept or edit.",
     "template": ("Summarise the story so far chronologically. Use these headings: Confirmed events; Promises; Injuries & conditions; "
                  "Important choices; Discovered facts; Unresolved mysteries; Relationship changes; Quests; Current scene. "
                  "Only include what the transcript and records establish — do not invent missing information. "
                  "Mark anything uncertain as uncertain.\n{{input}}")},
    {"name": "ooc", "aliases": ["meta"], "kind": "prompt", "action": None, "output_target": "ooc", "category": "Meta",
     "description": "Step out of character for a question, correction, lore clarification or direction.",
     "template": ("[OUT OF CHARACTER] Step outside the story and answer as the game master. Be concise and factual. If the "
                  "question concerns lore, distinguish confirmed lore from uncertain or community-reconstructed details. "
                  "Do not continue the story in this reply; the roleplay resumes when the player asks.\n\nPlayer: {{input}}")},
    {"name": "recon", "aliases": ["redcon", "reconcile"], "kind": "hybrid", "action": "recon", "output_target": "utility",
     "category": "Continuity",
     "description": "Continuity reconciliation: compare recent transcript with avatar, notes, memories, state and lore; list contradictions and fixes.",
     "template": ("Compare the recent transcript against the avatar profile, notes, memories, relationships, stats, inventory and "
                  "known lore provided in context. List each contradiction with: what conflicts, the source records involved, "
                  "and a suggested fix. Do not retcon anything yourself.\n{{input}}")},
    {"name": "addlore", "aliases": ["canon"], "kind": "local_action", "action": "addlore", "output_target": "utility",
     "category": "Lore", "description": "Capture a new fact as a local-canon candidate (requires your approval).", "template": "{{input}}"},
    {"name": "nsfw", "aliases": ["content"], "kind": "local_action", "action": "content_prefs", "output_target": "utility",
     "category": "Settings",
     "description": "Open this story's content preferences (tone, intensity, fade-to-black). Provider policies still apply.",
     "template": ""},
    {"name": "story", "aliases": ["next"], "kind": "prompt", "action": None, "output_target": "chat", "category": "Narrative",
     "description": "Create a plausible next situation that advances existing threads before introducing new plot.",
     "template": ("Create a plausible next situation based on the current scene, location, open quests and unresolved threads. "
                  "Advance existing threads before introducing a major new plot. Do not decide the protagonist's actions, "
                  "dialogue or feelings. End at a point where the player can act.\n{{input}}")},
    {"name": "continue", "aliases": ["cont"], "kind": "prompt", "action": None, "output_target": "chat", "category": "Narrative",
     "description": "Continue the scene without the protagonist taking a new deliberate action.",
     "template": CONTINUE_TEMPLATE},
    {"name": "scene", "aliases": [], "kind": "local_action", "action": "scene", "output_target": "utility", "category": "Scene",
     "description": "Inspect or edit scene metadata: time, location, weather, mood and attendees.", "template": ""},
    {"name": "state", "aliases": ["status"], "kind": "local_action", "action": "state", "output_target": "utility",
     "category": "Scene", "description": "Open the player/NPC state inspector and optionally ask the model to propose changes.",
     "template": ""},
    {"name": "lore", "aliases": ["search"], "kind": "local_action", "action": "lore_search", "output_target": "utility",
     "category": "Lore", "description": "Search the imported lore library and local canon (results show source/confidence).",
     "template": "{{input}}"},
    {"name": "meanwhile", "aliases": ["cutaway"], "kind": "prompt", "action": None, "output_target": "chat", "category": "Narrative",
     "description": "Narrate a brief cutaway from an NPC or faction perspective, limited to what that viewpoint knows.",
     "template": ("Narrate a brief cutaway (1–3 paragraphs) away from the protagonist, from the perspective named below or a "
                  "plausible NPC/faction. Strictly limit it to what that viewpoint knows; do not reveal secrets they have no "
                  "way of knowing, and do not reveal information the protagonist could not later discover. Then return to the "
                  "protagonist's scene without acting for them.\nViewpoint / focus: {{input}}")},
    {"name": "undo", "aliases": [], "kind": "local_action", "action": "undo", "output_target": "utility", "category": "Tools",
     "description": "Undo the last accepted state change (with confirmation).", "template": ""},
    {"name": "journal", "aliases": ["events"], "kind": "local_action", "action": "journal", "output_target": "utility",
     "category": "Continuity", "description": "Open the event timeline, or create a manual event from your text.", "template": "{{input}}"},
    {"name": "memory", "aliases": ["mem", "remember"], "kind": "local_action", "action": "memory", "output_target": "utility",
     "category": "Continuity", "description": "Search, pin, edit or create a durable memory/fact.", "template": "{{input}}"},
    {"name": "savepoint", "aliases": ["save"], "kind": "local_action", "action": "savepoint", "output_target": "utility",
     "category": "Tools", "description": "Create a named snapshot of this branch, its state, journal and memories.", "template": "{{input}}"},
    {"name": "chapter", "aliases": ["chapitre"], "kind": "local_action", "action": "chapter", "output_target": "utility",
     "category": "Continuity",
     "description": "Close the current chapter of the AI's memory now (optional title): the latest messages are summarised.",
     "template": "{{input}}"},
    {"name": "continuity", "aliases": ["check"], "kind": "hybrid", "action": "continuity", "output_target": "utility",
     "category": "Continuity",
     "description": "Check the current scene/state against recent events, memories and lore; propose fixes without retconning.",
     "template": ("Check the current scene and state against recent events, durable memories and source lore in context. List "
                  "inconsistencies (with the records involved) and propose fixes. Do not silently retcon.\n{{input}}")},
]


def seed(db: Session) -> int:
    builtins = {c.name: c for c in db.scalars(select(SlashCommand).where(SlashCommand.builtin.is_(True)))}
    n = 0
    for s in SEEDS:
        if s["name"] in builtins:
            cur = builtins[s["name"]]
            # upgrade an untouched built-in to the improved default; a template the user edited is never overwritten
            if cur.template in PREVIOUS_DEFAULTS.get(s["name"], set()) and cur.template != s["template"]:
                cur.template = s["template"]
            continue
        db.add(SlashCommand(name=s["name"], aliases_json=s["aliases"], description=s["description"], template=s["template"],
                            kind=s["kind"], action=s["action"], output_target=s["output_target"], scope="global",
                            category=s["category"], builtin=True, pinned=s["name"] in ("recap", "ooc", "story")))
        n += 1
    db.flush()
    return n


def visible(db: Session, story_id: str | None) -> list[SlashCommand]:
    q = select(SlashCommand).where(or_(SlashCommand.scope == "global", SlashCommand.story_id == story_id))
    return list(db.scalars(q.order_by(SlashCommand.pinned.desc(), SlashCommand.name)))


def find(db: Session, story_id: str | None, name: str) -> SlashCommand | None:
    n = name.lstrip("/").lower()
    cmds = visible(db, story_id)
    # story-scoped commands take precedence over global ones with the same name
    for c in sorted(cmds, key=lambda c: c.scope != "story"):
        if c.enabled and (c.name.lower() == n or n in [a.lower() for a in c.aliases_json or []]):
            return c
    return None


def expand(template: str, user_input: str, ctx: dict[str, str] | None = None) -> str:
    ctx = dict(ctx or {})
    ctx["input"] = user_input.strip()
    out = re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: ctx.get(m.group(1), ""), template or "")
    if "{{input}}" not in (template or "") and "{{ input }}" not in (template or "") and user_input.strip():
        out = f"{out}\n\n{user_input.strip()}"  # never drop the user's free text
    return out.strip()
