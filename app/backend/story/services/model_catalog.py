"""Recommended models for stories (v1.6): editorial notes joined with OpenRouter's public catalog.

Only the choice of candidates and their pros and cons are written here. Prices, context sizes, availability and capabilities
come from the official ``/api/v1/models`` endpoint, never from this file, because they change: on 2026-11-06 two of the four
prices in the spec were already out of date. The endpoint is public, so no API key is sent and no inference is involved. Offline, the last copy is shown with its date, marked stale.
Nothing here selects a model: a refreshed list can never change a story's model.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .runtime import AppContext

log = logging.getLogger(__name__)

CATALOG_URL = "https://openrouter.ai/api/v1/models"
CACHE_NAME = "openrouter_models.json"
MAX_AGE_SECONDS = 24 * 3600
MIN_RETRY_SECONDS = 60  # a failed or repeated refresh waits this long, so a reload loop cannot hammer the endpoint
TIMEOUT_SECONDS = 10.0
_last_attempt: dict[str, float] = {}

CANDIDATES: list[dict[str, Any]] = [
    {"slug": "~deepseek/deepseek-v4-flash-latest", "role": "Recommended", "label": "Recommended", "tested": True,
     "pros": ["Very, very low price for high quality", "Tested and recommended with StoryCore"],
     "cons": ["Follows the latest version of the model, so it can change over time"]},
    {"slug": "~anthropic/claude-haiku-latest", "role": "Budget", "label": "Low price, high quality", "tested": False,
     "pros": ["Low price for high quality"],
     "cons": ["Not yet tested in StoryCore"]},
    {"slug": "~anthropic/claude-sonnet-latest", "role": "Premium", "label": "Best quality", "tested": False,
     "pros": ["Best writing quality"],
     "cons": ["High price", "Not yet tested in StoryCore"]},
    {"slug": "mistralai/mistral-nemo", "role": "French", "label": "For French roleplay", "tested": False,
     "pros": ["A good choice to play in French"],
     "cons": ["Not yet tested in StoryCore"]},
    {"slug": "google/gemini-3.8-flash", "role": "Low cost", "label": "Low price", "tested": False,
     "pros": ["Low price"],
     "cons": ["Not yet tested in StoryCore"]},
]
FALLBACK_SLUG = "~deepseek/deepseek-v4-flash-latest"


def _cache_path(ctx: AppContext) -> Path:
    return Path(ctx.settings.data_dir) / "cache" / CACHE_NAME


def load_cache(ctx: AppContext) -> dict[str, Any] | None:
    try:
        data = json.loads(_cache_path(ctx).read_text(encoding="utf-8"))
        return data if isinstance(data.get("models"), dict) and data.get("fetched_at") else None
    except (OSError, ValueError, AttributeError):
        return None


def _per_million(v: Any) -> float | None:
    """USD per 1M tokens, or None for anything that is not a real price (OpenRouter uses "-1" for router models)."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return round(n * 1_000_000, 6) if n >= 0 else None


def _compact(m: dict[str, Any]) -> dict[str, Any]:
    p = m.get("pricing") if isinstance(m.get("pricing"), dict) else {}
    params = m.get("supported_parameters") if isinstance(m.get("supported_parameters"), list) else []
    return {"name": str(m.get("name") or m.get("id"))[:120], "context_length": m.get("context_length"),
            "input_per_million": _per_million(p.get("prompt")), "output_per_million": _per_million(p.get("completion")),
            "cache_read_per_million": _per_million(p.get("input_cache_read")), "expiration_date": m.get("expiration_date"),
            "structured_output": "structured_outputs" in params or "response_format" in params,
            "reasoning": "reasoning" in params}


async def refresh(ctx: AppContext, *, force: bool = False) -> dict[str, Any] | None:
    """Fetch the public catalog into the cache. Returns the new cache, or None when skipped or unreachable."""
    now = time.monotonic()
    key = str(ctx.settings.data_dir)
    if now - _last_attempt.get(key, -MIN_RETRY_SECONDS) < MIN_RETRY_SECONDS:
        return None
    _last_attempt[key] = now
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS), transport=ctx.transport) as c:
            r = await c.get(CATALOG_URL)
        r.raise_for_status()
        items = r.json()["data"]
        models = {m["id"]: _compact(m) for m in items if isinstance(m, dict) and m.get("id")}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        log.info("model catalog not refreshed: %s", type(e).__name__)
        return None
    if not models:
        return None
    data = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": CATALOG_URL, "models": models}
    path = _cache_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
    return data


def _age_seconds(cache: dict[str, Any] | None) -> float | None:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(cache["fetched_at"])).total_seconds() if cache else None
    except (TypeError, ValueError, KeyError):
        return None


def view(cache: dict[str, Any] | None) -> dict[str, Any]:
    """Cards for the settings page. A candidate missing from a known catalog is marked unavailable, with an alternative;
    without any catalog nothing is claimed about availability or price."""
    models = (cache or {}).get("models") or {}
    age = _age_seconds(cache)
    cards = []
    for c in CANDIDATES:
        m = models.get(c["slug"])
        known = bool(models)
        cards.append({**c, "available": bool(m) if known else None,
                      "unavailable_reason": None if m or not known else "Not listed in OpenRouter's catalog right now.",
                      "alternative": FALLBACK_SLUG if known and not m and c["slug"] != FALLBACK_SLUG else None,
                      "name": (m or {}).get("name") or c["slug"], **{k: (m or {}).get(k) for k in (
                          "context_length", "input_per_million", "output_per_million", "cache_read_per_million",
                          "expiration_date", "structured_output", "reasoning")}})
    return {"models": cards, "fetched_at": (cache or {}).get("fetched_at"), "stale": age is None or age > MAX_AGE_SECONDS,
            "source": CATALOG_URL}


async def current(ctx: AppContext, *, force: bool = False) -> dict[str, Any]:
    cache = load_cache(ctx)
    age = _age_seconds(cache)
    if force or age is None or age > MAX_AGE_SECONDS:
        cache = await refresh(ctx, force=force) or cache
    return view(cache)
