"""Build a clean, shareable StoryCore ZIP (see 11_RELEASE_CHECKLIST.txt).

Usage, from the StoryCore folder:
    app\\python\\python.exe DEVONLY\\make_release.py            -> _release\\StoryCore_v<version>.zip
    app\\python\\python.exe DEVONLY\\make_release.py D:\\out     -> D:\\out\\StoryCore_v<version>.zip
    app\\python\\python.exe DEVONLY\\make_release.py --folder D:\\stage
        -> the same files, unzipped, without the .bat launchers: the input of the Windows installer
           (scripts\\release\\publish.ps1, which adds StoryCore.exe)

Only what a new player needs goes in. Never included: data/ (your stories, settings, keys, logs), backups,
_to_delete, _release, compiled __pycache__ folders of the engine, version-control and editor files, your music files
(Music/ ships with its README and an empty library) and personal developer material (SKIP_PATHS).
"""
from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = "StoryCore"  # folder name inside the ZIP

INCLUDE = ["Start StoryCore.bat", "Check Lore Packs.bat", "START_HERE.txt", "README.md", "RELEASE_NOTES.md", "CREDITS.md",
           "THIRD_PARTY_NOTICES.txt", "ARCHITECTURE.md", "LOREPACK_FORMAT.md", "REFACTOR_LOG.md",
           "DEVONLY", "app", "scripts", "Lorepack"]
# not in the installed app: StoryCore.exe starts it (scripts/release/ builds the installer, it is not shipped)
INSTALLER_SKIP = {"Start StoryCore.bat", "Check Lore Packs.bat"}
SKIP_DIRS = {"__pycache__", ".git", ".vscode", ".idea", "node_modules", ".venv"}
SKIP_FILES = {"Thumbs.db", "desktop.ini", ".DS_Store"}
# personal or obsolete developer material (the owner's GitHub push script, screenshots of the v1.7 interface)
SKIP_PATHS = {("scripts", "release"), ("DEVONLY", "Publier une mise a jour.bat"), ("DEVONLY", "frontend_inventory"), ("DEVONLY", "CONTEXTE_SESSION.md")}
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


def collect(installer: bool = False) -> list[Path]:
    files = []
    for name in INCLUDE:
        if installer and name in INSTALLER_SKIP:
            continue
        p = ROOT / name
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [f for f in sorted(p.rglob("*")) if f.is_file() and not skipped(f.relative_to(ROOT))]
        else:
            print(f"warning: {name} not found")
    return files


def make_folder(dest: Path) -> None:
    """The installer's input: same content as the ZIP, unzipped, minus the .bat launchers (StoryCore.exe replaces
    them, and they would keep the player's files inside the program folder that updates replace)."""
    if dest.exists():
        shutil.rmtree(dest)
    files = collect(installer=True)
    for f in files:
        out = dest / f.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
    music = dest / "Music"
    music.mkdir(parents=True, exist_ok=True)
    if (ROOT / "Music" / "README.txt").is_file():
        shutil.copy2(ROOT / "Music" / "README.txt", music / "README.txt")
    (music / "library.json").write_text(EMPTY_LIBRARY, encoding="utf-8")
    print(f"{dest}  ({len(files) + 1} files, version {version()})")


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--folder":
        make_folder(Path(sys.argv[2]))
        return
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_release"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"StoryCore_v{version()}.zip"
    files = collect()
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
