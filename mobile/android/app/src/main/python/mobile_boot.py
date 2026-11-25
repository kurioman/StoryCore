"""StoryCore mobile: starts the shared engine (app/backend/story) inside the Android app.

Called from MainActivity.kt through Chaquopy. The engine code is the very same as on PC; this file only does what
``scripts/serve.py`` and ``story/__main__.py`` do there: choose the folders, then start the server on 127.0.0.1.
The app's WebView then opens http://127.0.0.1:8765/.

Folders on the phone (all inside the app's private storage):
    <home>/Lorepack, <home>/Music   copied from the APK by MainActivity
    <home>/data                     the player's database, saves, keys, logs (never touched by updates)
    <web>                           the built interface (app/frontend/dist), copied from the APK
"""
from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
import traceback
import urllib.request
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"

# (module to import, package name for the version)
LIBRARIES = [
    ("sqlite3", None),
    ("pydantic_core", "pydantic-core"),
    ("pydantic", "pydantic"),
    ("fastapi", "fastapi"),
    ("starlette", "starlette"),
    ("uvicorn", "uvicorn"),
    ("httpx", "httpx"),
    ("sqlalchemy", "sqlalchemy"),
    ("alembic", "alembic"),
    ("mako", "mako"),
    ("markupsafe", "markupsafe"),
    ("multipart", "python-multipart"),
    ("PIL", "pillow"),
]

_lock = threading.Lock()
_state: dict = {"status": "idle", "report": [], "error": None, "seconds": None}


def _note(line: str) -> None:
    _state["report"].append(line)
    print(f"[StoryCore boot] {line}", flush=True)


def check_libraries() -> bool:
    """Import every library the engine needs and note its version. Returns False if one is missing."""
    ok = True
    for module, dist in LIBRARIES:
        try:
            m = import_module(module)
            if dist:
                try:
                    v = version(dist)
                except PackageNotFoundError:
                    v = getattr(m, "__version__", "?")
            else:
                v = getattr(m, "sqlite_version", "?")
            _note(f"OK   {module} {v}")
        except Exception as e:  # noqa: BLE001 - every failure is reported, none is fatal here
            ok = False
            _note(f"FAIL {module}: {type(e).__name__}: {e}")
    return ok


def start(home: str, web_dir: str) -> str:
    """Start the engine once (later calls return at once). Blocks until it answers or fails. Returns the URL."""
    with _lock:
        if _state["status"] == "ready":
            return URL
        _state.update(status="starting", report=[], error=None)
        t0 = time.monotonic()
        try:
            _note(f"Python {sys.version.split()[0]} on {platform.machine()} ({platform.platform()})")
            if not check_libraries():
                raise RuntimeError("A library is missing (see the lines marked FAIL).")
            import android_webp  # Lore pack pictures are WebP: Chaquopy's Pillow needs Android's decoder for them
            _note("WebP: Android decoder" if android_webp.install() else "WebP: Pillow's own decoder")

            home_p = Path(home)
            # Same switches as the installed PC app (scripts/serve.py); must be set before story.config is imported.
            os.environ["STORY_USER_ROOT"] = str(home_p)
            os.environ["STORY_DATA_DIR"] = str(home_p / "data")
            os.environ["STORY_SECRETS_BACKEND"] = "file"  # no OS credential store on Android: data/secrets.json
            os.environ["STORY_PORT"] = str(PORT)

            import story.config as config
            config.FRONTEND_DIST = Path(web_dir)  # the interface is copied next to the data, not under the engine
            from story.config import load_settings
            from story.main import create_app

            settings = load_settings()
            app = create_app(settings)
            packs = sorted(p.name for p in (home_p / "Lorepack").iterdir() if p.is_dir()) \
                if (home_p / "Lorepack").is_dir() else []
            _note(f"Engine created (StoryCore {config.APP_VERSION}); Lore packs found: {', '.join(packs) or 'none'}")

            import uvicorn
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning",
                                                   lifespan="on"))
            threading.Thread(target=server.run, name="storycore-server", daemon=True).start()

            deadline = time.monotonic() + 300  # a first start imports the Lore packs: slow phones need time
            while True:
                try:
                    with urllib.request.urlopen(URL + "api/health", timeout=2) as r:
                        _note(f"Server answers: {r.read(200).decode('utf-8', 'replace')}")
                    break
                except Exception:
                    if server.should_exit or time.monotonic() > deadline:
                        raise RuntimeError("The server did not start (see the app log).")
                    time.sleep(0.25)

            _state["seconds"] = round(time.monotonic() - t0, 1)
            _note(f"Ready in {_state['seconds']} s")
            _state["status"] = "ready"
            return URL
        except Exception as e:
            _state["status"] = "failed"
            _state["error"] = "".join(traceback.format_exception(e))
            _note(f"FAILED: {type(e).__name__}: {e}")
            raise


def status_json() -> str:
    """The boot report, shown by MainActivity when something goes wrong."""
    return json.dumps(_state, ensure_ascii=False)
