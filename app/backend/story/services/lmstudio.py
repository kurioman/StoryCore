"""LM Studio in one click (v0.5): find the local server, list its models with their real context size, and create the
provider + model profile with settings that fit.

LM Studio speaks the OpenAI format at <host>/v1, and has its own REST API at <host>/api/v0/models that also says which
models are loaded and with which context length. A model loaded with a small context (LM Studio's default used to be
4,096 tokens) silently loses the beginning of a long story prompt, so the profile records the loaded context and the
engine's context budget then stays inside it (context_builder.effective_window).
"""
from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ModelProfile, Provider
from ..providers.adapters import ADAPTERS
from . import settings_service

DEFAULT_URL = "http://localhost:1234/v1"
DISPLAY_NAME = "LM Studio (local)"
SMALL_CONTEXT = 8192  # below this a story barely fits: say so
TIMEOUT = httpx.Timeout(4.0)
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests plug a fake LM Studio in here


def api_root(base_url: str) -> str:
    """http://localhost:1234/v1 -> http://localhost:1234"""
    u = (base_url or DEFAULT_URL).rstrip("/")
    return u[:-3] if u.endswith("/v1") else u


async def detect(base_url: str = DEFAULT_URL, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    """{"reachable", "base_url", "models": [{id, state, max_context, loaded_context, quantization, arch, type}], "message"}"""
    root = api_root(base_url)
    out: dict[str, Any] = {"reachable": False, "base_url": root + "/v1", "models": [], "detailed": False}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport or TRANSPORT) as c:
            r = await c.get(root + "/api/v0/models")
            if r.status_code == 200:
                out["detailed"] = True
                items = (r.json() or {}).get("data") or []
            else:  # older LM Studio or another OpenAI-compatible server: names only
                r = await c.get(root + "/v1/models")
                r.raise_for_status()
                items = (r.json() or {}).get("data") or []
    except (httpx.HTTPError, ValueError):
        out["message"] = ("LM Studio is not reachable at " + root + ". Open LM Studio, go to the Developer tab and start "
                          "the server (port 1234 by default).")
        return out
    out["reachable"] = True
    for m in items:
        if not m.get("id") or m.get("type") in ("embeddings", "embedding"):
            continue
        out["models"].append({
            "id": m["id"],
            "state": m.get("state") or "unknown",  # loaded | not-loaded
            "max_context": m.get("max_context_length"),
            "loaded_context": m.get("loaded_context_length") or m.get("context_length"),
            "quantization": m.get("quantization"),
            "arch": m.get("arch"),
            "type": m.get("type") or "llm",
        })
    out["models"].sort(key=lambda x: (x["state"] != "loaded", x["id"]))
    out["message"] = (f"LM Studio found: {len(out['models'])} model(s)" +
                      (f", {sum(m['state'] == 'loaded' for m in out['models'])} loaded." if out["detailed"] else "."))
    return out


def window_for(model: dict[str, Any]) -> int | None:
    """The context the model really runs with: the loaded length when LM Studio reports it, else its maximum."""
    return model.get("loaded_context") or model.get("max_context") or None


def setup(db: Session, base_url: str, model: dict[str, Any], *, make_default: bool = True) -> dict[str, Any]:
    """Create (or reuse) the LM Studio provider and a profile for ``model`` (as returned by detect). Idempotent."""
    base_url = api_root(base_url) + "/v1"
    p = db.scalar(select(Provider).where(Provider.provider_type == "openai_compat", Provider.base_url == base_url))
    created = p is None
    if p is None:
        p = Provider(provider_type="openai_compat", display_name=DISPLAY_NAME, base_url=base_url,
                     nonsecret_config_json={})
        db.add(p)
        db.flush()
    # LM Studio enforces a JSON Schema with its grammar; plain JSON mode is refused (see adapters.structured_mode)
    p.nonsecret_config_json = {**(p.nonsecret_config_json or {}), "structured_output": "json_schema"}
    p.is_enabled = True

    window = window_for(model)
    roomy = (window or 0) >= settings_service.ROOMY_LOCAL_WINDOW
    max_tokens = settings_service.DEFAULT_MAX_OUTPUT_TOKENS if roomy else settings_service.LOCAL_MAX_OUTPUT_TOKENS
    supported = ADAPTERS["openai_compat"].supported_params
    prof = db.scalar(select(ModelProfile).where(ModelProfile.provider_id == p.id, ModelProfile.model_id == model["id"]))
    gen = {"temperature": 0.8, "max_tokens": max_tokens}
    if prof is None:
        prof = ModelProfile(provider_id=p.id, model_id=model["id"], display_name=model["id"],
                            generation_settings_json={k: v for k, v in gen.items() if k in supported},
                            context_limit=window, capabilities_json={"supported_params": supported})
        db.add(prof)
        db.flush()
    else:  # keep the player's own parameters; refresh what LM Studio reports
        prof.context_limit = window or prof.context_limit
        prof.generation_settings_json = {**gen, **(prof.generation_settings_json or {})}
    if make_default:
        settings_service.set_many(db, {"default_model_profile_id": prof.id})

    notes = []
    if model.get("state") == "not-loaded":
        notes.append({"code": "not_loaded", "text": "This model is not loaded in LM Studio yet: load it there before playing (LM Studio may also load "
                     "it on the first request)."})
    if window and window < SMALL_CONTEXT:
        notes.append({"code": "small_context", "value": window, "text": f"It runs with a context of {window} tokens, which is small for a story: in LM Studio, reload the "
                     "model with a larger Context Length (16,384 or more if your memory allows), then press Detect again."})
    if not model.get("loaded_context") and model.get("max_context"):
        notes.append({"code": "max_context_used", "value": model["max_context"], "text": f"LM Studio did not say which context length the model is loaded with; its maximum "
                     f"({model['max_context']}) was used. If replies forget the start of the story, set the profile's "
                     "context window to the length chosen in LM Studio."})
    return {"provider_id": p.id, "provider_created": created, "profile_id": prof.id, "model_id": prof.model_id,
            "context_limit": prof.context_limit, "max_tokens": (prof.generation_settings_json or {}).get("max_tokens"),
            "is_default": make_default, "notes": notes}
