from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_ctx, get_db, sse
from ..models import ModelProfile, Provider, now_iso
from ..providers import ADAPTERS, PROVIDER_PRESETS, ProviderError
from ..providers.base import ALL_PARAMS
from ..services import model_catalog, settings_service
from ..services.context_builder import effective_window
from ..services.runtime import AppContext

router = APIRouter(tags=["providers"])

# A small, optional suggestion list. It is NOT a live catalogue: Ollama's local API has no public search endpoint.
CURATED_OLLAMA = {
    "source": "Hand-picked suggestions bundled with StoryCore (snapshot 2026-10-29). Availability, sizes and "
              "licences can change — check https://ollama.com/library before downloading.",
    "models": [
        {"name": "llama3.1:8b", "note": "General-purpose 8B model; a common starting point."},
        {"name": "mistral-nemo:12b", "note": "12B model with a long context window; popular for creative writing."},
        {"name": "qwen2.5:7b", "note": "7B multilingual model."},
        {"name": "gemma2:9b", "note": "9B model from Google."},
        {"name": "nomic-embed-text", "note": "Embedding model (not used for chat)."},
    ],
}
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9._\-/]*(:[A-Za-z0-9._\-]+)?$"


def provider_out(ctx: AppContext, p: Provider) -> dict[str, Any]:
    cls = ADAPTERS.get(p.provider_type)
    a = ctx.adapter_for(p) if cls else None
    cfg = dict(p.nonsecret_config_json or {})
    return {"id": p.id, "provider_type": p.provider_type, "display_name": p.display_name, "base_url": p.base_url,
            "model_listing_mode": p.model_listing_mode, "config": cfg, "is_enabled": p.is_enabled,
            # never the key itself — only whether one is stored
            "has_api_key": bool(p.secret_reference and ctx.secrets.get(p.secret_reference)),
            "is_cloud": bool(a and a.is_cloud), "supported_params": a.supported_params if a else [],
            "cloud_consent_at": cfg.get("cloud_consent_at"), "created_at": p.created_at}


def profile_out(m: ModelProfile) -> dict[str, Any]:
    return m.to_dict()


class ProviderIn(BaseModel):
    provider_type: str
    display_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(default=None, description="write-only")
    model_listing_mode: str = "auto"
    config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class ProviderPatch(BaseModel):
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    clear_api_key: bool = False
    model_listing_mode: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None


@router.get("/providers/presets")
def presets(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"presets": PROVIDER_PRESETS, "params": ALL_PARAMS,
            "supported_params": {k: v.supported_params for k, v in ADAPTERS.items()},
            "cloud_notice": "When you use a cloud provider, the request context is sent to that provider. See the data notice before the first request.",
            "secrets_backend": ctx.secrets.backend_name, "secrets_warning": ctx.secrets.warning}


@router.get("/providers")
def list_providers(ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    provs = list(db.scalars(select(Provider).order_by(Provider.created_at)))
    profs = list(db.scalars(select(ModelProfile).order_by(ModelProfile.created_at)))
    return {"providers": [provider_out(ctx, p) for p in provs], "profiles": [profile_out(m) for m in profs],
            "default_model_profile_id": settings_service.get(db, "default_model_profile_id")}


@router.post("/providers")
def create_provider(body: ProviderIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.provider_type not in ADAPTERS:
        raise ValueError("Unknown provider type")
    if body.provider_type == "openai_compat" and not (body.base_url or "").startswith(("http://", "https://")):
        raise ValueError("Enter the endpoint base URL (e.g. https://openrouter.ai/api/v1).")
    p = Provider(provider_type=body.provider_type, display_name=body.display_name.strip() or body.provider_type,
                 base_url=(body.base_url or "").strip() or None, model_listing_mode=body.model_listing_mode,
                 nonsecret_config_json=_clean_config(body.config), is_enabled=body.is_enabled)
    db.add(p)
    db.flush()
    if body.api_key:
        p.secret_reference = f"provider:{p.id}"
        ctx.secrets.set(p.secret_reference, body.api_key.strip())
    return provider_out(ctx, p)


def _clean_config(cfg: dict[str, Any]) -> dict[str, Any]:
    cfg = {k: v for k, v in (cfg or {}).items() if k not in ("api_key", "key", "secret", "authorization")}
    hdrs = cfg.get("extra_headers") or {}
    cfg["extra_headers"] = {k: v for k, v in hdrs.items() if k.lower() not in ("authorization", "x-api-key")}
    return cfg


@router.patch("/providers/{pid}")
def update_provider(pid: str, body: ProviderPatch, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Provider, pid)
    if p is None:
        raise HTTPException(404, "Provider not found")
    if body.display_name is not None:
        p.display_name = body.display_name
    if body.base_url is not None:
        p.base_url = body.base_url.strip() or None
    if body.model_listing_mode is not None:
        p.model_listing_mode = body.model_listing_mode
    if body.config is not None:
        keep = {k: v for k, v in (p.nonsecret_config_json or {}).items() if k in ("cloud_consent_at", "last_test")}
        p.nonsecret_config_json = {**_clean_config(body.config), **keep}
    if body.is_enabled is not None:
        p.is_enabled = body.is_enabled
    if body.clear_api_key and p.secret_reference:
        ctx.secrets.delete(p.secret_reference)
        p.secret_reference = None
    if body.api_key:
        p.secret_reference = p.secret_reference or f"provider:{p.id}"
        ctx.secrets.set(p.secret_reference, body.api_key.strip())
    return provider_out(ctx, p)


@router.delete("/providers/{pid}")
def delete_provider(pid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Provider, pid)
    if p is None:
        raise HTTPException(404, "Provider not found")
    if p.secret_reference:
        ctx.secrets.delete(p.secret_reference)
    prof_ids = [m.id for m in db.scalars(select(ModelProfile).where(ModelProfile.provider_id == pid))]
    if settings_service.get(db, "default_model_profile_id") in prof_ids:
        settings_service.set_many(db, {"default_model_profile_id": None})
    db.delete(p)
    return {"ok": True}


@router.post("/providers/{pid}/consent")
def give_consent(pid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Provider, pid)
    if p is None:
        raise HTTPException(404, "Provider not found")
    p.nonsecret_config_json = {**(p.nonsecret_config_json or {}), "cloud_consent_at": now_iso()}
    return provider_out(ctx, p)


@router.post("/providers/{pid}/test")
async def test_provider(pid: str, body: dict[str, Any] | None = None, ctx: AppContext = Depends(get_ctx),
                        db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Provider, pid)
    if p is None:
        raise HTTPException(404, "Provider not found")
    adapter = ctx.adapter_for(p)
    body = body or {}
    model_id = body.get("model_id")
    try:
        if body.get("generate"):  # the only path here that runs a model: the player pressed the disclosed paid test
            if not model_id:
                raise ProviderError("bad_request", "Choose a model to test first.")
            out = {"ok": True, **(await adapter.probe(model_id))}
        else:
            out = {"ok": True, **(await adapter.test_connection(model_id))}
    except ProviderError as e:
        out = {"ok": False, "message": e.message, "error": e.to_dict()}
    if body.get("record"):  # a test the player pressed, shown as "last tested"; background status checks leave no trace
        p.nonsecret_config_json = {**(p.nonsecret_config_json or {}), "last_test": {
            "ok": out["ok"], "at": now_iso(), "message": out["message"][:300], "model_id": model_id, "generated": bool(body.get("generate")),
            "category": (out.get("error") or {}).get("category")}}
    return out


@router.get("/providers/{pid}/models")
async def provider_models(pid: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Provider, pid)
    if p is None:
        raise HTTPException(404, "Provider not found")
    adapter = ctx.adapter_for(p)
    try:
        models = await adapter.list_models()
    except ProviderError as e:
        return {"ok": False, "models": [], "message": e.message, "error": e.to_dict(),
                "manual_entry": True, "manual_hint": "Model listing failed or is unsupported — enter the model ID manually."}
    out: dict[str, Any] = {"ok": True, "models": [m.__dict__ for m in models], "manual_entry": True}
    if p.provider_type == "ollama":
        out["running"] = await adapter.running_models()
    return out


@router.get("/model-catalog")
async def model_catalog_view(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    """Recommended models with OpenRouter's public prices. Metadata only: no key is sent and no model runs."""
    return await model_catalog.current(ctx)


@router.post("/model-catalog/refresh")
async def model_catalog_refresh(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return await model_catalog.current(ctx, force=True)


class ProfileIn(BaseModel):
    provider_id: str
    model_id: str
    display_name: Optional[str] = None
    generation_settings: dict[str, Any] = Field(default_factory=dict)
    context_limit: Optional[int] = None
    is_favourite: bool = False
    make_default: bool = False


@router.post("/model-profiles")
def create_profile(body: ProfileIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Provider, body.provider_id)
    if p is None:
        raise HTTPException(404, "Provider not found")
    if not body.model_id.strip():
        raise ValueError("Model ID is required")
    supported = ADAPTERS[p.provider_type].supported_params
    gen = {k: v for k, v in body.generation_settings.items() if k in supported}
    hosted = ctx.adapter_for(p).is_cloud
    window = effective_window(body.context_limit, gen)
    roomy = hosted or (window or 0) >= settings_service.ROOMY_LOCAL_WINDOW
    gen.setdefault("max_tokens", settings_service.DEFAULT_MAX_OUTPUT_TOKENS if roomy else settings_service.LOCAL_MAX_OUTPUT_TOKENS)
    if p.provider_type != "openai":
        gen.setdefault("temperature", 0.8)
    m = ModelProfile(provider_id=p.id, model_id=body.model_id.strip(), display_name=body.display_name or body.model_id.strip(),
                     generation_settings_json=gen, context_limit=body.context_limit, is_favourite=body.is_favourite,
                     capabilities_json={"supported_params": supported})
    db.add(m)
    db.flush()
    if body.make_default or not settings_service.get(db, "default_model_profile_id"):
        settings_service.set_many(db, {"default_model_profile_id": m.id})
    return profile_out(m)


class ProfilePatch(BaseModel):
    display_name: Optional[str] = None
    model_id: Optional[str] = None
    generation_settings: Optional[dict[str, Any]] = None
    context_limit: Optional[int] = None
    is_favourite: Optional[bool] = None


@router.patch("/model-profiles/{mid}")
def update_profile(mid: str, body: ProfilePatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.get(ModelProfile, mid)
    if m is None:
        raise HTTPException(404, "Model profile not found")
    p = db.get(Provider, m.provider_id)
    if body.display_name is not None:
        m.display_name = body.display_name
    if body.model_id is not None and body.model_id.strip():
        m.model_id = body.model_id.strip()
    if body.generation_settings is not None:
        supported = ADAPTERS[p.provider_type].supported_params
        m.generation_settings_json = {k: v for k, v in body.generation_settings.items() if k in supported and v not in (None, "")}
    if body.context_limit is not None:
        m.context_limit = body.context_limit or None
    if body.is_favourite is not None:
        m.is_favourite = body.is_favourite
    return profile_out(m)


@router.delete("/model-profiles/{mid}")
def delete_profile(mid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.get(ModelProfile, mid)
    if m is None:
        raise HTTPException(404, "Model profile not found")
    if settings_service.get(db, "default_model_profile_id") == mid:
        settings_service.set_many(db, {"default_model_profile_id": None})
    db.delete(m)
    return {"ok": True}


# --------------------------------------------------------------------------- Ollama management
def _ollama(db: Session, pid: str) -> Provider:
    p = db.get(Provider, pid)
    if p is None or p.provider_type != "ollama":
        raise HTTPException(404, "Ollama provider not found")
    return p


@router.get("/ollama/curated")
def curated() -> dict[str, Any]:
    return CURATED_OLLAMA


@router.get("/ollama/{pid}/show")
async def ollama_show(pid: str, model: str, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    return await ctx.adapter_for(_ollama(db, pid)).show(model)


class PullIn(BaseModel):
    model: str


@router.post("/ollama/{pid}/pull")
def ollama_pull(pid: str, body: PullIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    import re

    name = body.model.strip()
    if not re.match(NAME_RE, name) or len(name) > 200:
        raise ValueError("That doesn't look like a valid Ollama model name (e.g. llama3.1:8b).")
    job = ctx.pulls.start(_ollama(db, pid), name)
    return job.snapshot()


@router.get("/ollama/pulls")
def ollama_pulls(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"jobs": [j.snapshot() for j in ctx.pulls.jobs.values()]}


@router.get("/ollama/pulls/{job_id}/stream")
def ollama_pull_stream(job_id: str, ctx: AppContext = Depends(get_ctx)):
    return sse(ctx.pulls.subscribe(job_id))


@router.post("/ollama/pulls/{job_id}/cancel")
async def ollama_pull_cancel(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"cancelled": ctx.pulls.cancel(job_id)}


class DeleteModelIn(BaseModel):
    model: str
    confirm: bool = False


@router.post("/ollama/{pid}/delete")
async def ollama_delete(pid: str, body: DeleteModelIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not body.confirm:
        raise ValueError("Deleting a model requires explicit confirmation.")
    await ctx.adapter_for(_ollama(db, pid)).delete(body.model)
    return {"ok": True, "deleted": body.model}


@router.post("/ollama/quick-setup")
def ollama_quick_setup(ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Create the default local Ollama provider if it doesn't exist yet."""
    p = db.scalar(select(Provider).where(Provider.provider_type == "ollama"))
    if p is None:
        p = Provider(provider_type="ollama", display_name="Ollama (local)", base_url="http://localhost:11434")
        db.add(p)
        db.flush()
    return provider_out(ctx, p)


class LMStudioSetupIn(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    model_id: str
    make_default: bool = True


@router.get("/lmstudio/detect")
async def lmstudio_detect(base_url: str = "http://localhost:1234/v1") -> dict[str, Any]:
    """Look for LM Studio's local server and list its models with their context sizes."""
    from ..services import lmstudio
    return await lmstudio.detect(base_url)


@router.post("/lmstudio/setup")
async def lmstudio_setup(body: LMStudioSetupIn, ctx: AppContext = Depends(get_ctx),
                         db: Session = Depends(get_db)) -> dict[str, Any]:
    """One click: create (or reuse) the LM Studio connection and a model profile sized to the loaded context."""
    from ..services import lmstudio
    found = await lmstudio.detect(body.base_url)
    model = next((m for m in found["models"] if m["id"] == body.model_id), None)
    if model is None:
        if not found["reachable"]:
            raise ValueError(found.get("message") or "LM Studio is not reachable.")
        raise HTTPException(404, f"LM Studio does not list the model {body.model_id}.")
    return lmstudio.setup(db, body.base_url, model, make_default=body.make_default)
