from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import SlashCommand, now_iso
from ..services import commands as commands_svc
from ..services import state_service, story_tree

router = APIRouter(tags=["commands"])
NAME_RE = r"^[a-z0-9][a-z0-9_\-]{0,40}$"


@router.get("/commands")
def list_commands(story_id: Optional[str] = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"commands": [c.to_dict() for c in commands_svc.visible(db, story_id)]}


class CommandIn(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    template: str = ""
    kind: str = "prompt"
    action: Optional[str] = None
    output_target: str = "chat"
    scope: str = "global"
    story_id: Optional[str] = None
    pinned: bool = False
    category: str = "Custom"
    enabled: bool = True


def _validate(db: Session, body: CommandIn, exclude_id: str | None = None) -> None:
    import re

    names = [body.name.lower()] + [a.lower() for a in body.aliases]
    for n in names:
        if not re.match(NAME_RE, n):
            raise ValueError(f"'/{n}' is not a valid command name (lowercase letters, digits, - and _).")
    if body.kind not in ("prompt", "local_action", "hybrid"):
        raise ValueError("kind must be prompt, local_action or hybrid")
    if body.output_target not in ("chat", "utility", "ooc"):
        raise ValueError("output_target must be chat, utility or ooc")
    if body.scope == "story" and not body.story_id:
        raise ValueError("Story-scoped commands need a story")
    for c in commands_svc.visible(db, body.story_id):
        if c.id == exclude_id or c.scope != body.scope:
            continue
        taken = {c.name.lower(), *[a.lower() for a in c.aliases_json or []]}
        clash = taken & set(names)
        if clash:
            raise ValueError(f"/{clash.pop()} is already used by /{c.name}.")
    if len(body.template) > 20_000:
        raise ValueError("Template is limited to 20,000 characters.")


@router.post("/commands")
def create_command(body: CommandIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _validate(db, body)
    c = SlashCommand(name=body.name.lower(), aliases_json=[a.lower() for a in body.aliases], description=body.description,
                     template=body.template, kind=body.kind, action=body.action, output_target=body.output_target,
                     scope=body.scope, story_id=body.story_id if body.scope == "story" else None, pinned=body.pinned,
                     category=body.category, enabled=body.enabled, builtin=False)
    db.add(c)
    db.flush()
    return c.to_dict()


@router.put("/commands/{cid}")
def update_command(cid: str, body: CommandIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(SlashCommand, cid)
    if c is None:
        raise HTTPException(404, "Command not found")
    _validate(db, body, exclude_id=cid)
    if c.builtin and (body.kind != c.kind or (body.action or None) != (c.action or None)):
        raise ValueError("Built-in commands keep their action type; you can edit the prompt, aliases, scope and output target.")
    c.name, c.aliases_json, c.description, c.template = body.name.lower(), [a.lower() for a in body.aliases], body.description, body.template
    c.output_target, c.scope, c.story_id = body.output_target, body.scope, body.story_id if body.scope == "story" else None
    c.pinned, c.category, c.enabled, c.updated_at = body.pinned, body.category, body.enabled, now_iso()
    if not c.builtin:
        c.kind, c.action = body.kind, body.action
    return c.to_dict()


@router.delete("/commands/{cid}")
def delete_command(cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(SlashCommand, cid)
    if c is None:
        raise HTTPException(404, "Command not found")
    if c.builtin:
        raise ValueError("Built-in commands can be disabled or edited, but not deleted. Use 'Reset' to restore defaults.")
    db.delete(c)
    return {"ok": True}


@router.post("/commands/{cid}/duplicate")
def duplicate_command(cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(SlashCommand, cid)
    if c is None:
        raise HTTPException(404, "Command not found")
    base = f"{c.name}-copy"
    name, i = base, 2
    existing = {x.name for x in db.scalars(select(SlashCommand))}
    while name in existing:
        name, i = f"{base}{i}", i + 1
    d = SlashCommand(name=name, aliases_json=[], description=c.description, template=c.template,
                     kind="prompt" if c.kind == "local_action" else c.kind, action=None if c.kind != "hybrid" else c.action,
                     output_target=c.output_target, scope=c.scope, story_id=c.story_id, category=c.category, builtin=False)
    if c.kind == "hybrid":
        d.kind, d.action = "prompt", None
    db.add(d)
    db.flush()
    return d.to_dict()


@router.post("/commands/{cid}/reset")
def reset_command(cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(SlashCommand, cid)
    if c is None or not c.builtin:
        raise HTTPException(404, "Built-in command not found")
    seed = next((s for s in commands_svc.SEEDS if s["action"] == c.action and s["kind"] == c.kind and
                 (s["action"] or s["name"] == c.name or s["template"][:30] == c.template[:30])), None)
    seed = seed or next((s for s in commands_svc.SEEDS if s["name"] == c.name), None)
    if seed is None:
        raise ValueError("No default found for this command.")
    c.name, c.aliases_json, c.description, c.template = seed["name"], seed["aliases"], seed["description"], seed["template"]
    c.output_target, c.scope, c.story_id, c.enabled = seed["output_target"], "global", None, True
    return c.to_dict()


class ExpandIn(BaseModel):
    command_id: Optional[str] = None
    name: Optional[str] = None
    input: str = ""
    story_id: Optional[str] = None


@router.post("/commands/expand")
def expand(body: ExpandIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(SlashCommand, body.command_id) if body.command_id else commands_svc.find(db, body.story_id, body.name or "")
    if c is None:
        raise HTTPException(404, "Command not found")
    ctx: dict[str, str] = {}
    if body.story_id:
        s = story_tree.get_story(db, body.story_id)
        st = state_service.current(db, s.active_branch_id)
        sj = st.state_json if st else {}
        ctx = {"location": (sj.get("scene") or {}).get("location", ""), "player_name": (sj.get("player") or {}).get("name", "")}
    return {"command": c.to_dict(), "expansion": commands_svc.expand(c.template, body.input, ctx),
            "sends_to_model": c.kind in ("prompt", "hybrid")}


@router.get("/commands/export")
def export_commands(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(SlashCommand).where(SlashCommand.builtin.is_(False)))
    return {"format": "storycore-commands", "format_version": 1, "exported_at": now_iso(),
            "commands": [{k: v for k, v in c.to_dict().items() if k not in ("id", "story_id", "created_at", "updated_at")} for c in rows]}


@router.post("/commands/import")
def import_commands(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.get("format") not in ("storycore-commands", "lumencia-commands"):
        raise ValueError("Not a StoryCore command library file.")
    added, skipped = 0, []
    for raw in body.get("commands", []):
        ci = CommandIn(name=raw.get("name", ""), aliases=raw.get("aliases_json") or raw.get("aliases") or [],
                       description=raw.get("description", ""), template=raw.get("template", ""),
                       kind=raw.get("kind", "prompt") if raw.get("kind") != "local_action" else "prompt",
                       output_target=raw.get("output_target", "chat"), category=raw.get("category", "Imported"),
                       pinned=bool(raw.get("pinned")))
        try:
            _validate(db, ci)
        except ValueError as e:
            skipped.append(f"/{ci.name}: {e}")
            continue
        db.add(SlashCommand(name=ci.name.lower(), aliases_json=ci.aliases, description=ci.description, template=ci.template,
                            kind=ci.kind, output_target=ci.output_target, category=ci.category, pinned=ci.pinned, builtin=False))
        db.flush()
        added += 1
    return {"added": added, "skipped": skipped}
