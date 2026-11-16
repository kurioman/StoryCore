"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import logging
import logging.handlers
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import APP_VERSION, FRONTEND_DIST, Settings, load_settings
from .db import Database
from .models import ModelProfile, Provider, UserNote
from .providers import ProviderError
from .secrets_store import RedactingFilter, make_secret_store
from .services import commands as commands_svc
from .services import settings_service
from .services.extraction import ExtractionService
from .services.runtime import (AppContext, ConsentRequired, GenerationManager, NoModelConfigured, PullManager,
                               recover_interrupted)
from .services.story_tree import NotFound
from .services import turn_analysis
from .services.turns import TurnError, post_process

log = logging.getLogger("story")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CLOUD_NOTICE = ("When you use this cloud provider, the app sends the request context to the provider over the internet: "
                "core instructions, your active user notes, the avatar profile, current story state, scene and relationship "
                "summaries, relevant memories/journal events, retrieved lore snippets, the recap and recent messages. "
                "Scene analysis after each reply, event extraction and recaps (when enabled) send similar content. "
                "Nothing else leaves your computer, and your "
                "API key is only sent to this provider. Cloud API usage may be billed by the provider.")


def setup_logging(settings: Settings, ctx: AppContext) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_story", False) for h in root.handlers):
        return
    fh = logging.handlers.RotatingFileHandler(settings.logs_dir / "app.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    fh.addFilter(RedactingFilter(ctx.secrets))
    fh._story = True  # type: ignore[attr-defined]
    root.addHandler(fh)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # never log request headers


def seed_defaults(ctx: AppContext) -> None:
    with ctx.db.session() as db:
        commands_svc.seed(db)
        if db.scalar(select(UserNote).where(UserNote.scope == "global")) is None:
            db.add(UserNote(scope="global", content="", enabled=True))
        if db.scalar(select(Provider).where(Provider.provider_type == "mock")) is None:
            p = Provider(provider_type="mock", display_name="Mock (offline demo)", base_url=None,
                         nonsecret_config_json={"delay": 0.03})
            db.add(p)
            db.flush()
            prof = ModelProfile(provider_id=p.id, model_id="mock-narrator", display_name="Mock narrator (offline demo)",
                                generation_settings_json={"max_tokens": 1024}, context_limit=8192)
            db.add(prof)
            db.flush()
            if not settings_service.get(db, "default_model_profile_id"):
                settings_service.set_many(db, {"default_model_profile_id": prof.id})


def create_app(settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None,
               testing: bool = False) -> FastAPI:
    settings = settings or load_settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    secrets = make_secret_store(settings.secrets_backend, settings.data_dir)
    ctx = AppContext(settings=settings, db=db, secrets=secrets, transport=transport)
    from .services import music as music_svc
    music_svc.set_folder(settings.music_dir)
    ctx.generations = GenerationManager(ctx)
    ctx.pulls = PullManager(ctx)
    ctx.extraction = ExtractionService(ctx)

    async def after_generation(message_id: str) -> None:
        method_branch = await asyncio.to_thread(post_process, ctx, message_id)
        tagged = False
        try:  # v1.7: the narrator's portrait tags show the portraits at once, before the scene analysis
            tagged = await asyncio.to_thread(_apply_tags, message_id)
        except Exception:
            log.exception("portrait tags failed for %s", message_id)
        try:
            await turn_analysis.analyse(ctx, message_id, force=tagged)
        except Exception:  # never let optional metadata affect the finished reply or the extraction that follows
            log.exception("turn analysis crashed for %s", message_id)
        try:  # v1.8 phase 7.6: a character recorded as dead who speaks (no model call)
            from .services import continuity
            with ctx.db.session() as s:
                continuity.check_speakers(s, message_id)
        except Exception:
            log.exception("continuity check failed for %s", message_id)
        with ctx.db.session() as s:
            from .models import Message
            m = s.get(Message, message_id)
            story_id, branch_id = m.story_id, m.branch_id
            mode = settings_service.get(s, "event_capture_mode")
        if method_branch:
            await ctx.extraction.run(story_id, method_branch, "after_each_turn" if mode == "after_each_turn" else "automatic_batch")
        try:  # v1.8 phase 7.5: the real prompt size corrects the token estimate of this story
            from .services import usage
            with ctx.db.session() as s:
                usage.calibrate(s, message_id)
        except Exception:
            log.exception("token calibration failed for %s", message_id)
        try:  # v1.8 phase 7.1: summaries that memory capture did not write (older games, capture off, an empty field)
            from .services import summaries
            await summaries.catch_up(ctx, story_id, branch_id)
        except Exception:
            log.exception("memory summary catch-up crashed for %s", message_id)

    def _apply_tags(message_id: str) -> bool:
        from .services import portrait_tags
        with ctx.db.session() as s:
            return portrait_tags.apply(s, message_id)

    ctx.generations.on_complete.append(after_generation)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx.loop = asyncio.get_running_loop()
        if not testing:
            setup_logging(settings, ctx)
        pre = ctx.db.migrate(settings.backups_dir)
        if pre:
            log.info("database backed up before migration: %s", pre.name)
        n = recover_interrupted(ctx.db)
        if n:
            log.info("recovered %d interrupted generation(s)", n)
        seed_defaults(ctx)
        if not testing:
            from .bundled import sync_lore_packs
            await asyncio.to_thread(sync_lore_packs, ctx)
        log.info("StoryCore %s started; data dir %s; secrets backend %s", APP_VERSION, settings.data_dir,
                 secrets.backend_name)
        yield
        await app.state.remote.disable()  # phone access never survives a restart
        for t in [*ctx.background, *ctx.background_futures]:
            t.cancel()
        if ctx.background:  # let cancelled jobs persist their final text/status before the DB closes
            await asyncio.wait(list(ctx.background), timeout=5)
        ctx.db.dispose()

    app = FastAPI(title="StoryCore", version=APP_VERSION, lifespan=lifespan)
    app.state.ctx = ctx
    app.state.testing = testing
    app.state.cloud_notice = CLOUD_NOTICE

    from .services.remote import COOKIE as DEVICE_COOKIE, IP_HOST, RemoteAccess, blocked as pc_only

    remote = RemoteAccess(main_port=settings.port)
    app.state.remote = remote

    @app.middleware("http")
    async def security(request: Request, call_next):
        host = (request.headers.get("host") or "").lower()
        hostname = re.sub(r":\d+$", "", host)
        path = request.url.path
        if remote.is_network_request(request.scope):
            # v1.8 phone access: the network listener answers only by IP address (no DNS rebinding) and only to
            # paired devices; PC-only areas stay closed (services/remote.py).
            if not IP_HOST.match(hostname):
                return JSONResponse({"detail": "Host not allowed."}, 403)
            if path != "/pair":
                if remote.device_for(request.cookies.get(DEVICE_COOKIE)) is None:
                    if path.startswith("/api/"):
                        return JSONResponse({"detail": "This device is not connected. Scan the QR code shown on the "
                                                       "computer again.", "code": "not_paired"}, 401)
                    return RedirectResponse("/pair", status_code=303)
                if path.startswith("/api/") and pc_only(request.method, path):
                    return JSONResponse({"detail": "This is only available on the computer.", "code": "pc_only"}, 403)
            allowed_origin = re.compile(rf"^http://{re.escape(host)}$")
        else:
            if hostname not in LOOPBACK_HOSTS and not (testing and hostname == "testserver"):
                return JSONResponse({"detail": "Host not allowed. StoryCore only serves 127.0.0.1/localhost."}, 403)
            allowed_origin = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$")
        if request.method in UNSAFE and path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and not (allowed_origin.match(origin) or origin in settings.dev_origins):
                return JSONResponse({"detail": "Cross-origin request blocked."}, 403)
            # X-Lumencia-Client: the header name used by Lumencia Story Desk's frontend (still accepted).
            if "1" not in (request.headers.get("x-story-client"), request.headers.get("x-lumencia-client")):
                return JSONResponse({"detail": "Missing X-Story-Client header."}, 403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    @app.exception_handler(TurnError)
    async def _turn(_: Request, e: TurnError):
        return JSONResponse({"detail": e.message, "code": "turn_error"}, e.status)

    @app.exception_handler(NotFound)
    async def _nf(_: Request, e: NotFound):
        return JSONResponse({"detail": str(e), "code": "not_found"}, 404)

    @app.exception_handler(ConsentRequired)
    async def _consent(_: Request, e: ConsentRequired):
        return JSONResponse({"detail": "This cloud provider needs your approval before the first request.",
                             "code": "cloud_consent_required", "provider_id": e.provider_id,
                             "provider_name": e.provider_name, "notice": CLOUD_NOTICE}, 409)

    @app.exception_handler(NoModelConfigured)
    async def _nomodel(_: Request, e: NoModelConfigured):
        return JSONResponse({"detail": str(e), "code": "no_model"}, 400)

    @app.exception_handler(ProviderError)
    async def _perr(_: Request, e: ProviderError):
        return JSONResponse({"detail": e.message, "code": "provider_error", "error": e.to_dict()}, 502)

    @app.exception_handler(ValueError)
    async def _verr(_: Request, e: ValueError):
        return JSONResponse({"detail": str(e), "code": "invalid"}, 400)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, e: Exception):
        # uvicorn prints these only to the console window; keep them in app.log (secrets are redacted by its filter)
        log.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=e)
        return JSONResponse({"detail": "Unexpected server error; details are in the app log.", "code": "internal"}, 500)

    from .routers import (assets, avatars, backup, commands, journal, lore, memory, music, narrative, providers,
                          remote as remote_r, state, stories, system)

    for r in (system.router, providers.router, stories.router, state.router, journal.router, avatars.router,
              lore.router, assets.router, commands.router, backup.router, narrative.router, music.router, remote_r.router,
              memory.router):
        app.include_router(r, prefix="/api")

    app.include_router(remote_r.pair_router)

    # v1.8: the interface (built from app/frontend/src into app/frontend/dist) is served at /. The addresses used
    # while the old and the new interface lived side by side (/next/, /old) lead back to it (the #/... part is kept).
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/old", include_in_schema=False)
    @app.get("/next", include_in_schema=False)
    @app.get("/next/{full_path:path}", include_in_schema=False)
    async def former_addresses(full_path: str = ""):
        return RedirectResponse("/", status_code=307)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, 404)
        f = (FRONTEND_DIST / full_path).resolve() if full_path else None
        if f and f.is_file() and FRONTEND_DIST.resolve() in f.parents:
            return FileResponse(f)
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return HTMLResponse("<h1>StoryCore</h1><p>The interface has not been built yet: run <code>npm run build</code> "
                            "in app/frontend (see DEVONLY/13_FRONTEND_SOURCE.md).</p>")

    return app
