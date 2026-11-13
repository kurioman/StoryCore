"""Lore pack checker: the shipped packs pass; a damaged copy is reported precisely."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (puts the backend on sys.path)
from story.config import PROJECT_ROOT
from story.services.pack_check import check_all, check_pack, format_report

PACKS = PROJECT_ROOT / "Lorepack"


class PackCheckTest(unittest.TestCase):
    def test_shipped_packs_have_no_errors(self):
        reports = check_all(PACKS)
        self.assertGreaterEqual(len(reports), 2)
        for r in reports:
            self.assertTrue(r["ok"], format_report(r))
            self.assertGreater(r["stats"]["lore_records"], 10)

    def test_damaged_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "broken_pack"
            shutil.copytree(PACKS / "hero_chronicle_lore_pack", pack)
            images = pack / "hero_chronicle_images"
            # 1. invalid JSON in a lore file
            (pack / "lore" / "world.json").write_text('{"name": "Arche",\n  "era": oops}', encoding="utf-8")
            # 2. a portrait that matches nobody, and a missing expression
            shutil.copy(images / "riana_1.webp", images / "nobody_1.webp")
            (images / "riana_6.webp").unlink()
            # 3. the same picture for every expression of a character
            for n in range(2, 7):
                shutil.copy(images / "casey_1.webp", images / f"casey_{n}.webp")
            # 4. an opening whose portrait tag names nobody
            manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
            manifest["starters"][0]["blueprint"] += '\n[Ghost:2] "Boo."'
            (pack / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")

            r = check_pack(pack)
            text = format_report(r)
            self.assertFalse(r["ok"], text)
            self.assertTrue(any("lore/world.json: invalid JSON at line 2" in e for e in r["errors"]), text)
            self.assertTrue(any("nobody_1.webp" in w for w in r["warnings"]), text)
            self.assertTrue(any(w.startswith("Riana") and "6 (love/shy)" in w for w in r["warnings"]), text)
            self.assertTrue(any(w.startswith("Casey") and "same picture" in w for w in r["warnings"]), text)
            self.assertTrue(any("[Ghost" in w for w in r["warnings"]), text)

    def test_missing_folder_and_missing_manifest(self):
        self.assertFalse(check_pack(Path("/no/such/folder"))["ok"])
        with tempfile.TemporaryDirectory() as tmp:
            r = check_pack(Path(tmp))
            self.assertFalse(r["ok"])
            self.assertIn("pack.json", " ".join(r["errors"]))

    def test_api_endpoint(self):
        from support import AppTestCase  # noqa: F401
        from fastapi.testclient import TestClient
        from story.config import Settings
        from story.main import create_app
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Settings(data_dir=Path(tmp) / "data", secrets_backend="memory"), testing=True)
            with TestClient(app) as client:
                r = client.get("/api/lore/packs/check")
                self.assertEqual(r.status_code, 200, r.text)
                self.assertGreaterEqual(len(r.json()["packs"]), 2)
