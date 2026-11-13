"""Engine/session management and Alembic migrations."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _sqlite_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - trivial
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def make_engine(db_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def alembic_config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%"))
    return cfg


def run_migrations(engine: Engine, revision: str = "head") -> None:
    cfg = alembic_config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head_revision(engine: Engine) -> str | None:
    return ScriptDirectory.from_config(alembic_config(engine)).get_current_head()


class Database:
    def __init__(self, db_path: Path):
        self.path = db_path
        self.engine = make_engine(db_path)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def migrate(self, backup_dir: Path | None = None) -> Path | None:
        """Upgrade to head. If an existing database is behind, a consistent copy is saved first (recovery point)."""
        backup = None
        if backup_dir is not None and self.path.is_file() and self.path.stat().st_size > 0:
            cur, head = current_revision(self.engine), head_revision(self.engine)
            if cur is not None and cur != head:
                import sqlite3
                from datetime import datetime

                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / f"pre_migration_{cur}_to_{head}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
                src, dst = sqlite3.connect(self.path), sqlite3.connect(backup)
                with dst:
                    src.backup(dst)
                src.close()
                dst.close()
        run_migrations(self.engine)
        return backup

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def dispose(self) -> None:
        self.engine.dispose()
