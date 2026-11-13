"""Server-side secret storage.

Preference order: OS credential store via ``keyring`` (Windows Credential Manager,
macOS Keychain, Secret Service on Linux) -> restrictive local file in the data dir.
Secret values are never returned to the frontend, written to logs, or exported.
"""
from __future__ import annotations

import json
import logging
import os
import stat
import threading
from pathlib import Path

log = logging.getLogger(__name__)
SERVICE = "story-desk"


class SecretStore:
    backend_name = "base"
    warning: str | None = None

    def get(self, ref: str) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError

    def set(self, ref: str, value: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def delete(self, ref: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def known_values(self) -> list[str]:
        """Values used by the log redaction filter."""
        return []


class MemorySecretStore(SecretStore):
    backend_name = "memory"

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def set(self, ref: str, value: str) -> None:
        self._d[ref] = value

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)

    def known_values(self) -> list[str]:
        return list(self._d.values())


class FileSecretStore(SecretStore):
    backend_name = "file"
    warning = ("API keys are stored in a local file (data/secrets.json) with owner-only permissions "
               "because the OS credential store was unavailable. Keep the data folder private.")

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.error("secrets file unreadable; treating as empty")
            return {}

    def _write(self, d: dict[str, str]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        os.replace(tmp, self.path)

    def get(self, ref: str) -> str | None:
        with self._lock:
            return self._read().get(ref)

    def set(self, ref: str, value: str) -> None:
        with self._lock:
            d = self._read()
            d[ref] = value
            self._write(d)

    def delete(self, ref: str) -> None:
        with self._lock:
            d = self._read()
            if d.pop(ref, None) is not None:
                self._write(d)

    def known_values(self) -> list[str]:
        return list(self._read().values())


class KeyringSecretStore(SecretStore):
    backend_name = "keyring"

    def __init__(self) -> None:
        import keyring  # noqa: F401  (import errors are handled by make_secret_store)

        self._kr = keyring
        self._cache: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        if ref in self._cache:
            return self._cache[ref]
        v = self._kr.get_password(SERVICE, ref)
        if v:
            self._cache[ref] = v
        return v

    def set(self, ref: str, value: str) -> None:
        self._kr.set_password(SERVICE, ref, value)
        self._cache[ref] = value

    def delete(self, ref: str) -> None:
        self._cache.pop(ref, None)
        try:
            self._kr.delete_password(SERVICE, ref)
        except Exception:  # already absent
            pass

    def known_values(self) -> list[str]:
        return list(self._cache.values())


def make_secret_store(backend: str, data_dir: Path) -> SecretStore:
    if backend == "memory":
        return MemorySecretStore()
    if backend in ("auto", "keyring"):
        try:
            store = KeyringSecretStore()
            # round-trip probe: fails fast on headless Linux without a Secret Service
            probe = "__probe__"
            store.set(probe, "ok")
            ok = store.get(probe) == "ok"
            store.delete(probe)
            if ok:
                return store
        except Exception as e:  # pragma: no cover - environment specific
            log.warning("OS credential store unavailable (%s); using file fallback", type(e).__name__)
        if backend == "keyring":
            raise RuntimeError("keyring backend requested but unavailable")
    return FileSecretStore(data_dir / "secrets.json")


class RedactingFilter(logging.Filter):
    """Masks known secret values and common key shapes in log records."""

    import re as _re

    PATTERNS = [_re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), _re.compile(r"(x-api-key|authorization)[\"']?\s*[:=]\s*\S+", _re.I)]

    def __init__(self, store: SecretStore):
        super().__init__()
        self.store = store

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        red = msg
        for v in self.store.known_values():
            if v and len(v) >= 6:
                red = red.replace(v, "[REDACTED]")
        for p in self.PATTERNS:
            red = p.sub("[REDACTED]", red)
        if red != msg:
            record.msg, record.args = red, ()
        return True
