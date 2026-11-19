from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db
from ..models import (EntityFact, ExtractionCursor, MemoryExtractionRun, Message, Recap, Savepoint, StateProposal,
                      StoryEvent, now_iso)
from ..services import context_builder, savepoints, settings_service, story_tree
from ..services.entities import build_index
from ..services import extraction as extraction_svc
from ..services.extraction import activate_recap
from ..services.runtime import AppContext

router = APIRouter(tags=["journal"])

EVENT_STATUSES = ("candidate", "recorded_unverified", "confirmed_from_transcript", "confirmed", "uncertain", "rejected", "superseded")


def _ctx(db: Session, sid: str):
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    path_ids = story_tree.path_ids(db, b)
    return s, b, path_ids


# --------------------------------------------------------------------------- events
@router.get("/stories/{sid}/events")
def list_events(sid: str, q: str = "", entity: str = "", event_type: str = "", status: str = "", min_importance: int = 0,
                chapter: str = "", location: str = "", include_rejected: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    evs = context_builder.visible_events(db, s, b, path_ids)
    if q:
        try:
            ids = {r[0] for r in db.execute(text("SELECT id FROM events_fts WHERE events_fts MATCH :q AND story_id = :s"),
                                            {"q": context_builder.fts_query(q) or q, "s": sid})}
        except Exception:
            ids = set()
        ql = q.lower()
        evs = [e for e in evs if e.id in ids or ql in e.title.lower() or ql in e.summary.lower()]
    if entity:
        evs = [e for e in evs if entity in (e.entity_ids_json or [])]
    if event_type:
        evs = [e for e in evs if e.event_type == event_type]
    if status:
        evs = [e for e in evs if e.verification_status == status]
    elif not include_rejected:
        evs = [e for e in evs if e.verification_status != "rejected"]
    if min_importance:
        evs = [e for e in evs if e.importance >= min_importance]
    if chapter:
        evs = [e for e in evs if e.chapter_id == chapter]
    if location:
        evs = [e for e in evs if e.location_id == location]
    evs.sort(key=lambda e: (e.order_key or "", e.branch_sequence, e.created_at))
    seqs = {m.id: m.seq for m in db.scalars(select(Message).where(Message.story_id == sid))}
    out = []
    for e in evs:
        d = e.to_dict()
        d["source_seqs"] = [seqs.get(i) for i in e.source_message_ids_json or []]
        out.append(d)
    return {"events": out}


class EventIn(BaseModel):
    title: str
    summary: str = ""
    event_type: str = "other"
    importance: int = 3
    confidence: float = 1.0
    verification_status: str = "confirmed"
    evidence_kind: str = "witnessed"
    entity_ids: list[str] = Field(default_factory=list)
    location_id: Optional[str] = None
    in_world_time: Optional[str] = None
    chapter_id: Optional[str] = None
    scene_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    source_message_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    pinned: bool = False


@router.post("/stories/{sid}/events")
def create_event(sid: str, body: EventIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    bad = [i for i in body.source_message_ids if i not in path_ids]
    if bad:
        raise ValueError("Source messages must belong to the current branch.")
    e = StoryEvent(story_id=s.id, branch_id=b.id, branch_sequence=story_tree.next_event_sequence(db, b), title=body.title[:300],
                   summary=body.summary, event_type=body.event_type, importance=max(1, min(5, body.importance)),
                   confidence=body.confidence, verification_status=body.verification_status, evidence_kind=body.evidence_kind,
                   entity_ids_json=body.entity_ids, location_id=body.location_id, in_world_time=body.in_world_time,
                   chapter_id=body.chapter_id, scene_id=body.scene_id, tags_json=body.tags,
                   source_message_ids_json=body.source_message_ids, capture_method="manual", notes=body.notes, pinned=body.pinned)
    db.add(e)
    db.flush()
    return e.to_dict()


class EventPatch(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    event_type: Optional[str] = None
    importance: Optional[int] = None
    verification_status: Optional[str] = None
    evidence_kind: Optional[str] = None
    entity_ids: Optional[list[str]] = None
    location_id: Optional[str] = None
    in_world_time: Optional[str] = None
    chapter_id: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    pinned: Optional[bool] = None
    stale: Optional[bool] = None


@router.patch("/stories/{sid}/events/{eid}")
def patch_event(sid: str, eid: str, body: EventPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = db.get(StoryEvent, eid)
    if e is None or e.story_id != sid:
        raise HTTPException(404, "Event not found")
    data = body.model_dump(exclude_none=True)
    if "verification_status" in data and data["verification_status"] not in EVENT_STATUSES:
        raise ValueError("Unknown status")
    for k, v in data.items():
        col = {"entity_ids": "entity_ids_json", "tags": "tags_json"}.get(k, k)
        setattr(e, col, v)
    if body.stale is False:
        e.stale_reason = None
    return e.to_dict()


class SupersedeIn(BaseModel):
    title: str
    summary: str
    reason: str = "Retcon / correction"


@router.post("/stories/{sid}/events/{eid}/supersede")
def supersede_event(sid: str, eid: str, body: SupersedeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Explicit correction: the old event stays (status superseded) and links to its replacement."""
    s, b, _ = _ctx(db, sid)
    old = db.get(StoryEvent, eid)
    if old is None or old.story_id != sid:
        raise HTTPException(404, "Event not found")
    savepoints.create(db, s, b, label=f"Before retcon of '{old.title[:60]}'", kind="auto", reason="retcon")
    new = StoryEvent(story_id=sid, branch_id=old.branch_id, branch_sequence=story_tree.next_event_sequence(db, b),
                     title=body.title, summary=body.summary, event_type=old.event_type, importance=old.importance,
                     confidence=1.0, verification_status="confirmed", evidence_kind=old.evidence_kind,
                     entity_ids_json=old.entity_ids_json, location_id=old.location_id, in_world_time=old.in_world_time,
                     tags_json=list(old.tags_json or []) + ["retcon"], source_message_ids_json=old.source_message_ids_json,
                     capture_method="manual", supersedes_event_id=old.id, notes=body.reason, order_key=old.order_key)
    db.add(new)
    db.flush()
    old.verification_status, old.superseded_by_event_id = "superseded", new.id
    return {"old": old.to_dict(), "new": new.to_dict()}


class MergeIn(BaseModel):
    keep_id: str
    merge_ids: list[str]


@router.post("/stories/{sid}/events/merge")
def merge_events(sid: str, body: MergeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    keep = db.get(StoryEvent, body.keep_id)
    if keep is None or keep.story_id != sid:
        raise HTTPException(404, "Event not found")
    srcs = list(keep.source_message_ids_json or [])
    ents = list(keep.entity_ids_json or [])
    for mid in body.merge_ids:
        e = db.get(StoryEvent, mid)
        if e is None or e.story_id != sid or e.id == keep.id:
            continue
        srcs += [x for x in e.source_message_ids_json or [] if x not in srcs]
        ents += [x for x in e.entity_ids_json or [] if x not in ents]
        e.verification_status, e.superseded_by_event_id = "superseded", keep.id
        e.notes = (e.notes + "\n" if e.notes else "") + f"Merged into {keep.id}"
    keep.source_message_ids_json, keep.entity_ids_json = srcs, ents
    keep.related_event_ids_json = list(dict.fromkeys((keep.related_event_ids_json or []) + body.merge_ids))
    return keep.to_dict()


# --------------------------------------------------------------------------- facts / memories
@router.get("/stories/{sid}/facts")
def list_facts(sid: str, q: str = "", subject: str = "", status: str = "", fact_kind: str = "", category: str = "",
               perspective: str = "", db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    facts = context_builder.visible_facts(db, s, b, path_ids)
    if q:
        try:
            ids = {r[0] for r in db.execute(text("SELECT id FROM facts_fts WHERE facts_fts MATCH :q"), {"q": context_builder.fts_query(q) or q})}
        except Exception:
            ids = set()
        ql = q.lower()
        facts = [f for f in facts if f.id in ids or ql in f.content.lower()]
    if subject:
        facts = [f for f in facts if f.subject_entity_id == subject or subject in ((f.knowledge_json or {}).get("known_by") or [])]
    if status:
        facts = [f for f in facts if f.status == status]
    if fact_kind:
        facts = [f for f in facts if f.fact_kind == fact_kind]
    if category:
        facts = [f for f in facts if f.category == category]
    if perspective == "player":
        facts = [f for f in facts if "player" in ((f.knowledge_json or {}).get("known_by") or []) or
                 (f.fact_kind in ("established", "witnessed") and "player" not in ((f.knowledge_json or {}).get("hidden_from") or []))]
    elif perspective == "uncertain":
        facts = [f for f in facts if f.status in ("candidate", "disputed") or f.fact_kind in ("rumour", "claim", "hypothetical", "plan", "dream_vision")]
    elif perspective == "beliefs":
        facts = [f for f in facts if f.fact_kind == "belief"]
    elif perspective == "happened":
        facts = [f for f in facts if f.fact_kind in ("established", "witnessed") and f.status == "active"]
    facts.sort(key=lambda f: (not f.pinned, -f.importance, f.created_at))
    return {"facts": [f.to_dict() for f in facts]}


class FactIn(BaseModel):
    content: str
    subject_entity_id: Optional[str] = None
    subject_label: Optional[str] = None
    predicate: str = ""
    category: str = "memory"
    fact_kind: str = "established"
    belief_holder_id: Optional[str] = None
    known_by: list[str] = Field(default_factory=list)
    hidden_from: list[str] = Field(default_factory=list)
    scope: str = "story"
    tags: list[str] = Field(default_factory=list)
    importance: int = 3
    pinned: bool = False
    status: str = "active"
    source_message_ids: list[str] = Field(default_factory=list)


@router.post("/stories/{sid}/facts")
def create_fact(sid: str, body: FactIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    if len(body.content) > 10_000:
        raise ValueError("Memory text is limited to 10,000 characters.")
    f = EntityFact(story_id=None if body.scope == "global" else s.id, branch_id=b.id if body.scope == "branch" else None,
                   scope=body.scope, category=body.category, subject_entity_id=body.subject_entity_id,
                   subject_label=body.subject_label, predicate=body.predicate, content=body.content, fact_kind=body.fact_kind,
                   belief_holder_id=body.belief_holder_id, knowledge_json={"known_by": body.known_by, "hidden_from": body.hidden_from},
                   tags_json=body.tags, importance=body.importance, pinned=body.pinned, status=body.status, confidence=1.0,
                   source_message_ids_json=[i for i in body.source_message_ids if i in path_ids], capture_method="manual",
                   user_corrected=True)
    db.add(f)
    db.flush()
    return f.to_dict()


class FactPatch(BaseModel):
    content: Optional[str] = None
    subject_entity_id: Optional[str] = None
    predicate: Optional[str] = None
    fact_kind: Optional[str] = None
    belief_holder_id: Optional[str] = None
    known_by: Optional[list[str]] = None
    hidden_from: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    importance: Optional[int] = None
    pinned: Optional[bool] = None
    status: Optional[str] = None
    stale: Optional[bool] = None


@router.patch("/stories/{sid}/facts/{fid}")
def patch_fact(sid: str, fid: str, body: FactPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    f = db.get(EntityFact, fid)
    if f is None or (f.story_id not in (sid, None)):
        raise HTTPException(404, "Fact not found")
    data = body.model_dump(exclude_none=True)
    k = dict(f.knowledge_json or {})
    for key in ("known_by", "hidden_from"):
        if key in data:
            k[key] = data.pop(key)
    f.knowledge_json = k
    if "tags" in data:
        f.tags_json = data.pop("tags")
    for key, v in data.items():
        setattr(f, key, v)
    if body.content is not None or body.fact_kind is not None:
        f.user_corrected = True
    return f.to_dict()


@router.delete("/stories/{sid}/facts/{fid}")
def delete_fact(sid: str, fid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Facts are rejected rather than erased, preserving the audit trail."""
    f = db.get(EntityFact, fid)
    if f is None:
        raise HTTPException(404, "Fact not found")
    f.status = "rejected"
    return f.to_dict()


class FactSupersede(BaseModel):
    content: str
    reason: str = ""


@router.post("/stories/{sid}/facts/{fid}/supersede")
def supersede_fact(sid: str, fid: str, body: FactSupersede, db: Session = Depends(get_db)) -> dict[str, Any]:
    old = db.get(EntityFact, fid)
    if old is None:
        raise HTTPException(404, "Fact not found")
    new = EntityFact(**{k: v for k, v in old.to_dict().items() if k not in ("id", "created_at", "updated_at", "dedupe_key")})
    new.content, new.status, new.user_corrected, new.capture_method = body.content, "active", True, "manual"
    new.contradicts_fact_ids_json = []
    db.add(new)
    db.flush()
    old.status, old.superseded_by_fact_id = "superseded", new.id
    return {"old": old.to_dict(), "new": new.to_dict()}


class ContradictIn(BaseModel):
    other_id: str


@router.post("/stories/{sid}/facts/{fid}/contradiction")
def mark_contradiction(sid: str, fid: str, body: ContradictIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    a, b_ = db.get(EntityFact, fid), db.get(EntityFact, body.other_id)
    if a is None or b_ is None:
        raise HTTPException(404, "Fact not found")
    for x, y in ((a, b_), (b_, a)):
        x.contradicts_fact_ids_json = list(dict.fromkeys((x.contradicts_fact_ids_json or []) + [y.id]))
        if x.status == "active":
            x.status = "disputed"
    return {"facts": [a.to_dict(), b_.to_dict()]}


# --------------------------------------------------------------------------- review queue / search / character history
@router.get("/stories/{sid}/review")
def review_queue(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    evs = [e for e in context_builder.visible_events(db, s, b, path_ids) if e.verification_status in ("candidate", "uncertain") or e.stale]
    facts = [f for f in context_builder.visible_facts(db, s, b, path_ids) if f.status in ("candidate", "disputed") or f.stale]
    props = list(db.scalars(select(StateProposal).where(StateProposal.branch_id == b.id, StateProposal.status == "pending")))
    return {"events": [e.to_dict() for e in evs], "facts": [f.to_dict() for f in facts], "proposals": [p.to_dict() for p in props],
            "count": len(evs) + len(facts) + len(props)}


@router.get("/stories/{sid}/search")
def search_all(sid: str, q: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    fq = context_builder.fts_query(q) or q
    out: dict[str, list[dict[str, Any]]] = {"events": [], "facts": [], "recaps": [], "local_canon": []}
    vis_e = {e.id: e for e in context_builder.visible_events(db, s, b, path_ids)}
    vis_f = {f.id: f for f in context_builder.visible_facts(db, s, b, path_ids)}
    for table, key, src in (("events_fts", "events", vis_e), ("facts_fts", "facts", vis_f)):
        try:
            for (i,) in db.execute(text(f"SELECT id FROM {table} WHERE {table} MATCH :q ORDER BY rank LIMIT 50"), {"q": fq}):
                if i in src:
                    out[key].append(src[i].to_dict())
        except Exception:
            pass
    try:
        for (i,) in db.execute(text("SELECT id FROM recaps_fts WHERE recaps_fts MATCH :q AND story_id = :s LIMIT 20"), {"q": fq, "s": sid}):
            r = db.get(Recap, i)
            if r and r.branch_id == b.id:
                out["recaps"].append(r.to_dict())
        from ..models import LocalCanon
        for (i,) in db.execute(text("SELECT id FROM canon_fts WHERE canon_fts MATCH :q LIMIT 20"), {"q": fq}):
            c = db.get(LocalCanon, i)
            if c and (c.story_id in (None, sid)):
                out["local_canon"].append(c.to_dict())
    except Exception:
        pass
    return out


@router.get("/stories/{sid}/characters/{cid}/history")
def character_history(sid: str, cid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    from ..services import state_service

    evs = [e.to_dict() for e in context_builder.visible_events(db, s, b, path_ids) if cid in (e.entity_ids_json or [])
           and e.verification_status != "rejected"]
    facts = context_builder.visible_facts(db, s, b, path_ids)
    about = [f.to_dict() for f in facts if f.subject_entity_id == cid and f.status != "rejected"]
    knows = [f.to_dict() for f in facts if cid in ((f.knowledge_json or {}).get("known_by") or []) and f.status != "rejected"]
    hidden = [f.to_dict() for f in facts if cid in ((f.knowledge_json or {}).get("hidden_from") or []) and f.status != "rejected"]
    beliefs = [f.to_dict() for f in facts if f.belief_holder_id == cid and f.status != "rejected"]
    st = state_service.current(db, b.id)
    rel = next((r for r in (st.state_json if st else {}).get("relationships", []) if r.get("target_id") == cid), None)
    idx = build_index(db, s.world_id, st.state_json if st else {})
    return {"character_id": cid, "name": idx.name(cid), "events": evs, "facts_about": about, "secrets_known": knows,
            "kept_from": hidden, "beliefs": beliefs, "relationship": rel}


# --------------------------------------------------------------------------- extraction
@router.post("/stories/{sid}/extract")
async def extract_now(sid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.db.session() as db:
        s = story_tree.get_story(db, sid)
        bid = s.active_branch_id
    return await ctx.extraction.run(sid, bid, "manual")


@router.post("/stories/{sid}/extract/rebuild")
async def extract_rebuild(sid: str, body: dict[str, Any] | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.db.session() as db:
        s = story_tree.get_story(db, sid)
        bid = s.active_branch_id
    return await ctx.extraction.run(sid, bid, "manual", rebuild_from_seq=int((body or {}).get("from_seq", 0)))


@router.get("/stories/{sid}/extract/runs")
def extraction_runs(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(MemoryExtractionRun).where(MemoryExtractionRun.story_id == sid)
                      .order_by(MemoryExtractionRun.started_at.desc()).limit(50))
    return {"runs": [r.to_dict() for r in rows]}


@router.post("/stories/{sid}/extract/runs/{rid}/retry")
async def retry_run(sid: str, rid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.db.session() as db:
        r = db.get(MemoryExtractionRun, rid)
        if r is None or r.story_id != sid:
            raise HTTPException(404, "Run not found")
        if r.status not in ("failed", "cancelled"):
            raise ValueError("Only failed or stopped runs can be retried.")
        bid = r.branch_id
        # a cut-off answer is not requested again unchanged: a bounded run that was cut off retries in halves (legacy
        # unbounded runs of 50+ messages already become normal chunks); other failures retry with the normal chunk
        span = r.end_seq - r.start_seq + 1
        cut_off = (r.result_json or {}).get("error_category") == "truncated"
        size = extraction_svc.half(span) if cut_off and span <= extraction_svc.CHUNK_MAX_MESSAGES else None
    return await ctx.extraction.run(sid, bid, "manual", chunk_messages=size)


@router.post("/stories/{sid}/extract/skip")
async def skip_next_chunk(sid: str, body: dict[str, Any] | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    """Mark the next unprocessed chunk as not captured (explicit player choice; recorded as ``skipped``)."""
    if not (body or {}).get("confirm"):
        raise ValueError("Skipping messages requires confirmation: they will not be added to the journal.")
    with ctx.db.session() as db:
        s = story_tree.get_story(db, sid)
        bid = s.active_branch_id
    return await ctx.extraction.skip_next(sid, bid)


@router.post("/stories/{sid}/reconcile")
async def reconcile(sid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    """Re-check stale records: re-run extraction over the edited range and list stale items for review."""
    with ctx.db.session() as db:
        s, b, path_ids = _ctx(db, sid)
        stale_e = [e for e in context_builder.visible_events(db, s, b, path_ids) if e.stale]
        stale_f = [f for f in context_builder.visible_facts(db, s, b, path_ids) if f.stale]
        seqs = {m.id: m.seq for m in db.scalars(select(Message).where(Message.story_id == sid))}
        src = [seqs[i] for x in stale_e + stale_f for i in (x.source_message_ids_json or []) if i in seqs]
        bid = b.id
        stale = {"events": [e.to_dict() for e in stale_e], "facts": [f.to_dict() for f in stale_f]}
    proposal = None
    if src:
        proposal = await ctx.extraction.run(sid, bid, "manual", rebuild_from_seq=min(src))
    return {"stale": stale, "re_extraction": proposal,
            "note": "Stale records are kept. Compare them with the new candidates, then confirm, supersede or reject each one."}


# --------------------------------------------------------------------------- recaps
@router.get("/stories/{sid}/recaps")
def list_recaps(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    rows = db.scalars(select(Recap).where(Recap.branch_id == s.active_branch_id).order_by(Recap.version.desc()))
    return {"recaps": [r.to_dict() for r in rows]}


@router.post("/stories/{sid}/recaps/generate")
async def generate_recap(sid: str, body: dict[str, Any] | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return await ctx.extraction.generate_recap(sid, (body or {}).get("instructions", ""))


class RecapIn(BaseModel):
    content: str
    activate: bool = True


@router.post("/stories/{sid}/recaps")
def manual_recap(sid: str, body: RecapIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    head = db.get(Message, b.head_message_id) if b.head_message_id else None
    v = (db.scalar(select(func.max(Recap.version)).where(Recap.branch_id == b.id)) or 0) + 1
    rc = Recap(story_id=sid, branch_id=b.id, version=v, content=body.content, end_message_id=head.id if head else None,
               start_seq=0, end_seq=head.seq if head else -1, source="manual", status="candidate")
    db.add(rc)
    db.flush()
    if body.activate:
        activate_recap(db, rc)
    return rc.to_dict()


class RecapPatch(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None


@router.patch("/stories/{sid}/recaps/{rid}")
def patch_recap(sid: str, rid: str, body: RecapPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    rc = db.get(Recap, rid)
    if rc is None or rc.story_id != sid:
        raise HTTPException(404, "Recap not found")
    if body.content is not None:
        rc.content = body.content
        rc.source = "edited"
    if body.status == "active":
        activate_recap(db, rc)
    elif body.status in ("rejected", "superseded", "candidate"):
        rc.status = body.status
    return rc.to_dict()


# --------------------------------------------------------------------------- continuity tools
@router.post("/stories/{sid}/continuity")
async def continuity(sid: str, body: dict[str, Any] | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    focus = (body or {}).get("focus", "recon")
    if focus not in ("recon", "continuity"):
        raise ValueError("focus must be recon or continuity")
    result = await ctx.extraction.continuity_check(sid, focus, (body or {}).get("input", ""))
    with ctx.db.session() as db:  # keep the result in the transcript as an out-of-story utility record
        s = story_tree.get_story(db, sid)
        b = story_tree.get_branch(db, s)
        m = story_tree.append_message(db, s, b, role="system", kind="utility", content=result.get("summary") or "Continuity check",
                                      command_json={"name": focus, "result": result})
        result["message_id"] = m.id
    return result


# --------------------------------------------------------------------------- savepoints
@router.get("/stories/{sid}/savepoints")
def list_savepoints(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Savepoint).where(Savepoint.story_id == sid).order_by(Savepoint.created_at.desc()))
    return {"savepoints": [{"id": r.id, "label": r.label, "kind": r.kind, "reason": r.reason, "branch_id": r.branch_id,
                            "created_at": r.created_at, "messages": len(r.snapshot_json.get("messages", [])),
                            "events": len(r.snapshot_json.get("events", [])), "facts": len(r.snapshot_json.get("facts", []))}
                           for r in rows]}


@router.post("/stories/{sid}/savepoints")
def create_savepoint(sid: str, body: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    b = story_tree.get_branch(db, s)
    sp = savepoints.create(db, s, b, label=(body or {}).get("label") or f"Savepoint {now_iso()[:16].replace('T', ' ')}")
    return {"id": sp.id, "label": sp.label, "created_at": sp.created_at}


@router.post("/stories/{sid}/savepoints/{spid}/restore")
def restore_savepoint(sid: str, spid: str, body: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = story_tree.get_story(db, sid)
    sp = db.get(Savepoint, spid)
    if sp is None or sp.story_id != sid:
        raise HTTPException(404, "Savepoint not found")
    mode = (body or {}).get("mode", "new_branch")
    if mode == "replace" and not (body or {}).get("confirm"):
        raise ValueError("Replacing the current branch requires confirmation.")
    nb = savepoints.restore(db, s, sp, mode=mode)
    return {"branch_id": nb.id, "label": nb.label}


@router.delete("/stories/{sid}/savepoints/{spid}")
def delete_savepoint(sid: str, spid: str, confirm: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Deleting a savepoint requires confirmation.")
    sp = db.get(Savepoint, spid)
    if sp is None or sp.story_id != sid:
        raise HTTPException(404, "Savepoint not found")
    db.delete(sp)
    return {"ok": True}


# --------------------------------------------------------------------------- maintenance
@router.get("/stories/{sid}/maintenance")
def maintenance(sid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s, b, path_ids = _ctx(db, sid)
    msgs = story_tree.path_messages(db, b.head_message_id)
    cur = db.get(ExtractionCursor, b.id)
    last_ok = db.scalar(select(MemoryExtractionRun).where(MemoryExtractionRun.branch_id == b.id, MemoryExtractionRun.status == "succeeded")
                        .order_by(MemoryExtractionRun.finished_at.desc()).limit(1))
    last_fail = db.scalar(select(MemoryExtractionRun).where(MemoryExtractionRun.branch_id == b.id, MemoryExtractionRun.status == "failed")
                          .order_by(MemoryExtractionRun.started_at.desc()).limit(1))
    evs = context_builder.visible_events(db, s, b, path_ids)
    facts = context_builder.visible_facts(db, s, b, path_ids)
    recap = db.scalar(select(Recap).where(Recap.branch_id == b.id, Recap.status == "active").order_by(Recap.version.desc()).limit(1))
    props = db.scalar(select(func.count()).select_from(StateProposal).where(StateProposal.branch_id == b.id, StateProposal.status == "pending"))
    head_seq = msgs[-1].seq if msgs else -1
    _, pending = extraction_svc.ExtractionService._pending(db, b, cur.last_seq if cur else -1)
    nxt = extraction_svc.chunk(pending) if pending else []
    return {
        "transcript_messages": len(msgs), "transcript_chars": sum(len(m.content) for m in msgs),
        "head_seq": head_seq, "last_processed_seq": cur.last_seq if cur else -1,
        "unprocessed_messages": len([m for m in msgs if m.seq > (cur.last_seq if cur else -1)]),
        "last_successful_extraction": last_ok.finished_at if last_ok else None,
        "last_failed_extraction": ({"id": last_fail.id, "error": last_fail.error_summary, "at": last_fail.started_at}
                                   if last_fail and (not last_ok or last_fail.started_at > last_ok.finished_at) else None),
        "events_total": len(evs), "events_candidates": len([e for e in evs if e.verification_status == "candidate"]),
        "facts_active": len([f for f in facts if f.status == "active"]),
        "facts_candidates": len([f for f in facts if f.status == "candidate"]),
        "stale_records": len([e for e in evs if e.stale]) + len([f for f in facts if f.stale]),
        "pending_proposals": props or 0,
        "recap": {"version": recap.version, "end_seq": recap.end_seq, "updated_at": recap.updated_at} if recap else None,
        "last_backup": settings_service.get(db, "last_backup_at"),
        "capture_mode": settings_service.get(db, "event_capture_mode"),
        "batch_every": settings_service.get(db, "event_capture_batch_turns"),
        "turns_since_extraction": cur.assistant_turns_since if cur else 0,
        # v1.4: bounded chunks; automatic capture pauses on a range that failed for a non-transient reason
        "capturable_messages": len(pending),
        "next_chunk": {"start_seq": nxt[0].seq, "end_seq": nxt[-1].seq, "messages": len(nxt)} if nxt else None,
        "chunk_max_messages": extraction_svc.CHUNK_MAX_MESSAGES,
        "capture_paused": extraction_svc.pause_reason(db, b.id, pending[0].seq if pending else None),
    }


