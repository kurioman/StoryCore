"""Start Lumencia Story Desk from the project root (used by the start_* launchers)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from story.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
