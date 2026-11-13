"""Command line: check lore packs and print a readable report.

    python -m story.pack_check                 every pack in <project>/Lorepack
    python -m story.pack_check <folder> ...    the given pack folders
    python -m story.pack_check --json ...      machine-readable output

Exit code 1 when a pack has errors (warnings alone exit 0). Nothing in the data folder is read or written.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import PROJECT_ROOT
from .services.pack_check import ascii_safe, check_all, check_pack, format_report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="story.pack_check", description="Check StoryCore lore packs.")
    ap.add_argument("folders", nargs="*", help="pack folders (default: every pack in the Lorepack folder)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
    reports = [check_pack(Path(f)) for f in args.folders] if args.folders else check_all(PROJECT_ROOT / "Lorepack")
    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    else:
        if not reports:
            print("No lore pack found (a pack is a folder with a pack.json inside Lorepack).")
        text = "\n\n".join(format_report(r) for r in reports)
        enc = (sys.stdout.encoding or "").lower()
        print(text if enc.startswith("utf") else ascii_safe(text))
    return 0 if all(r["ok"] for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
