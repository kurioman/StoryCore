"""Run the engine tests (app/backend/tests) with any Python 3.11+ that has the app's packages, including the one
bundled in app/python. Usage: run_tests.bat (Windows), or python DEVONLY/run_tests.py [-v] [test name ...]."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "app" / "backend" / "tests"
sys.path[:0] = [str(ROOT / "app" / "backend"), str(TESTS)]  # the bundled Python ignores the script folder

if __name__ == "__main__":
    verbose = "-v" in sys.argv
    names = [a for a in sys.argv[1:] if a != "-v"]
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromNames(names) if names else loader.discover(str(TESTS), top_level_dir=str(TESTS))
    result = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
