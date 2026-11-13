"""Check the lore packs from the project root (used by Check Lore Packs.bat)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from story.pack_check import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
