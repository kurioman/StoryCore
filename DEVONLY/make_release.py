"""Build a clean, shareable StoryCore ZIP (see 11_RELEASE_CHECKLIST.txt).

Usage, from the StoryCore folder:
    app\\python\\python.exe DEVONLY\\make_release.py            -> _release\\StoryCore_v<version>.zip
    app\\python\\python.exe DEVONLY\\make_release.py D:\\out     -> D:\\out\\StoryCore_v<version>.zip

Only what a new player needs goes in. Never included: data/ (your stories, settings, keys, logs), backups,
_to_delete, _release, compiled __pycache__ folders of the engine, version-control and editor files, your music files
(Music/ ships with its README and an empty library) and personal developer material (SKIP_PATHS).
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = "StoryCore"  # folder name inside the ZIP

INCLUDE = ["Start StoryCore.bat", "Check Lore Packs.bat", "START_HERE.txt", "README.md", "RELEASE_NOTES.md", "CREDITS.md",
           "THIRD_PARTY_NOTICES.txt", "ARCHITECTURE.md", "LOREPACK_FORMAT.md", "REFACTOR_LOG.md",
           "DEVONLY", "app", "scripts", "Lorepack"]
SKIP_DIRS = {"__pycache__", ".git", ".vscode", ".idea", "node_modules", ".venv"}
SKIP_FILES = {"Thumbs.db", "desktop.ini", ".DS_Store"}
# personal or obsolete developer material (the owner's GitHub push script, screenshots of the v1.7 interface)
SKIP_PATHS = {("DEVONLY", "Push vers GitHub.bat"), ("DEVONLY", "frontend_inventory")}
# the music library ships empty: the player's own tracks (Music/*.mp3) are never put in a release
EMPTY_LIBRARY = '{\n  "format_version": 1,\n  "_comment": "StoryCore music library: edit in the app (Music page) or by hand.",\n  "tracks": []\n}\n'


def skipped(rel: Path) -> bool:
    parts = rel.parts
    if any(parts[:len(sp)] == sp for sp in SKIP_PATHS):
        return True
    if any(p in SKIP_DIRS for p in parts):
        # the bundled Python's own standard-library caches are fine; only the engine's are stale
        return not (parts[:2] == ("app", "python") and "__pycache__" in parts)
    return rel.name in SKIP_FILES or rel.suffix in (".pyc", ".pyo") and parts[:2] != ("app", "python")


def version() -> str:
    m = re.search(r'APP_VERSION = "([^"]+)"', (ROOT / "app/backend/story/config.py").read_text(encoding="utf-8"))
    return m.group(1) if m else "dev"


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_release"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"StoryCore_v{version()}.zip"
    files = []
    for name in INCLUDE:
        p = ROOT / name
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [f for f in sorted(p.rglob("*")) if f.is_file() and not skipped(f.relative_to(ROOT))]
        else:
            print(f"warning: {name} not found")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files:
            zf.write(f, f"{TOP}/{f.relative_to(ROOT).as_posix()}")
        if (ROOT / "Music" / "README.txt").is_file():
            zf.write(ROOT / "Music" / "README.txt", f"{TOP}/Music/README.txt")
        zf.writestr(f"{TOP}/Music/library.json", EMPTY_LIBRARY)
        files.append(ROOT / "Music" / "library.json")
    size = out.stat().st_size / 1e6
    print(f"{out}  ({len(files)} files, {size:.0f} MB)")


if __name__ == "__main__":
    main()
