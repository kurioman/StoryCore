"""Application runtime: provider resolution, generation jobs and Ollama pull jobs."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

import httpx
from sqlalchemy import select

from ..config import Settings
from ..db import Database
from ..models import MemoryExtractionRun, Message, ModelProfile, Provider, Story, TurnAnalysis, now_iso
from ..providers import ADAPTERS, ChatMessage, ProviderAdapter, ProviderError
from ..secrets_store import SecretStore
from . import settings_service

log = logging.getLogger(__name__)
CHECKPOINT_SECONDS = 1.0


class ConsentRequired(Exception):
    def __init__(self, provider: Provider):
        super().__init__("cloud consent required")
        # plain values: the ORM instance is expired once the request's session rolls back
        self.provider_id = provider.id
        self.provider_name = provider.display_name


class NoModelConfigured(Exception):
    pass


def story_params(profile_params: dict[str, Any] | None, story: Story, hosted: bool, context_limit: int | None = None) -> dict[str, Any]:
    """A profile's parameters with the story's own output limit (v1.6.2): on hosted models, and on local models whose window can
    afford it (v1.6.4). In a smaller or unknown local window that limit would come out of the story's context. Stories without
    one keep the profile's value. In any window a reply may take at most half, so the input can never be planned below zero."""
    from .context_builder import effective_window

    params = dict(profile_params or {})
    window = effective_window(context_limit, params)
    limit = (story.settings_json or {}).get("max_tokens")
    if limit and (hosted or (window or 0) >= settings_service.ROOMY_LOCAL_WINDOW):
        params["max_tokens"] = limit
    if window and int(params.get("max_tokens") or 0) > window // 2:
        params["max_tokens"] = window // 2
    # v0.6 (phase 9): a reply may not run far past its target length. Long free runs are where small models loop
    # (one 740-token reply told the same scene twice). A reply cut by this ceiling is trimmed to its last sentence.
    cap = length_cap((story.settings_json or {}).get("output_length"))
    if cap and int(params.get("max_tokens") or cap + 1) > cap:
        params["max_tokens"] = cap
    if not hosted and "repeat_penalty" not in params:
        params["repeat_penalty"] = settings_service.LOCAL_REPEAT_PENALTY  # story narration only, never JSON requests
    return params


def length_cap(output_length: str | None) -> int | None:
    """Ceiling on a reply's tokens for the story's target length ("short (1–2 paragraphs)", "medium ...", "long ...")."""
    text = (output_length or "").lower()
    for word, cap in settings_service.REPLY_TOKEN_CAPS.items():
        if text.startswith(word):
            return cap
    return None


@dataclass
class Resolved:
    provider: Provider
    profile: ModelProfile
    adapter: ProviderAdapter
    story: Story | None = None  # set for story narration only; analysis and memory capture keep their own budgets

    @property
    def params(self) -> dict[str, Any]:
        if self.story is not None:
            return story_params(self.profile.generation_settings_json, self.story, self.adapter.is_cloud, self.profile.context_limit)
        return dict(self.profile.generation_settings_json or {})


@dataclass
class AppContext:
    settings: Settings
    db: Database
    secrets: SecretStore
    transport: httpx.AsyncBaseTransport | None = None  # injected by tests
    generations: "GenerationManager" = None  # type: ignore[assignment]
    pulls: "PullManager" = None  # type: ignore[assignment]
    extraction: Any = None
    background: set[asyncio.Task] = field(default_factory=set)
    background_futures: set[Any] = field(default_factory=set)
    loop: asyncio.AbstractEventLoop | None = None

    def adapter_for(self, provider: Provider) -> ProviderAdapter:
        cls = ADAPTERS.get(provider.provider_type)
        if cls is None:
            raise ProviderError("bad_request", f"Unknown provider type '{provider.provider_type}'.")
        key = self.secrets.get(provider.secret_reference) if provider.secret_reference else None
        return cls(provider.base_url, key, dict(provider.nonsecret_config_json or {}), transport=self.transport)

    def resolve(self, db, profile_id: str | None, *, require_consent: bool = True) -> Resolved:
        if not profile_id:
            raise NoModelConfigured("No model selected. Pick a provider and model in the top bar or in Settings → Providers.")
        profile = db.get(ModelProfile, profile_id)
        if profile is None:
            raise NoModelConfigured("The selected model profile no longer exists. Choose another model.")
        provider = db.get(Provider, profile.provider_id)
        if provider is None or not provider.is_enabled:
            raise NoModelConfigured(f"The provider for '{profile.display_name}' is disabled or missing.")
        adapter = self.adapter_for(provider)
        if require_consent and adapter.is_cloud and not (provider.nonsecret_config_json or {}).get("cloud_consent_at"):
            raise ConsentRequired(provider)
        return Resolved(provider, profile, adapter)

    def story_profile_id(self, db, story: Story) -> str | None:
        return (story.settings_json or {}).get("model_profile_id") or settings_service.get(db, "default_model_profile_id")

    def extraction_profile_id(self, db, story: Story) -> str | None:
        src = settings_service.get(db, "extraction_model_source")
        if src == "none":
            return None
        if src == "separate":
            return settings_service.get(db, "extraction_model_profile_id")
        return self.story_profile_id(db, story)

    def spawn(self, coro):
        """Schedule a coroutine on the server loop, from the loop itself or from a worker thread."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None and (self.loop is None or running is self.loop):
            t = asyncio.create_task(coro)
            self.background.add(t)
            t.add_done_callback(self.background.discard)
            return t
        if self.loop is None:
            raise RuntimeError("Server event loop not initialised")
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)  # cancel() propagates to the task
        self.background_futures.add(fut)  # tracked so shutdown can cancel jobs started from worker threads
        fut.add_done_callback(self.background_futures.discard)
        return fut


# --------------------------------------------------------------------------- generation jobs
@dataclass
class GenerationJob:
    message_id: str
    story_id: str
    branch_id: str
    text: str = ""
    status: str = "streaming"
    error: dict[str, Any] | None = None
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    cancel_requested: bool = False
    task: asyncio.Task | None = None
    marker_filter: Any = None  # v1.5 immersive mode: removes reaction markers from the stream (services/immersive.py)
    tag_filter: Any = None  # v1.7 portrait tags: removes [Name:N] tags from the stream (services/portrait_tags.py)

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self.subscribers):
            q.put_nowait(event)


def diagnostics(r: Resolved, job: GenerationJob, params: dict[str, Any], first_text: float | None, duration: float) -> dict[str, Any]:
    """How a reply ended, for the optional details under it. Counts, ids and a hash only: no text, prompt or reasoning."""
    fin, used = r.adapter.last_finish or {}, r.adapter.last_usage or {}
    out, thought = used.get("completion_tokens"), used.get("reasoning_tokens")
    return {"model": r.profile.model_id, "provider": fin.get("provider"), "generation_id": fin.get("generation_id"),
            "status": job.status, "finish_reason": fin.get("reason"), "native_finish_reason": fin.get("native"),
            "reasoning": fin.get("reasoning"), "max_tokens": params.get("max_tokens"), "input_tokens": used.get("prompt_tokens"),
            "output_tokens": out, "reasoning_tokens": thought,
            "visible_tokens": out - thought if out is not None and thought is not None else None,
            "first_text_s": round(first_text, 2) if first_text is not None else None, "duration_s": duration,
            "chars": len(job.text), "text_hash": hashlib.sha1(job.text.encode("utf-8")).hexdigest()[:12],
            "error": (job.error or {}).get("category")}


class GenerationManager:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.jobs: dict[str, GenerationJob] = {}
        self.on_complete: list[Callable[[str], Any]] = []

    def active_for_branch(self, branch_id: str) -> GenerationJob | None:
        return next((j for j in self.jobs.values() if j.branch_id == branch_id and j.status == "streaming"), None)

    def start(self, message: Message, resolved: Resolved, system: str, messages: list[ChatMessage],
              marker_filter: Any = None) -> GenerationJob:
        from .portrait_tags import TagFilter
        job = GenerationJob(message.id, message.story_id, message.branch_id, marker_filter=marker_filter,
                            tag_filter=TagFilter())
        self.jobs[message.id] = job
        job.task = self.ctx.spawn(self._run(job, resolved, system, messages))
        return job

    def cancel(self, message_id: str) -> bool:
        job = self.jobs.get(message_id)
        if not job or job.status != "streaming":
            return False
        job.cancel_requested = True
        if job.task:
            job.task.cancel()
        return True

    def _save(self, job: GenerationJob, *, final: bool, meta: dict[str, Any] | None = None) -> None:
        with self.ctx.db.session() as db:
            m = db.get(Message, job.message_id)
            if m is None:
                return
            m.content = job.text
            m.status = job.status if final else "streaming"
            if meta:
                md = dict(m.generation_metadata_json or {})
                md.update(meta)
                m.generation_metadata_json = md

    async def _run(self, job: GenerationJob, r: Resolved, system: str, messages: list[ChatMessage]) -> None:
        started = time.monotonic()
        last_ck = started
        first_text: float | None = None
        params = r.params
        try:
            async for piece in r.adapter.stream_chat(r.profile.model_id, system, messages, params):
                if not piece:
                    continue
                if job.tag_filter is not None:  # the player never sees portrait tags, not even while streaming
                    piece = job.tag_filter.feed(piece)
                    if not piece:
                        continue
                if job.marker_filter is not None:
                    piece = job.marker_filter.feed(piece)
                    if not piece:
                        continue
                first_text = first_text or time.monotonic() - started
                job.text += piece
                job.publish({"type": "delta", "text": piece})
                if time.monotonic() - last_ck >= CHECKPOINT_SECONDS:
                    await asyncio.to_thread(self._save, job, final=False)
                    last_ck = time.monotonic()
            if job.tag_filter is not None:
                tail = job.tag_filter.flush()
                if tail and job.marker_filter is not None:
                    tail = job.marker_filter.feed(tail)
                if tail:
                    job.text += tail
                    job.publish({"type": "delta", "text": tail})
            r.adapter.raise_if_cut_off(params)
            job.status = "complete" if job.text.strip() else "failed"
            if not job.text.strip():
                job.error = ProviderError("invalid_response", f"{r.adapter.label} returned an empty response.").to_dict()
        except asyncio.CancelledError:
            job.status = "cancelled"
        except ProviderError as e:
            job.status = "partial" if job.text.strip() else "failed"
            job.error = e.to_dict()
            log.warning("generation failed: %s (%s)", e.message, e.category)
        except Exception as e:  # never lose partial text on unexpected errors
            job.status = "partial" if job.text.strip() else "failed"
            job.error = {"category": "internal", "message": "Unexpected error during generation.", "details": f"{type(e).__name__}: {e}"}
            log.exception("unexpected generation error")
        meta = {"finished_at": now_iso(), "duration_s": round(time.monotonic() - started, 2),
                "approx_output_tokens": len(job.text) // 4, "error": job.error,
                **({"usage": r.adapter.last_usage} if r.adapter.last_usage else {})}
        meta["diagnostics"] = diagnostics(r, job, params, first_text, meta["duration_s"])
        if job.tag_filter is not None and job.tag_filter.tags:
            meta["portrait_tags_raw"] = job.tag_filter.found()  # resolved to characters by portrait_tags.apply
        if job.tag_filter is not None and job.tag_filter.music:
            meta["music_tags"] = job.tag_filter.music  # v0.5: what the story's music player follows (services/music.py)
        log.info("generation %s: %s", job.message_id, meta["diagnostics"])  # figures and ids only, never story text
        if job.marker_filter is not None:
            try:
                job.marker_filter.flush()
                job.text, meta["immersive"] = job.marker_filter.finalize(job.status == "complete")
            except Exception:  # never lose the reply over the presentation layer
                log.exception("immersive finalisation failed; keeping the streamed text")
                meta["immersive"] = {"mode": "immersive", "status": "fallback", "reason": "internal error"}
        shutting_down = False
        try:
            await asyncio.shield(asyncio.to_thread(self._save, job, final=True, meta=meta))
        except asyncio.CancelledError:  # app shutting down: still persist the final text/status, then stop
            self._save(job, final=True, meta=meta)
            shutting_down = True
        job.publish({"type": "done", "status": job.status, "error": job.error})
        # keep the finished job briefly for late subscribers without holding the task open (clean shutdown)
        asyncio.get_running_loop().call_later(30, self.jobs.pop, job.message_id, None)
        if shutting_down:
            raise asyncio.CancelledError
        for cb in self.on_complete:
            try:
                res = cb(job.message_id)
                if asyncio.iscoroutine(res):
                    self.ctx.spawn(res)
            except Exception:
                log.exception("post-generation hook failed")

    async def subscribe(self, message_id: str) -> AsyncIterator[dict[str, Any]]:
        job = self.jobs.get(message_id)
        if job is None:
            await asyncio.sleep(0.3)  # tiny window between placeholder commit and job registration
            job = self.jobs.get(message_id)
        if job is None:
            with self.ctx.db.session() as db:
                m = db.get(Message, message_id)
                if m is not None and m.status == "streaming":
                    # no job owns this placeholder any more: it can never finish, so record it as interrupted
                    m.status = "partial" if m.content.strip() else "failed"
                    md = dict(m.generation_metadata_json or {})
                    md["error"] = {"category": "interrupted", "message": "This response was interrupted. The text saved so far is kept."}
                    m.generation_metadata_json = md
            with self.ctx.db.session() as db:
                m = db.get(Message, message_id)
                if m is None:
                    yield {"type": "error", "error": {"message": "Message not found"}}
                    return
                yield {"type": "snapshot", "text": m.content, "status": m.status}
                yield {"type": "done", "status": m.status, "error": (m.generation_metadata_json or {}).get("error")}
            return
        q: asyncio.Queue = asyncio.Queue()
        job.subscribers.append(q)
        try:
            yield {"type": "snapshot", "text": job.text, "status": job.status}
            if job.status != "streaming":
                yield {"type": "done", "status": job.status, "error": job.error}
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"type": "ping"}
                    continue
                yield ev
                if ev["type"] == "done":
                    return
        finally:
            if q in job.subscribers:
                job.subscribers.remove(q)


def recover_interrupted(db_: Database) -> int:
    """Messages left 'streaming' by a crash/restart become 'partial' (or 'failed' when empty)."""
    n = 0
    with db_.session() as db:
        for m in db.scalars(select(Message).where(Message.status == "streaming")):
            m.status = "partial" if m.content.strip() else "failed"
            md = dict(m.generation_metadata_json or {})
            md["error"] = {"category": "interrupted", "message": "The app stopped while this response was streaming. "
                           "The text saved so far is kept; you can regenerate or continue."}
            m.generation_metadata_json = md
            n += 1
        # background work that no task owns any more would otherwise look busy forever (and refuse a retry)
        msg = "Interrupted: the app stopped while this was running. Retry to run it again."
        for a in db.scalars(select(TurnAnalysis).where(TurnAnalysis.status.in_(("pending", "running")))):
            a.status, a.error = "failed", msg
            a.suggestions_error = msg if not a.suggestions_json else a.suggestions_error
        for r in db.scalars(select(MemoryExtractionRun).where(MemoryExtractionRun.status == "running")):
            r.status, r.error_summary, r.finished_at = "failed", msg, now_iso()
    return n


# --------------------------------------------------------------------------- ollama pulls
@dataclass
class PullJob:
    id: str
    provider_id: str
    model: str
    status: str = "running"  # running | succeeded | failed | cancelled
    last: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    task: asyncio.Task | None = None
    started_at: str = field(default_factory=now_iso)

    def snapshot(self) -> dict[str, Any]:
        return {"id": self.id, "provider_id": self.provider_id, "model": self.model, "status": self.status,
                "progress": self.last, "error": self.error, "started_at": self.started_at}


class PullManager:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.jobs: dict[str, PullJob] = {}

    def start(self, provider: Provider, model: str) -> PullJob:
        import uuid

        for j in self.jobs.values():
            if j.model == model and j.provider_id == provider.id and j.status == "running":
                return j
        job = PullJob(uuid.uuid4().hex, provider.id, model)
        self.jobs[job.id] = job
        adapter = self.ctx.adapter_for(provider)
        job.task = self.ctx.spawn(self._run(job, adapter))
        return job

    async def _run(self, job: PullJob, adapter) -> None:
        try:
            async for obj in adapter.pull(job.model):
                job.last = {k: obj.get(k) for k in ("status", "digest", "total", "completed")}
                for q in job.subscribers:
                    q.put_nowait({"type": "progress", **job.snapshot()})
            job.status = "succeeded" if job.last.get("status") == "success" else "failed"
            if job.status == "failed":
                job.error = f"Ollama ended the download without a success status (last status: {job.last.get('status')})."
        except asyncio.CancelledError:
            job.status = "cancelled"
        except ProviderError as e:
            job.status, job.error = "failed", e.message
        except Exception as e:  # pragma: no cover
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
        for q in job.subscribers:
            q.put_nowait({"type": "done", **job.snapshot()})

    def cancel(self, job_id: str) -> bool:
        j = self.jobs.get(job_id)
        if j and j.status == "running" and j.task:
            j.task.cancel()
            return True
        return False

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        j = self.jobs.get(job_id)
        if j is None:
            yield {"type": "error", "error": "Unknown download job"}
            return
        q: asyncio.Queue = asyncio.Queue()
        j.subscribers.append(q)
        try:
            yield {"type": "progress", **j.snapshot()}
            if j.status != "running":
                yield {"type": "done", **j.snapshot()}
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"type": "ping"}
                    continue
                yield ev
                if ev["type"] == "done":
                    return
        finally:
            if q in j.subscribers:
                j.subscribers.remove(q)
