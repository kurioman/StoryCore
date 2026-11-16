"""Paths and runtime configuration.

Runtime data lives in ``<project>/data`` unless ``STORY_DATA_DIR`` is set.
Source lore and image folders are never written to.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIST = PROJECT_ROOT / "app" / "frontend" / "dist"
APP_VERSION = "1.7.0"
EXPORT_FORMAT_VERSION = 1


@dataclass
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8765
    # Extra origins allowed for state-changing requests (Vite dev server).
    dev_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    project_root: Path = PROJECT_ROOT
    secrets_backend: str = "auto"  # auto | keyring | file | memory
    music_dir_override: Optional[Path] = None  # tests use a throw-away folder

    @property
    def music_dir(self) -> Path:
        """The app's music library (v1.8): <project>/Music with library.json, shared by every story."""
        return self.music_dir_override or (self.project_root / "Music")

    @property
    def db_path(self) -> Path:
        # Points to a generic database name for multi-story support
        return self.data_dir / "stories.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.cache_dir, self.backups_dir, self.logs_dir, self.tmp_dir,
                  self.uploads_dir / "avatars", self.uploads_dir / "assets"):
            d.mkdir(parents=True, exist_ok=True)
        self._adopt_legacy_db()

    def _adopt_legacy_db(self) -> None:
        """First start after the rename: copy the old ``lumencia.db`` to ``stories.db`` (the old file is left untouched)."""
        legacy = self.data_dir / "lumencia.db"
        if self.db_path.exists() or not legacy.is_file():
            return
        import sqlite3

        src, dst = sqlite3.connect(legacy), sqlite3.connect(self.db_path)
        try:
            with dst:
                src.backup(dst)  # consistent copy, includes anything still in the WAL file
        finally:
            src.close()
            dst.close()


def load_settings() -> Settings:
    # Support both old and new environment variables for backward compatibility
    data_dir = Path(os.environ.get("STORY_DATA_DIR") or (PROJECT_ROOT / "data")).resolve()
    s = Settings(data_dir=data_dir)
    if os.environ.get("STORY_PORT"):
        s.port = int(os.environ.get("STORY_PORT", 8765))
    if os.environ.get("STORY_SECRETS_BACKEND"):
        s.secrets_backend = os.environ.get("STORY_SECRETS_BACKEND", "auto")
    
    return s
