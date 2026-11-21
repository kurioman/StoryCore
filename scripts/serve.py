"""Start StoryCore from the project root (used by Start StoryCore.bat and by StoryCore.exe of the installed app)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

# Installed app only: Velopack hooks, update check, the player's folder. Must run before story.config is imported.
from story import installer  # noqa: E402

installer.startup()

from story.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
