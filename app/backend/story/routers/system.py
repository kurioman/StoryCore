from __future__ import annotations

from pathlib import Path

import os
import platform
import subprocess
import sys
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import APP_VERSION
from ..deps import get_ctx, get_db
from ..models import AssetRoot, World
from ..services import assets as assets_svc
from ..services import backup as backup_svc
from ..services import lore_import, settings_service
from ..services.runtime import AppContext

router = APIRouter(tags=["system"])


@router.get("/health")
def health(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"ok": True, "version": APP_VERSION, "data_dir": str(ctx.settings.data_dir),
            "secrets_backend": ctx.secrets.backend_name, "secrets_warning": ctx.secrets.warning,
            "platform": platform.system()}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return settings_service.get_all(db)


@router.get("/prompt-profiles")
def prompt_profiles() -> dict[str, Any]:
    from ..services.context_builder import DEFAULT_PROMPT_PROFILE, PROMPT_PROFILES
    return {"default": DEFAULT_PROMPT_PROFILE, "profiles": [{"id": k, "label": v["label"]} for k, v in PROMPT_PROFILES.items()]}


@router.get("/narration-languages")
def narration_languages() -> dict[str, Any]:
    from ..services.narration_language import DEFAULT, LANGUAGES
    return {"default": DEFAULT, "languages": [{"code": k, "label": v} for k, v in LANGUAGES.items()]}


@router.put("/settings")
def put_settings(values: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    bad = [k for k in values if k not in settings_service.DEFAULTS]
    if bad:
        raise ValueError(f"Unknown setting(s): {', '.join(bad)}")
    if "context_layout" in values and values["context_layout"] not in ("stable", "classic"):
        raise ValueError("context_layout must be stable or classic")
    if "event_capture_mode" in values and values["event_capture_mode"] not in ("off", "manual", "batch", "after_each_turn"):
        raise ValueError("event_capture_mode must be off, manual, batch or after_each_turn")
    if values.get("narrator_prompt_profile") is not None:
        from ..services.context_builder import PROMPT_PROFILES
        if values["narrator_prompt_profile"] not in PROMPT_PROFILES:
            raise ValueError(f"narrator_prompt_profile must be one of {', '.join(PROMPT_PROFILES)}")
    if "turn_analysis_mode" in values and values["turn_analysis_mode"] not in settings_service.ANALYSIS_MODES:
        raise ValueError("turn_analysis_mode must be always, local_only or off")
    if "relationship_mode" in values and values["relationship_mode"] not in settings_service.RELATIONSHIP_MODES:
        raise ValueError("relationship_mode must be auto_conservative, review or off")
    if "story_font" in values and values["story_font"] not in ("sans", "serif"):
        raise ValueError("story_font must be sans or serif")
    if "dialogue_style" in values and values["dialogue_style"] not in ("cinematic", "emphasis", "classic"):
        raise ValueError("dialogue_style must be cinematic, emphasis or classic")
    if "narration_language" in values:
        from ..services.narration_language import LANGUAGES
        if values["narration_language"] not in LANGUAGES:
            raise ValueError(f"narration_language must be one of {', '.join(LANGUAGES)}")
    return settings_service.set_many(db, values)


@router.get("/onboarding")
def onboarding(ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    worlds = db.scalar(select(func.count()).select_from(World)) or 0
    roots = [r.path for r in db.scalars(select(AssetRoot))]
    lore = lore_import.discover(ctx.settings.project_root)
    imported_paths = {w.source_path for w in db.scalars(select(World))}
    for c in lore:
        c["imported"] = c["path"] in imported_paths
    folders = assets_svc.discover_image_folders(ctx.settings.project_root)
    for f in folders:
        # a folder that holds registered portrait folders (e.g. Lorepack, whose packs' image folders are registered at
        # start) is covered already: registering it too would index the same portraits twice
        inside = [r for r in roots if Path(r).is_relative_to(Path(f["path"]))]
        f["registered"] = f["path"] in roots or bool(inside)
    return {"worlds": worlds, "asset_roots": len(roots), "lore_candidates": lore, "image_folders": folders,
            "dismissed": settings_service.get(db, "onboarding_dismissed")}


@router.get("/system/paths")
def paths(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    s = ctx.settings
    return {"data_dir": str(s.data_dir), "database": str(s.db_path), "uploads": str(s.uploads_dir),
            "backups": str(s.backups_dir), "logs": str(s.logs_dir), "cache": str(s.cache_dir),
            "secrets": "OS credential store" if ctx.secrets.backend_name == "keyring" else str(s.data_dir / "secrets.json")}


@router.post("/system/open-data-folder")
def open_data_folder(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    p = str(ctx.settings.data_dir)  # only ever the app's own data folder
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
        return {"ok": True, "path": p}
    except Exception as e:
        return {"ok": False, "path": p, "error": f"Could not open the folder automatically ({type(e).__name__}). Path: {p}"}


@router.post("/system/clear-logs")
def clear_logs(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    n = 0
    for f in ctx.settings.logs_dir.glob("*.log*"):
        try:
            f.write_text("", encoding="utf-8")
            n += 1
        except OSError:
            pass
    return {"cleared": n}


@router.get("/system/logs")
def read_logs(ctx: AppContext = Depends(get_ctx), lines: int = 200) -> dict[str, Any]:
    f = ctx.settings.logs_dir / "app.log"
    if not f.is_file():
        return {"lines": []}
    return {"lines": f.read_text(encoding="utf-8", errors="replace").splitlines()[-min(lines, 1000):]}


@router.get("/system/bug-report")
def bug_report(ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    """A zip for reporting a problem: versions, logs, settings, providers (never keys), lore pack check, recent
    generation figures. No story text, no secrets (services/bug_report.py)."""
    from fastapi.responses import Response
    from ..services import bug_report
    name, data = bug_report.build(ctx, db)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


class BugReportIn(BaseModel):
    description: str | None = Field(default=None, max_length=20_000)
    story_id: str | None = None
    page: str | None = Field(default=None, max_length=200)


@router.post("/system/bug-report")
def bug_report_with_description(body: BugReportIn, ctx: AppContext = Depends(get_ctx), db: Session = Depends(get_db)):
    """Same zip, plus what the player wrote and where they were (the red "Report a problem" button)."""
    from fastapi.responses import Response
    from ..services import bug_report
    name, data = bug_report.build(ctx, db, description=body.description,
                                  context={"page": body.page, "story_id": body.story_id})
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/system/gpu")
def gpu() -> dict[str, Any]:
    """Graphics cards and their video memory, for the first-run assistant's model advice (NVIDIA only)."""
    from ..services import hardware
    return hardware.gpus()


@router.get("/system/integrity")
def integrity(db: Session = Depends(get_db)) -> dict[str, Any]:
    return backup_svc.integrity_check(db)
