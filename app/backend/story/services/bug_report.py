"""Bug report (v1.8): one zip with what a developer needs to understand a problem, and nothing private.

Inside: app and system versions, the app log (already redacted when written, and redacted again here), all settings,
the AI providers and model profiles (never an API key), the lore pack check, the database integrity check, and
figures about the stories and the latest generations (model, status, timing, errors) without any story text.

Not inside: API keys or other secrets, story text, notes, lore content, portraits, the database itself.
"""
from __future__ import annotations

import io
import json
import platform
import re
import sys
import zipfile
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import APP_VERSION
from ..models import Message, ModelProfile, Provider, Story, World
from ..secrets_store import RedactingFilter
from . import backup as backup_svc
from . import settings_service
from .runtime import AppContext

LOG_TAIL_BYTES = 3_000_000  # the log rotates at 2 MB, so this keeps the whole current log and part of the previous one
RECENT_GENERATIONS = 30
README = """StoryCore bug report
====================

Made by Settings > Data & backups > Export a bug report. Send it to the person who helps you with StoryCore,
together with what you did, what you expected and what happened.

What is inside
  system.json        app version, Python, operating system, data folder sizes
  settings.json      every app setting (no secret is a setting)
  providers.json     AI providers and model profiles: type, address, parameters, whether a key is stored (never the key)
  generations.json   the latest replies and scene analyses: model, status, timing, token counts, errors (no story text)
  stories.json       per story: world, number of messages and branches, status (titles are not included)
  lore_packs.json    the lore pack checker report (same as Check Lore Packs.bat)
  integrity.json     database integrity check
  logs/              the app log, with API keys and key-like strings masked

Never inside
  API keys and other secrets, story text, story titles, notes, lore content, portraits, the database.
"""


def build(ctx: AppContext, db: Session) -> tuple[str, bytes]:
    """(file name, zip bytes)."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def put(name: str, data: Any) -> None:
            text = data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False, default=str)
            zf.writestr(name, _redact(ctx, text))

        put("README.txt", README)
        put("system.json", _system(ctx))
        put("settings.json", settings_service.get_all(db))
        put("providers.json", _providers(ctx, db))
        put("generations.json", _generations(db))
        put("stories.json", _stories(db))
        put("lore_packs.json", _safe(lambda: _lore_packs(ctx)))
        put("integrity.json", _safe(lambda: backup_svc.integrity_check(db)))
        for f in sorted(ctx.settings.logs_dir.glob("app.log*")):
            data = f.read_bytes()[-LOG_TAIL_BYTES:]
            put(f"logs/{f.name}", data.decode("utf-8", errors="replace"))
    return f"StoryCore_bug_report_{APP_VERSION}_{stamp}.zip", buf.getvalue()


# --------------------------------------------------------------------------- parts
def _system(ctx: AppContext) -> dict[str, Any]:
    s = ctx.settings

    def size(p) -> int | None:
        try:
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size
        except OSError:
            return None

    return {
        "app_version": APP_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "secrets_backend": ctx.secrets.backend_name,
        "database_revision": _revision(ctx),
        "sizes_bytes": {"database": size(s.db_path), "uploads": size(s.uploads_dir), "backups": size(s.backups_dir),
                        "cache": size(s.cache_dir), "logs": size(s.logs_dir)},
    }


def _revision(ctx: AppContext) -> str | None:
    try:
        from ..db import current_revision
        return current_revision(ctx.db.engine)
    except Exception:
        return None


def _providers(ctx: AppContext, db: Session) -> list[dict[str, Any]]:
    out = []
    for p in db.scalars(select(Provider).order_by(Provider.created_at)):
        profiles = db.scalars(select(ModelProfile).where(ModelProfile.provider_id == p.id)).all()
        out.append({
            "type": p.provider_type, "name": p.display_name, "base_url": _clean_url(p.base_url), "enabled": p.is_enabled,
            "has_api_key": bool(p.secret_reference and _has_secret(ctx, p.secret_reference)),
            "config": p.nonsecret_config_json or {},
            "models": [{"model_id": m.model_id, "name": m.display_name, "context_limit": m.context_limit,
                        "parameters": m.generation_settings_json or {}, "capabilities": m.capabilities_json or {}}
                       for m in profiles],
        })
    return out


def _has_secret(ctx: AppContext, ref: str) -> bool:
    try:
        return bool(ctx.secrets.get(ref))
    except Exception:
        return False


def _generations(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(Message).where(Message.role == "assistant").order_by(Message.created_at.desc())
                      .limit(RECENT_GENERATIONS)).all()
    out = []
    for m in rows:
        meta = m.generation_metadata_json or {}
        out.append({
            "at": m.created_at, "status": m.status, "kind": m.kind, "characters": len(m.content or ""),
            "model": (meta.get("diagnostics") or {}).get("model") or meta.get("model_id"),
            "provider_type": meta.get("provider_type"), "duration_s": meta.get("duration_s"),
            "usage": meta.get("usage"), "error": meta.get("error"),
            "diagnostics": {k: v for k, v in (meta.get("diagnostics") or {}).items() if k != "text_hash"},
            "analysis": _analysis(db, m.id),
        })
    return out


def _analysis(db: Session, message_id: str) -> dict[str, Any] | None:
    from ..models import TurnAnalysis
    row = db.scalar(select(TurnAnalysis).where(TurnAnalysis.message_id == message_id))
    if row is None:
        return None
    return {"status": row.status, "error": row.error, "diagnostics": row.diagnostics_json}


def _stories(db: Session) -> list[dict[str, Any]]:
    worlds = {w.id: w.name for w in db.scalars(select(World))}
    out = []
    for s in db.scalars(select(Story).order_by(Story.created_at)):
        n = db.scalar(select(func.count()).select_from(Message).where(Message.story_id == s.id)) or 0
        out.append({"id": s.id, "world": worlds.get(s.world_id), "status": s.status, "messages": n,
                    "created_at": s.created_at, "narration_language": (s.settings_json or {}).get("narration_language")})
    return out


def _lore_packs(ctx: AppContext) -> Any:
    from .pack_check import check_all
    return check_all(ctx.settings.project_root / "Lorepack")


def _safe(fn) -> Any:
    try:
        return fn()
    except Exception as e:  # a report is still useful without this part
        return {"error": f"{type(e).__name__}: {e}"}


def _clean_url(url: str | None) -> str | None:
    """Drop credentials and query strings an address might carry."""
    if not url:
        return url
    try:
        u = urlsplit(url)
        host = u.hostname or ""
        netloc = host + (f":{u.port}" if u.port else "")
        return urlunsplit((u.scheme, netloc, u.path, "", ""))
    except ValueError:
        return "(unparseable address)"


_KEYISH = re.compile(r"\b(sk-or-v1-|sk-ant-|sk-)[A-Za-z0-9_\-]{8,}")


def _redact(ctx: AppContext, text: str) -> str:
    for v in ctx.secrets.known_values():
        if v and len(v) >= 6:
            text = text.replace(v, "[REDACTED]")
    for p in RedactingFilter.PATTERNS:
        text = p.sub("[REDACTED]", text)
    return _KEYISH.sub("[REDACTED]", text)
