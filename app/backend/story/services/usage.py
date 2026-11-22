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
from ..providers.base import ProviderError

log = logging.getLogger(__name__)

KINDS = ("analysis", "capture", "summary", "recap", "rewrite")
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
            u = dict(getattr(adapter, "last_usage", None) or {})
            spent = float(getattr(adapter, "spent_cost", 0.0) or 0.0)
            new_cost = round(spent - float(getattr(adapter, "recorded_cost", 0.0) or 0.0), 8)
            u.pop("cost", None)  # v0.6.2: every request of this side job (retries included), not only the latest
            if new_cost > 0:
                u["cost"] = new_cost
                adapter.recorded_cost = spent
                add_spend(db, new_cost)
            _add(side.setdefault(kind, {}), u or None)
            settings["usage_side"] = side
            s.settings_json = settings
    except Exception:
        log.exception("could not record token use for %s", story_id)


# --------------------------------------------------------------------------- v0.6.2 spending cap
class BudgetReached(ProviderError):
    def __init__(self, message: str):
        super().__init__("budget", message)


def _month() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m")


def add_spend(db: Session, cost: float | None) -> None:
    """Add a paid request to this month's total (settings ``spend_by_month``; the last 12 months are kept)."""
    if not isinstance(cost, (int, float)) or cost <= 0:
        return
    from . import settings_service
    months = dict(settings_service.get(db, "spend_by_month") or {})
    k = _month()
    months[k] = round(float(months.get(k) or 0) + float(cost), 8)
    settings_service.set_many(db, {"spend_by_month": dict(sorted(months.items())[-12:])})


def add_spend_ctx(ctx, cost: float | None) -> None:
    try:
        with ctx.db.session() as db:
            add_spend(db, cost)
    except Exception:
        log.exception("could not record this month's spending")


def story_cost(db: Session, story: Story) -> float:
    """Everything the story cost: all its replies (regenerated, removed, other branches) and its side requests."""
    spent = 0.0
    for md in db.scalars(select(Message.generation_metadata_json).where(Message.story_id == story.id,
                                                                         Message.role == "assistant")):
        md = md or {}
        c = md.get("spent_cost", (md.get("usage") or {}).get("cost"))
        if isinstance(c, (int, float)):
            spent += float(c)
    side = (story.settings_json or {}).get("usage_side") or {}
    spent += sum(float(v.get("cost") or 0) for v in side.values() if isinstance(v, dict))
    return round(spent, 6)


def budget(db: Session, story: Story | None) -> dict[str, Any]:
    """The caps and what was spent: state ``ok`` / ``warn`` (past the warning share) / ``over`` (a cap reached)."""
    from . import settings_service
    cfg = settings_service.get_all(db)

    def num(k: str) -> float:
        try:
            return max(0.0, float(cfg.get(k) or 0))
        except (TypeError, ValueError):
            return 0.0
    out = {"story_limit": num("budget_story_usd"), "month_limit": num("budget_month_usd"),
           "warn_pct": min(100.0, max(1.0, num("budget_warn_pct") or 80.0)),
           "story_spent": story_cost(db, story) if story is not None else 0.0,
           "month_spent": round(float((cfg.get("spend_by_month") or {}).get(_month()) or 0), 6)}
    state = "ok"
    for lim, used in ((out["story_limit"], out["story_spent"]), (out["month_limit"], out["month_spent"])):
        if lim > 0 and used >= lim:
            state = "over"
        elif lim > 0 and used >= lim * out["warn_pct"] / 100 and state == "ok":
            state = "warn"
    out["state"] = state
    return out


def check_budget(db: Session, story: Story | None, adapter) -> None:
    """Raise ``BudgetReached`` before a paid request when a cap is reached (local models are free: never stopped)."""
    if not getattr(adapter, "is_cloud", False):
        return
    b = budget(db, story)
    if b["state"] != "over":
        return
    if b["story_limit"] and b["story_spent"] >= b["story_limit"]:
        raise BudgetReached(f"Spending cap reached for this story (${b['story_spent']:.3f} of ${b['story_limit']:.2f}). "
                            "Raise it in Settings > Budget to keep playing; your message is saved.")
    raise BudgetReached(f"Monthly spending cap reached (${b['month_spent']:.3f} of ${b['month_limit']:.2f}). "
                        "Raise it in Settings > Budget to keep playing; your message is saved.")


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
    # v0.6.2 (Kurio's DeepSeek test: $0.015 shown, $0.017 on OpenRouter): the money is what was really spent, not only
    # the replies still in the story (see story_cost)
    spent = story_cost(db, story)
    total: dict[str, Any] = {}
    for part in [narration, *side.values()]:
        for k, v in part.items():
            total[k] = round(total.get(k, 0) + v, 6) if isinstance(v, float) else total.get(k, 0) + v
    total.pop("cost", None)
    if spent > 0:
        total["cost"] = round(spent, 6)
    ratio = ratio_of(story.settings_json)
    out_last = None
    if last is not None:
        md = last.generation_metadata_json or {}
        u = md.get("usage") or {}
        est = (md.get("context") or {}).get("total_tokens")
        out_last = {"message_id": last.id, "seq": last.seq, "input": u.get("prompt_tokens"), "cached": u.get("cached_tokens"),
                    "output": u.get("completion_tokens"), "cost": u.get("cost"),
                    "estimated_input": int(est * ratio) if isinstance(est, (int, float)) else None}
    return {"last": out_last, "narration": narration, "side": side, "total": total, "token_ratio": ratio,
            "budget": budget(db, story)}
