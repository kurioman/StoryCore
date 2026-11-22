from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db, sse
from ..models import (Avatar, LoreEntity, Message, MessageBranch, MessageVersion, ModelProfile, Provider, SlashCommand,
                      LocalCanon, Story, UserNote, World, now_iso)
from ..services import assets as assets_svc
from ..services import world_pack
from ..services import backup as backup_svc
from ..services import context_builder, savepoints, settings_service, state_service, story_tree, turns, world_state
from ..services.entities import build_index
from ..services.runtime import AppContext, story_params

router = APIRouter(tags=["stories"])


def story_out(db: Session, s: Story) -> dict[str, Any]:
    d = s.to_dict()
    d.pop("avatar_snapshot_json", None)
    world = db.get(World, s.world_id) if s.world_id else None
    av = db.get(Avatar, s.active_avatar_id) if s.active_avatar_id else None
    last = db.scalar(select(Message).where(Message.story_id == s.id, Message.deleted_at.is_(None)).order_by(Message.created_at.desc()).limit(1))
    d["world_name"] = world.name if world else None
    d["avatar_name"] = av.name if av else None
    d["avatar_portrait"] = av.portrait_path if av else None
    d["last_activity"] = last.created_at if last else s.updated_at
    d["last_snippet"] = (last.content[:140] if last else "")
    d["message_count"] = db.scalar(select(func.count()).select_from(Message).where(Message.story_id == s.id, Message.deleted_at.is_(None))) or 0
    return d


@router.get("/stories")
def list_stories(q: str = "", status: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    query = select(Story).order_by(Story.updated_at.desc())
    if status:
        query = query.where(Story.status == status)
    rows = [story_out(db, s) for s in db.scalars(query)]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["title"].lower() or ql in (r["world_name"] or "").lower()]
    return {"stories": rows}


class StoryCreate(BaseModel):
    title: str
    world_id: Optional[str] = None
    avatar_id: Optional[str] = None
    starter_id: Optional[str] = None
    starter_blueprint: Optional[str] = None
    starting_location: Optional[str] = None
    starting_time: Optional[str] = None
    tone: Optional[str] = None
    pacing: Optional[str] = None
    output_length: Optional[str] = settings_service.DEFAULT_OUTPUT_LENGTH  # "" = the model's own default
    max_tokens: Optional[int] = settings_service.DEFAULT_MAX_OUTPUT_TOKENS  # None = the model profile's own limit
    agency_policy: Optional[str] = None  # optional extra text; the built-in player-agency rules always apply
    content_prefs: dict[str, Any] = Field(default_factory=dict)
    model_profile_id: Optional[str] = None
    preset_id: str = "cinematic"  # v0.6: settings_service.DEFAULT_PRESET_ID
    stat_template: str = "world"
    featured_characters: list[str] = Field(default_factory=list)
    story_note: str = ""


def check_max_tokens(v: Any) -> None:
    if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 16 <= v <= 32000):
        raise ValueError("Max output tokens must be a whole number from 16 to 32000.")


@router.post("/stories")
def create_story(body: StoryCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    check_max_tokens(body.max_tokens)
    if body.world_id and db.get(World, body.world_id) is None:
        raise ValueError("Unknown world")
    av = db.get(Avatar, body.avatar_id) if body.avatar_id else None
    if body.avatar_id and av is None:
        raise ValueError("Unknown avatar")
    starter: dict[str, Any] = {}
    if body.starter_id:
        world = db.get(World, body.world_id) if body.world_id else None
        starters = (world.data_json or {}).get("starters", []) if world else []
        starter = next((s for s in starters if s.get("id") == body.starter_id), None) or {}
    blueprint = body.starter_blueprint or starter.get("blueprint")
    s = Story(title=body.title.strip() or "Untitled story", world_id=body.world_id, active_avatar_id=av.id if av else None,
              avatar_snapshot_json={"name": av.name, "profile": av.profile_json} if av else None,
              settings_json={k: v for k, v in {
                  "starter_id": body.starter_id, "starter_blueprint": blueprint, "tone": body.tone, "pacing": body.pacing,
                  "output_length": body.output_length, "max_tokens": body.max_tokens, "agency_policy": body.agency_policy,
                  "content_prefs": body.content_prefs,
                  "model_profile_id": body.model_profile_id, "preset_id": body.preset_id,
                  "featured_characters": body.featured_characters, "use_world_prompt": True}.items() if v not in (None, "", [], {})})
    db.add(s)
    db.flush()
    b = MessageBranch(story_id=s.id, label="Main")
    db.add(b)
    db.flush()
    s.active_branch_id = b.id
    st = state_service.default_state(body.stat_template)
    # "world" (the default choice): the world's own stat sheet (pack.json → stats), or Fantasy basics when it has none.
    # "lumencia" is what older versions of the app sent for the same thing. Any other choice the player made is kept.
    pack_stats = world_pack.section(db, body.world_id, "stats") if body.stat_template in ("world", "lumencia") else None
    if pack_stats:
        st["stats"] = state_service.stats_from(pack_stats)
    st["scene"]["location"] = body.starting_location or ""
    st["scene"]["time"] = body.starting_time or ""
    if body.world_id and body.starting_location:
        le = db.scalar(select(LoreEntity).where(LoreEntity.world_id == body.world_id, LoreEntity.category == "location",
                                                LoreEntity.name == body.starting_location))
        st["scene"]["location_id"] = le.entity_id if le else None
    if body.featured_characters:
        st["scene"]["present"] = list(body.featured_characters)
    # the opening's own scene (pack.json starters[].scene): fills only what the player left empty
    for k, v in world_state.starter_scene(starter.get("scene")).items():
        if not st["scene"].get(k):
            st["scene"][k] = v
    if av:
        st["player"]["name"] = av.profile_json.get("display_name") or av.name
        st["player"]["title"] = av.profile_json.get("title", "")
        if av.profile_json.get("stats"):
            st["stats"] = [dict(x) for x in av.profile_json["stats"]]
        for it in av.profile_json.get("inventory") or []:
            st["inventory"].append(dict(it))
    state_service.save(db, s.id, b.id, st, source="manual", summary="Story created")
    db.add(UserNote(scope="story", story_id=s.id, content=body.story_note, enabled=True))
    return story_out(db, s)


class StoryPatch(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    settings: Optional[dict[str, Any]] = None
    world_id: Optional[str] = None


@router.get("/stories/{sid}")
def get_story(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    out = story_out(db, s)
    out["branches"] = branches_out(db, s)
    return out


@router.patch("/stories/{sid}")
def patch_story(sid: str, body: StoryPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    if body.title is not None:
        s.title = body.title.strip()[:300] or s.title
    if body.status is not None:
        if body.status not in ("active", "archived", "template"):
            raise ValueError("Invalid status")
        s.status = body.status
        s.archived_at = now_iso() if body.status == "archived" else None
    if body.settings is not None:
        merged = dict(s.settings_json or {})
        from ..services import immersive, relationships
        if body.settings.get("relationship_difficulty") not in (None, *relationships.DIFFICULTY):
            raise ValueError("relationship_difficulty must be relaxed, normal or strict")
        if body.settings.get("narrative_presentation") not in (None, *immersive.MODES):
            raise ValueError("narrative_presentation must be classic or immersive")
        check_max_tokens(body.settings.get("max_tokens"))
        for k, v in body.settings.items():
            if k == "expressions":
                continue  # managed by the expressions endpoint
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v
        s.settings_json = merged
    if body.world_id is not None:
        s.world_id = body.world_id or None
    s.updated_at = now_iso()
    return story_out(db, s)


@router.delete("/stories/{sid}")
def delete_story(sid: str, confirm: bool = False, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Deleting a story requires confirmation.")
    s = story_tree.get_story(db, sid)
    # safety net: keep a recovery package of the deleted story (avatars, global notes, providers, lore are untouched)
    out_dir = ctx.settings.backups_dir / "deleted_stories"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", s.title)[:40]
    pkg = out_dir / f"{safe}_{now_iso()[:19].replace(':', '-')}.zip"
    backup_svc.export_story(db, sid, ctx.settings.uploads_dir, pkg)
    for model in (UserNote, LocalCanon, SlashCommand):
        for r in db.scalars(select(model).where(model.story_id == sid)):
            db.delete(r)
    db.delete(s)
    return {"ok": True, "recovery_package": str(pkg)}


@router.post("/stories/{sid}/duplicate")
def duplicate_story(sid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    story_tree.get_story(db, sid)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "dup.zip"
        backup_svc.export_story(db, sid, ctx.settings.uploads_dir, p)
        new_id = backup_svc.import_story(db, p, ctx.settings.uploads_dir, title_suffix=" (copy)")
    s = db.get(Story, new_id)
    # duplicates keep using the original avatar rather than an "(imported)" copy
    orig = db.get(Story, sid)
    dup_av = db.get(Avatar, s.active_avatar_id) if s.active_avatar_id else None
    if dup_av is not None and orig.active_avatar_id:
        s.active_avatar_id = orig.active_avatar_id
        db.delete(dup_av)
    return story_out(db, s)


# --------------------------------------------------------------------------- avatar binding
class AvatarSwitch(BaseModel):
    avatar_id: Optional[str]
    confirm: bool = False


@router.post("/stories/{sid}/avatar")
def switch_avatar(sid: str, body: AvatarSwitch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    has_msgs = db.scalar(select(func.count()).select_from(Message).where(Message.story_id == sid)) or 0
    if has_msgs and not body.confirm:
        raise ValueError("Switching the avatar mid-story affects continuity; confirmation required.")
    av = db.get(Avatar, body.avatar_id) if body.avatar_id else None
    if body.avatar_id and av is None:
        raise ValueError("Unknown avatar")
    branch = story_tree.get_branch(db, s)
    savepoints.create(db, s, branch, label="Before avatar switch", kind="auto", reason="avatar switch")
    s.active_avatar_id = av.id if av else None
    s.avatar_snapshot_json = {"name": av.name, "profile": av.profile_json} if av else None
    return story_out(db, s)


# --------------------------------------------------------------------------- branches
def branches_out(db: Session, s: Story) -> list[dict[str, Any]]:
    out = []
    for b in db.scalars(select(MessageBranch).where(MessageBranch.story_id == s.id).order_by(MessageBranch.created_at)):
        head = db.get(Message, b.head_message_id) if b.head_message_id else None
        out.append({"id": b.id, "label": b.label, "archived": b.archived, "parent_branch_id": b.parent_branch_id,
                    "fork_message_id": b.fork_message_id, "head_message_id": b.head_message_id,
                    "head_seq": head.seq if head else -1, "head_preview": head.content[:100] if head else "",
                    "active": b.id == s.active_branch_id, "created_at": b.created_at})
    return out


@router.get("/stories/{sid}/branches")
def list_branches(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"branches": branches_out(db, story_tree.get_story(db, sid))}


class BranchPatch(BaseModel):
    label: Optional[str] = None
    archived: Optional[bool] = None


@router.patch("/stories/{sid}/branches/{bid}")
def patch_branch(sid: str, bid: str, body: BranchPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s, bid)
    if body.label is not None:
        b.label = body.label[:200]
    if body.archived is not None:
        if body.archived and b.id == s.active_branch_id:
            raise ValueError("Switch to another branch before archiving this one.")
        b.archived = body.archived
    return {"branches": branches_out(db, s)}


@router.post("/stories/{sid}/branches/{bid}/activate")
def activate_branch(sid: str, bid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    cur = story_tree.get_branch(db, s)
    if ctx.generations.active_for_branch(cur.id):
        raise ValueError("Stop the current generation before switching branches.")
    b = story_tree.get_branch(db, s, bid)
    s.active_branch_id = b.id
    b.archived = False
    return {"branches": branches_out(db, s)}


@router.delete("/stories/{sid}/branches/{bid}")
def delete_branch(sid: str, bid: str, confirm: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Branches are archived, not destroyed: their messages may be shared with other branches."""
    if not confirm:
        raise ValueError("Removing a branch requires confirmation.")
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s, bid)
    if b.id == s.active_branch_id:
        raise ValueError("Switch to another branch first.")
    savepoints.create(db, s, b, label=f"Before removing branch '{b.label}'", kind="auto", reason="branch removal")
    b.archived = True
    return {"branches": branches_out(db, s), "note": "Branch archived; a recovery savepoint was created."}


@router.post("/stories/{sid}/messages/{mid}/branch")
def branch_from(sid: str, mid: str, body: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    nb = turns.branch_from(db, sid, mid, (body or {}).get("label"))
    return {"branch_id": nb.id, "branches": branches_out(db, story_tree.get_story(db, sid))}


# --------------------------------------------------------------------------- messages
def message_out(db: Session, m: Message, alt: dict[str, Any] | None = None) -> dict[str, Any]:
    d = m.to_dict()
    md = d.get("generation_metadata_json") or {}
    d["generation"] = {k: md.get(k) for k in ("provider_name", "provider_type", "model_id", "started_at", "finished_at",
                                               "duration_s", "approx_output_tokens", "error", "mood_suggestions",
                                               "mentioned_characters", "lore_conflicts", "immersive", "usage", "diagnostics",
                                               # v0.6: the notices under a reply (repetition B9, dead speaker, time
                                               # going back, pinned memory) were never sent to the screen
                                               "continuity_alerts")}
    info = md.get("info_table")
    if isinstance(info, dict):  # phase 2 (step 4): the lines of the info block, shown under the reply
        d["generation"]["info_table"] = {"lines": info.get("lines") or [], "edited_by_player": bool(info.get("edited_by_player"))}
    d.pop("generation_metadata_json", None)
    d["has_context"] = "context" in md
    d["version_count"] = db.scalar(select(func.count()).select_from(MessageVersion).where(MessageVersion.message_id == m.id)) or 0
    if alt:
        d["alternatives"] = alt
    return d


@router.get("/stories/{sid}/messages")
def list_messages(sid: str, include_deleted: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    path = story_tree.path_messages(db, b.head_message_id, include_deleted=True)
    out = []
    deleted = 0
    for m in path:
        if m.deleted_at and not include_deleted:
            deleted += 1
            continue
        alt = None
        if m.role == "assistant":
            sib = [x for x in story_tree.siblings(db, m) if x.role == "assistant"]
            if len(sib) > 1:
                alt = {"ids": [x.id for x in sib], "index": [x.id for x in sib].index(m.id) if m.id in [x.id for x in sib] else 0,
                       "leaf": [not story_tree.has_children(db, x.id) for x in sib]}
        out.append(message_out(db, m, alt))
    _attach_presentation(db, s, b, path, out)
    _attach_immersive(out)
    from ..services import chrono, world_state
    chrono.attach(db, s, [m for m in path if include_deleted or not m.deleted_at], out)
    cal = world_state.calendar_of(db, s.world_id)
    return {"messages": out, "branch_id": b.id, "deleted_hidden": deleted,
            "chronology": {"year_label": cal["year_label"], "year_start": cal["year_start"], "provenance": cal["provenance"]}}


def _attach_immersive(out: list[dict[str, Any]]) -> None:
    """v1.5 immersive view: the player's parts (sliced from the stored user message) interleaved with the reaction blocks
    (sliced from the stored reply). Only when both texts are unchanged since generation; the user message is then marked
    as shown inside the composite, so its text appears once in the reading flow (the raw message stays inspectable)."""
    from ..services import immersive

    by_id = {d["id"]: d for d in out}
    for d in out:
        meta = ((d.get("generation") or {}) if isinstance(d.get("generation"), dict) else {}).get("immersive")
        if d.get("role") != "assistant" or not meta or d.get("deleted_at"):
            continue
        user = by_id.get(meta.get("user_message_id") or "")
        if user is None or user.get("deleted_at"):
            continue
        comp = immersive.composite(user.get("content") or "", d.get("content") or "", meta)
        if comp:
            d["immersive"] = comp
            user["immersive_reply_id"] = d["id"]


def _attach_presentation(db: Session, s, b, path: list[Message], out: list[dict[str, Any]]) -> None:
    """Inline portraits and dialogue styling for analysed replies (v1.3): only validated data from scene analysis —
    known character ids, verified text anchors/dialogue substrings, local portrait asset ids. Never model-provided
    paths or HTML. A reply edited after its analysis gets nothing (the anchors may no longer exist)."""
    from ..models import TurnAnalysis

    ids = [m.id for m in path if m.role == "assistant"]
    if not ids:
        return
    rows = {r.message_id: r for r in db.scalars(select(TurnAnalysis).where(TurnAnalysis.message_id.in_(ids),
                                                                            TurnAnalysis.status == "succeeded"))}
    if not rows:
        return
    from ..services import canon as canon_svc, identity, roles, turn_analysis

    st_row = state_service.current(db, b.id)
    index = build_index(db, s.world_id, state_service.normalize(st_row.state_json if st_row else {}))
    pmap = assets_svc.portrait_map(db, s.world_id)
    edited = {m.id: m.edited_at for m in path}
    registry = roles.build_registry(db, s.world_id, index)
    canon = canon_svc.facts(db, s.world_id, index)
    for d in out:
        r = rows.get(d["id"])
        if r is None or (edited.get(d["id"]) and (r.updated_at or "") < edited[d["id"]]):
            continue
        beats = []
        for bt in turn_analysis.visible_beats(r.beats_json):
            cid = bt.get("character_id")
            if cid not in index.entities:
                continue
            asset_id, used, fallback = assets_svc.resolve_expression(pmap.get(cid, {}), int(bt.get("expression") or 1))
            beats.append({"character_id": cid, "name": index.name(cid), "expression": int(bt.get("expression") or 1),
                          "beat": bt.get("beat"), "paragraph": bt.get("paragraph"), "asset_id": asset_id,
                          "slot_used": used, "is_fallback": fallback})
        dialogue = [x for x in (r.dialogue_json or []) if x.get("character_id") in index.entities and x.get("text")]
        # v1.5 reading aid: who speaks in each quoted paragraph, limited to the speakers the analysis verified
        speakers = {sp.get("character_id") for sp in r.speakers_json or []}
        named = identity.resolver(index, registry, canon, speakers | set(turn_analysis.cast_of(r.beats_json)["present"]))
        paragraphs = [{**a, "name": index.name(a["character_id"]) if a["character_id"] not in (None, "protagonist") else None}
                      for a in turn_analysis.attribute_dialogue(d.get("content") or "", index, speakers, named, dialogue)] if speakers else []
        if beats or dialogue or paragraphs:
            d["presentation"] = {"beats": beats, "dialogue": dialogue, "paragraphs": paragraphs}


class SendIn(BaseModel):
    content: str = ""
    command: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None


@router.post("/stories/{sid}/turns")
def send_turn(sid: str, body: SendIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    return turns.send(ctx, db, sid, content=body.content, command=body.command, request_id=body.request_id)


@router.post("/stories/{sid}/start")
def start_story(sid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Generate the opening scene from the story's starter blueprint."""
    s = story_tree.get_story(db, sid)
    if db.scalar(select(func.count()).select_from(Message).where(Message.story_id == sid)):
        raise ValueError("This story has already started.")
    cfg = s.settings_json or {}
    parts: list[str] = []
    st_row = state_service.current(db, s.active_branch_id)
    sc = (st_row.state_json if st_row else {}).get("scene", {})
    if sc.get("location"):
        parts.append(f"Starting location: {sc['location']}.")
    if sc.get("time"):
        parts.append(f"Starting time: {sc['time']}.")
    if cfg.get("featured_characters"):
        idx = build_index(db, s.world_id, {})
        parts.append("Featured characters: " + ", ".join(idx.name(c) for c in cfg["featured_characters"]) + ".")
    # the blueprint comes last: an opening that quotes the author's text (e.g. a prologue) must end the request, or
    # small models copy whatever follows it into the scene
    parts.append("Do not decide the protagonist's dialogue, feelings or actions.")
    if s.world_id and settings_service.get(db, "portrait_tags_enabled"):
        # small models copy the transcript's habits: the first reply must already use the portrait tags
        parts.append("Use portrait tags from the very first spoken line, before the quotation marks, e.g. [Name:2] \"Hello.\"")
    blueprint = cfg.get("starter_blueprint") or "Open the story with a concrete scene and an immediate situation for the player."
    expansion = "[STORY START] " + " ".join(parts) + "\n\n" + blueprint
    branch = story_tree.get_branch(db, s)
    ctx.resolve(db, ctx.story_profile_id(db, s))
    user = story_tree.append_message(db, s, branch, role="user", content="Begin the story.",
                                     command_json={"name": "start", "expansion": expansion, "output_target": "chat"})
    ph = story_tree.append_message(db, s, branch, role="assistant", content="", status="streaming")
    manifest = turns._start_generation(ctx, db, s, branch, ph)
    return {"user_message_id": user.id, "assistant_message_id": ph.id, "context": manifest}


def _reconcile(db: Session, sid: str, mid: str, *, edited: bool = False) -> None:
    """Automatic relationship and world-state changes follow their source reply: revert those whose reply just left the
    story (or whose text was edited). Approved changes stay (they are flagged in the character view instead)."""
    from ..services import relationships, scene_cast, world_state

    m = db.get(Message, mid)
    if m is None:
        return
    story = story_tree.get_story(db, sid)
    branch = story_tree.get_branch(db, story, m.branch_id)
    relationships.reconcile(db, story, branch, also={mid} if edited else None)
    world_state.reconcile(db, story, branch, also={mid} if edited else None)
    scene_cast.reconcile(db, story, branch, also={mid} if edited else None)


@router.post("/stories/{sid}/messages/{mid}/regenerate")
def regenerate(sid: str, mid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    return turns.regenerate(ctx, db, sid, mid)  # reconciles relationships before the new reply starts


@router.post("/stories/{sid}/messages/{mid}/select")
def select_alt(sid: str, mid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    turns.select_alternative(db, sid, mid)
    _reconcile(db, sid, mid)
    return {"ok": True}


class EditIn(BaseModel):
    content: str


@router.patch("/stories/{sid}/messages/{mid}")
def edit_message(sid: str, mid: str, body: EditIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = turns.edit(db, sid, mid, body.content)
    _reconcile(db, sid, mid, edited=m.role == "assistant")
    return message_out(db, m)


class RewriteIn(BaseModel):
    paragraph: int
    instruction: str = ""
    keep: Optional[str] = None  # the proposal the player keeps: saved as an edit of the message


@router.post("/stories/{sid}/messages/{mid}/rewrite")
async def rewrite_paragraph(sid: str, mid: str, body: RewriteIn, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    """v0.6.2: propose a new version of one paragraph of a reply (``keep`` empty), or save the one the player keeps."""
    from ..services import rewrite
    if body.keep is None:
        return await rewrite.propose(ctx, sid, mid, body.paragraph, body.instruction)
    with ctx.db.session() as db:
        m = db.get(Message, mid)
        if m is None or m.story_id != sid or m.role != "assistant":
            raise HTTPException(404, "Message not found")
        if not 0 <= body.paragraph < len(rewrite.split(m.content or "")) or not body.keep.strip():
            raise HTTPException(400, "That paragraph does not exist.")
        m = turns.edit(db, sid, mid, rewrite.replace(m.content, body.paragraph, body.keep))
        _reconcile(db, sid, mid, edited=True)
        return message_out(db, m)


class InfoLineIn(BaseModel):
    line: int
    value: Optional[str] = None  # None: the line is cancelled


@router.post("/stories/{sid}/messages/{mid}/info")
def edit_info_line(sid: str, mid: str, body: InfoLineIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Phase 2 (step 4): the player cancels or corrects one line of a reply's info table."""
    from ..services import info_table
    m = db.get(Message, mid)
    if m is None or m.story_id != sid or m.role != "assistant":
        raise HTTPException(404, "Message not found")
    try:
        info_table.edit_line(db, story_tree.get_story(db, sid), m, body.line, body.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return message_out(db, m)


@router.delete("/stories/{sid}/messages/{mid}")
def delete_message(sid: str, mid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    m0 = db.get(Message, mid)
    if m0 is not None and m0.story_id == sid and (m0.generation_metadata_json or {}).get("info_table"):
        from ..services import info_table  # phase 2: what the deleted reply's info block changed leaves with it
        st = story_tree.get_story(db, sid)
        info_table.revert(db, st, story_tree.get_branch(db, st, m0.branch_id), m0, f"message #{m0.seq} was deleted")
    m = turns.delete(db, sid, mid)
    _reconcile(db, sid, mid)
    return message_out(db, m)


@router.post("/stories/{sid}/messages/{mid}/restore")
def restore_message(sid: str, mid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return message_out(db, turns.undelete(db, sid, mid))


@router.get("/stories/{sid}/messages/{mid}/versions")
def message_versions(sid: str, mid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(MessageVersion).where(MessageVersion.message_id == mid).order_by(MessageVersion.created_at.desc()))
    return {"versions": [r.to_dict() for r in rows]}


@router.post("/stories/{sid}/messages/{mid}/versions/{vid}/restore")
def restore_version(sid: str, mid: str, vid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return message_out(db, turns.restore_version(db, sid, mid, vid))


@router.get("/stories/{sid}/messages/{mid}/context")
def message_context(sid: str, mid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.get(Message, mid)
    if m is None or m.story_id != sid:
        raise HTTPException(404, "Message not found")
    return {"context": (m.generation_metadata_json or {}).get("context"), "params": (m.generation_metadata_json or {}).get("params")}


# --------------------------------------------------------------------------- generation stream
@router.get("/generations/{mid}/stream")
def generation_stream(mid: str, ctx: AppContext = Depends(get_ctx)):
    return sse(ctx.generations.subscribe(mid))


@router.post("/generations/{mid}/cancel")
async def generation_cancel(mid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"cancelled": ctx.generations.cancel(mid)}


@router.get("/generations/active")
def generations_active(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"active": [{"message_id": j.message_id, "story_id": j.story_id, "branch_id": j.branch_id}
                       for j in ctx.generations.jobs.values() if j.status == "streaming"]}


# --------------------------------------------------------------------------- context inspector
@router.get("/stories/{sid}/context")
def context_preview(sid: str, full: bool = False, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    pid = ctx.story_profile_id(db, s)
    prof = db.get(ModelProfile, pid) if pid else None
    prov = db.get(Provider, prof.provider_id) if prof else None
    built = context_builder.build(db, s, b, context_limit=prof.context_limit if prof else None,
                                  params=story_params(prof.generation_settings_json, s, ctx.adapter_for(prov).is_cloud, prof.context_limit) if prov else None)
    out: dict[str, Any] = {"manifest": built.manifest}
    if prof:
        out["model"] = {"profile_id": prof.id, "model_id": prof.model_id, "provider": prov.display_name if prov else None,
                        "is_cloud": bool(prov and ctx.adapter_for(prov).is_cloud)}
    if full:
        system = built.system
        for secret in built.secrets:  # narrator-only notes never reach the player's screen
            system = system.replace(secret, "[Narrator-only notes are hidden from the player.]")
        out["system"] = system
        msgs = [{"role": m.role, "content": m.content} for m in built.messages]
        for m in msgs:  # v0.5 "stable" layout: the per-turn sections (secrets included) ride with the last message
            for secret in built.secrets:
                m["content"] = m["content"].replace(secret, "[Narrator-only notes are hidden from the player.]")
        out["messages"] = msgs
    return out


# --------------------------------------------------------------------------- v0.6 planned events
@router.get("/stories/{sid}/planned-events")
def planned_events(sid: str, lang: str = "en", db: Session = Depends(get_db)) -> dict[str, Any]:
    """The planned events already played on the current path, and the choices already settled (the Journal shows them;
    events still to come stay a surprise)."""
    from ..services import story_events
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    pack = world_pack.of(db, s.world_id)
    if not story_events.events_of(pack) and not story_events.choices_of(pack):
        return {"played": [], "choices": []}
    prog = story_events.progress(pack, story_tree.path_messages(db, b.head_message_id))
    choices = []
    for c in story_events.choices_of(pack):
        if c["id"] in prog["choices"]:
            o = next((o for o in c.get("options") or [] if o["id"] == prog["choices"][c["id"]]), {})
            choices.append({"id": c["id"], "name": story_events.text_of(c.get("name"), lang),
                            "value": o.get("id"), "label": story_events.text_of(o.get("name"), lang)})
    return {"played": story_events.played(pack, prog, lang), "choices": choices}


class ExclusionIn(BaseModel):
    key: str  # e.g. "lore:<id>", "fact:<id>", "event:<id>", "canon:<id>"
    excluded: bool


@router.post("/stories/{sid}/context/exclusions")
def set_exclusion(sid: str, body: ExclusionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    cfg = dict(s.settings_json or {})
    ex = set(cfg.get("context_exclusions") or [])
    (ex.add if body.excluded else ex.discard)(body.key)
    cfg["context_exclusions"] = sorted(ex)
    s.settings_json = cfg
    return {"context_exclusions": cfg["context_exclusions"]}


class PinLoreIn(BaseModel):
    chunk_id: str
    pinned: bool


@router.post("/stories/{sid}/context/pinned-lore")
def pin_lore(sid: str, body: PinLoreIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    cfg = dict(s.settings_json or {})
    pins = list(cfg.get("pinned_lore_ids") or [])
    if body.pinned and body.chunk_id not in pins:
        pins.append(body.chunk_id)
    if not body.pinned and body.chunk_id in pins:
        pins.remove(body.chunk_id)
    cfg["pinned_lore_ids"] = pins
    s.settings_json = cfg
    return {"pinned_lore_ids": pins}


# --------------------------------------------------------------------------- cast & expressions
@router.get("/stories/{sid}/cast")
def cast(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    st_row = state_service.current(db, b.id)
    state = state_service.normalize(st_row.state_json if st_row else {})
    index = build_index(db, s.world_id, state)
    present = list(state["scene"].get("present") or [])
    recent = [m for m in story_tree.path_messages(db, b.head_message_id) if m.role == "assistant"][-3:]
    mentioned: list[str] = []
    for m in recent:
        for c in (m.generation_metadata_json or {}).get("mentioned_characters") or index.find_mentions(m.content, ("character",)):
            if c not in mentioned:
                mentioned.append(c)
    exprs = ((s.settings_json or {}).get("expressions") or {}).get(b.id, {})
    pmap = assets_svc.portrait_map(db, s.world_id)
    rels = {r.get("target_id"): r for r in state["relationships"] if r.get("target_id") and not r.get("source_id")}
    out = []
    for cid in list(dict.fromkeys(present + mentioned)):
        if cid not in index.entities or index.entities[cid].category != "character":
            continue
        e = index.entities[cid]
        ex = exprs.get(cid) or {"slot": 1, "locked": False, "source": "default"}
        asset_id, used, fallback = assets_svc.resolve_expression(pmap.get(cid, {}), int(ex.get("slot", 1)))
        out.append({"id": cid, "name": e.name, "type": e.type, "local": e.local, "present": cid in present,
                    "recently_mentioned": cid in mentioned, "expression": ex, "asset_id": asset_id, "slot_used": used,
                    "is_fallback": fallback, "available_slots": sorted(pmap.get(cid, {}).keys()),
                    "relationship": rels.get(cid)})
    return {"cast": out}


class ExpressionIn(BaseModel):
    character_id: str
    slot: Optional[int] = None
    locked: Optional[bool] = None


@router.post("/stories/{sid}/expressions")
def set_expression(sid: str, body: ExpressionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    cfg = dict(s.settings_json or {})
    ex = dict(cfg.get("expressions") or {})
    cur = dict(ex.get(s.active_branch_id) or {})
    e = dict(cur.get(body.character_id) or {"slot": 1, "locked": False})
    if body.slot is not None:
        if not 1 <= body.slot <= 6:
            raise ValueError("Expression slot must be 1–6")
        e["slot"], e["source"] = body.slot, "manual"
    if body.locked is not None:
        e["locked"] = body.locked
    e["updated_at"] = now_iso()
    cur[body.character_id] = e
    ex[s.active_branch_id] = cur
    cfg["expressions"] = ex
    s.settings_json = cfg
    return {"expression": e}
