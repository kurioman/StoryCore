"""Token use of a story (v0.5, phase 7.5): what each request really cost, and the estimate corrected with it.

* The narrator's replies keep the provider's own figures in their metadata (``generation_metadata_json.usage``).
* Side requests (scene analysis, memory capture, summaries, the player recap) are added up per story in
  ``story.settings_json.usage_side`` by ``record``.
* ``calibrate`` compares the real prompt size the provider reported with the app's estimate (characters / 4) and keeps a
  per-story ratio (``settings_json.token_ratio``); the context builder divides its budget by it, so a story written in
  a language that needs more tokens (French...) no longer overflows a small model window.
Only counts are stored: never text.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Message, Story

log = logging.getLogger(__name__)

KINDS = ("analysis", "capture", "summary", "recap")
RATIO_MIN, RATIO_MAX = 0.6, 2.0
FIELDS = (("prompt_tokens", "input"), ("completion_tokens", "output"), ("cached_tokens", "cached"))


def _add(acc: dict[str, Any], usage: dict[str, Any] | None) -> None:
    acc["requests"] = acc.get("requests", 0) + 1
    u = usage or {}
    if not isinstance(u.get("prompt_tokens"), (int, float)):
        acc["unreported"] = acc.get("unreported", 0) + 1
    for src, dst in FIELDS:
        if isinstance(u.get(src), (int, float)):
            acc[dst] = acc.get(dst, 0) + int(u[src])
    if isinstance(u.get("cost"), (int, float)):
        acc["cost"] = round(acc.get("cost", 0.0) + float(u["cost"]), 6)


def record(ctx, story_id: str, kind: str, adapter) -> None:
    """Count one side request of this story (whatever the provider reported; never raises)."""
    try:
        with ctx.db.session() as db:
            s = db.get(Story, story_id)
            if s is None:
                return
            settings = dict(s.settings_json or {})
            side = {k: dict(v) for k, v in (settings.get("usage_side") or {}).items()}
            _add(side.setdefault(kind, {}), getattr(adapter, "last_usage", None))
            settings["usage_side"] = side
            s.settings_json = settings
    except Exception:
        log.exception("could not record token use for %s", story_id)


def ratio_of(story_settings: dict[str, Any] | None) -> float:
    try:
        r = float((story_settings or {}).get("token_ratio") or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return min(RATIO_MAX, max(RATIO_MIN, r))


def calibrate(db: Session, message_id: str) -> float | None:
    """After a reply: real prompt tokens / estimated ones, folded into the story's ratio (moving average)."""
    m = db.get(Message, message_id)
    if m is None:
        return None
    md = m.generation_metadata_json or {}
    real = (md.get("usage") or {}).get("prompt_tokens")
    est = (md.get("context") or {}).get("total_tokens")
    if not isinstance(real, (int, float)) or not isinstance(est, (int, float)) or real < 300 or est < 300:
        return None
    observed = min(RATIO_MAX, max(RATIO_MIN, real / est))
    s = db.get(Story, m.story_id)
    settings = dict(s.settings_json or {})
    old = settings.get("token_ratio")
    new = observed if old is None else 0.7 * ratio_of(settings) + 0.3 * observed
    settings["token_ratio"] = round(new, 3)
    s.settings_json = settings
    return settings["token_ratio"]


def summary(db: Session, story: Story, path_ids: set[str]) -> dict[str, Any]:
    """Token use of the story: the narrator's replies (on this path), side requests, the latest turn."""
    narration: dict[str, Any] = {}
    last = None
    rows = db.scalars(select(Message).where(Message.story_id == story.id, Message.role == "assistant")
                      .order_by(Message.seq))
    for m in rows:
        md = m.generation_metadata_json or {}
        if "usage" not in md and "context" not in md:
            continue
        if m.id in path_ids:
            _add(narration, md.get("usage"))
            last = m
    side = (story.settings_json or {}).get("usage_side") or {}
    total: dict[str, Any] = {}
    for part in [narration, *side.values()]:
        for k, v in part.items():
            total[k] = round(total.get(k, 0) + v, 6) if isinstance(v, float) else total.get(k, 0) + v
    ratio = ratio_of(story.settings_json)
    out_last = None
    if last is not None:
        md = last.generation_metadata_json or {}
        u = md.get("usage") or {}
        est = (md.get("context") or {}).get("total_tokens")
        out_last = {"message_id": last.id, "seq": last.seq, "input": u.get("prompt_tokens"), "cached": u.get("cached_tokens"),
                    "output": u.get("completion_tokens"), "cost": u.get("cost"),
                    "estimated_input": int(est * ratio) if isinstance(est, (int, float)) else None}
    return {"last": out_last, "narration": narration, "side": side, "total": total, "token_ratio": ratio}
