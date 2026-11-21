"""Installed copy (``StoryCore-win-Setup.exe``): Velopack hooks, the player's folder, update check at launch.

An installed StoryCore lives in ``%LOCALAPPDATA%\\StoryCore``: ``Update.exe`` next to a ``current\\`` folder that every
update replaces. The player's files therefore live elsewhere, in ``%APPDATA%\\StoryCore`` (``Lorepack\\``, ``Music\\``,
``data\\``), and the worlds shipped with the app are copied there.

Nothing here runs for an extracted folder started with ``Start StoryCore.bat``: that copy keeps everything in its own
folder, as before. This module only uses the standard library (and ``velopack`` when installed), because it runs
before ``story.config`` is imported.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Optional

REPO_URL = "https://github.com/kurioman/StoryCore"
APP_ROOT = Path(__file__).resolve().parents[3]
SHIPPED_STATE = ".shipped.json"
CHECK_TIMEOUT_S = 10


def install_root() -> Optional[Path]:
    """The Velopack root (``<root>\\Update.exe`` + ``<root>\\current``) when this copy was installed, else None."""
    if sys.platform != "win32":
        return None
    root = APP_ROOT.parent
    if APP_ROOT.name.lower() == "current" and (root / "Update.exe").is_file():
        return root
    return None


def user_root() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "StoryCore"


def _say(text: str = "") -> None:
    print(f"  {text}" if text else "", flush=True)


# --------------------------------------------------------------------------- Velopack
def run_velopack_hooks() -> None:
    """Must run first: during install, update and uninstall, Velopack starts the app with ``--veloapp-...`` arguments
    and this call answers them and ends the process. It also applies an update that was downloaded but not applied."""
    try:
        import velopack
    except ImportError:
        _say("Update support is missing from this copy (velopack). StoryCore starts without it.")
        return
    # The real command line is "python.exe <options> serve.py <args>": give Velopack only the app's own arguments.
    velopack.App().set_args(list(sys.argv[1:])).run()


def check_for_update() -> None:
    """Looks for a newer release on GitHub; if there is one, downloads it, installs it and restarts StoryCore.
    Never stops the app: no network, a slow answer or any error simply starts the current version."""
    try:
        import velopack
    except ImportError:
        return
    result: dict[str, Any] = {}

    def work() -> None:
        try:
            mgr = velopack.UpdateManager(velopack.GithubSource(REPO_URL))
            result["mgr"] = mgr
            result["info"] = mgr.check_for_updates()
        except Exception as e:  # noqa: BLE001 - any failure means "start this version"
            result["error"] = e

    _say("Checking for updates...")
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(CHECK_TIMEOUT_S)
    if t.is_alive():
        _say("The update check is taking too long. Starting this version.")
        return
    if "error" in result:
        _say(f"Could not check for updates ({type(result['error']).__name__}). Starting this version.")
        return
    info, mgr = result.get("info"), result.get("mgr")
    if not info or mgr is None:
        _say(f"StoryCore {mgr.get_current_version() if mgr else ''} is up to date.".replace("  ", " "))
        return
    new = info.TargetFullRelease.Version
    _say()
    _say(f"A new version of StoryCore is available: {new}. Downloading...")

    def progress(p: Any, *_: Any) -> None:
        print(f"\r  {p}%   ", end="", flush=True)

    try:
        mgr.download_updates(info, progress)
    except Exception as e:  # noqa: BLE001
        _say()
        _say(f"The download failed ({type(e).__name__}). Starting this version; the update will be tried next time.")
        return
    _say()
    _say(f"Installing StoryCore {new}. It restarts by itself in a few seconds.")
    mgr.apply_updates_and_restart(info)
    sys.exit(0)  # not reached: the call above ends the process


# --------------------------------------------------------------------------- the player's folder
def _fingerprint(folder: Path) -> list[list[Any]]:
    """Files of a folder with size and modification time (copies keep the time, so an untouched copy matches)."""
    out: list[list[Any]] = []
    for f in sorted(folder.rglob("*")):
        if f.is_file():
            st = f.stat()
            out.append([f.relative_to(folder).as_posix(), st.st_size, int(st.st_mtime)])
    return out


def _read_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _replace_folder(src: Path, dst: Path) -> None:
    tmp, old = dst.with_name(dst.name + ".updating"), dst.with_name(dst.name + ".old")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    shutil.copytree(src, tmp)
    dst.rename(old)
    tmp.rename(dst)
    shutil.rmtree(old, ignore_errors=True)


def seed_user_folder(user: Path, app_version: str, app_root: Path = APP_ROOT) -> list[str]:
    """Copies the worlds and music shipped with the app into the player's folder.

    A shipped world is copied when it is new, and replaced by the newer shipped version only while the player's copy
    is exactly what was copied last time. A world the player changed or deleted is left as it is. Runs once per
    app version. Returns what was done (for the log)."""
    user.mkdir(parents=True, exist_ok=True)
    state_file = user / SHIPPED_STATE
    state = _read_state(state_file)
    if state.get("app_version") == app_version and state.get("app_root") == str(app_root):
        return []
    done: list[str] = []
    recorded: dict[str, Any] = state.get("packs") if isinstance(state.get("packs"), dict) else {}
    new_state: dict[str, Any] = {}
    src_packs, dst_packs = app_root / "Lorepack", user / "Lorepack"
    dst_packs.mkdir(parents=True, exist_ok=True)
    for src in sorted(p for p in src_packs.iterdir() if p.is_dir()) if src_packs.is_dir() else []:
        dst, before = dst_packs / src.name, recorded.get(src.name)
        try:
            if dst.exists():
                if before is None or _fingerprint(dst) != before:
                    if before is not None:
                        new_state[src.name] = before
                        done.append(f"{src.name}: kept (changed by the player)")
                    continue
                if _fingerprint(src) == before:
                    new_state[src.name] = before
                    continue
                _replace_folder(src, dst)
                done.append(f"{src.name}: updated")
            elif before is not None:
                new_state[src.name] = before  # the player deleted it: do not bring it back
                continue
            else:
                shutil.copytree(src, dst)
                done.append(f"{src.name}: added")
            new_state[src.name] = _fingerprint(dst)
        except OSError as e:
            done.append(f"{src.name}: could not be copied ({e})")
            if before is not None:
                new_state[src.name] = before
    music_src, music_dst = app_root / "Music", user / "Music"
    if music_src.is_dir() and not music_dst.exists():
        shutil.copytree(music_src, music_dst)
        done.append("Music: added")
    tmp = state_file.with_name(SHIPPED_STATE + ".tmp")
    tmp.write_text(json.dumps({"app_version": app_version, "app_root": str(app_root), "packs": new_state}, indent=1),
                   encoding="utf-8")
    tmp.replace(state_file)
    return done


# --------------------------------------------------------------------------- entry point
def startup() -> None:
    """Called by ``scripts/serve.py`` before anything else. Does nothing for an extracted folder."""
    if install_root() is None:
        return
    run_velopack_hooks()
    user = user_root()
    os.environ.setdefault("STORY_USER_ROOT", str(user))
    if not os.environ.get("STORYCORE_NO_UPDATE"):
        check_for_update()
    from .config import APP_VERSION  # after STORY_USER_ROOT is set

    try:
        for line in seed_user_folder(user, APP_VERSION):
            _say(line)
    except OSError as e:
        _say(f"Your StoryCore folder could not be prepared ({e}).")
    _say(f"Your worlds, music and saves are in {user}")
