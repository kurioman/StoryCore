"""Installed app: shipped worlds are copied to the player's folder, updated while untouched, never over the player's
changes, and not brought back once deleted."""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import support  # noqa: F401  (puts the backend on sys.path)
from story import installer


def make_pack(root: Path, name: str, text: str) -> Path:
    d = root / "Lorepack" / name
    (d / "lore").mkdir(parents=True, exist_ok=True)
    (d / "pack.json").write_text('{"id": "%s"}' % name, encoding="utf-8")
    (d / "lore" / "world.json").write_text(text, encoding="utf-8")
    return d


def touch_later(path: Path, seconds: int = 5) -> None:
    t = time.time() + seconds
    os.utime(path, (t, t))


class SeedUserFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.app, self.user = self.tmp / "app", self.tmp / "user"
        make_pack(self.app, "a_lore_pack", '{"v": 1}')
        make_pack(self.app, "b_lore_pack", '{"v": 1}')
        (self.app / "Music").mkdir(parents=True)
        (self.app / "Music" / "library.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seed(self, version):
        return installer.seed_user_folder(self.user, version, self.app)

    def test_first_start_copies_everything(self):
        done = self.seed("1.0.0")
        self.assertIn("a_lore_pack: added", done)
        self.assertTrue((self.user / "Lorepack" / "b_lore_pack" / "pack.json").is_file())
        self.assertTrue((self.user / "Music" / "library.json").is_file())
        self.assertEqual(self.seed("1.0.0"), [])  # same version: nothing to do

    def test_update_replaces_untouched_keeps_changed_and_deleted(self):
        self.seed("1.0.0")
        # player edits pack a, deletes pack b
        f = self.user / "Lorepack" / "a_lore_pack" / "lore" / "world.json"
        f.write_text('{"v": "mine"}', encoding="utf-8")
        shutil.rmtree(self.user / "Lorepack" / "b_lore_pack")
        # new app version changes both packs and ships a new one
        for name in ("a_lore_pack", "b_lore_pack"):
            g = make_pack(self.app, name, '{"v": 2}') / "lore" / "world.json"
            touch_later(g)
        make_pack(self.app, "c_lore_pack", '{"v": 2}')
        done = self.seed("1.1.0")
        self.assertIn("a_lore_pack: kept (changed by the player)", done)
        self.assertIn("c_lore_pack: added", done)
        self.assertEqual(f.read_text(encoding="utf-8"), '{"v": "mine"}')
        self.assertFalse((self.user / "Lorepack" / "b_lore_pack").exists())

    def test_update_replaces_an_untouched_pack(self):
        self.seed("1.0.0")
        g = make_pack(self.app, "a_lore_pack", '{"v": 2}') / "lore" / "world.json"
        touch_later(g)
        done = self.seed("1.1.0")
        self.assertIn("a_lore_pack: updated", done)
        f = self.user / "Lorepack" / "a_lore_pack" / "lore" / "world.json"
        self.assertEqual(f.read_text(encoding="utf-8"), '{"v": 2}')
        self.assertFalse((self.user / "Lorepack" / "a_lore_pack.old").exists())
        # and it is still tracked: the next update replaces it again
        touch_later(make_pack(self.app, "a_lore_pack", '{"v": 3}') / "lore" / "world.json", 10)
        self.assertIn("a_lore_pack: updated", self.seed("1.2.0"))

    def test_extracted_folder_is_not_an_install(self):
        self.assertIsNone(installer.install_root())


if __name__ == "__main__":
    unittest.main()
