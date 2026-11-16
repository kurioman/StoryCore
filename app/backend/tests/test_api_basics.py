"""Server health, settings validation, pages served, lore packs imported at start."""
from support import AppTestCase


class BasicsTest(AppTestCase):
    def test_health(self):
        h = self.get("/health")
        self.assertTrue(h["ok"])
        self.assertIn("version", h)

    def test_settings_roundtrip_and_validation(self):
        s = self.get("/settings")
        self.assertEqual(s["narration_language"], "en")
        r = self.client.put("/api/settings", json={"narration_language": "fr"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.get("/settings")["narration_language"], "fr")
        self.client.put("/api/settings", json={"narration_language": "en"})
        for bad in ({"narration_language": "xx"}, {"no_such_setting": 1}, {"story_font": "comic"}):
            r = self.client.put("/api/settings", json=bad)
            self.assertEqual(r.status_code, 400, f"{bad} should be refused: {r.text}")

    def test_state_changing_requests_need_the_client_header(self):
        r = self.client.post("/api/stories", json={"title": "x"}, headers={"X-Story-Client": ""})
        self.assertEqual(r.status_code, 403)

    def test_both_lore_packs_imported(self):
        worlds = {w["slug"]: w for w in self.get("/worlds")["worlds"]}
        self.assertIn("hero_chronicle", worlds)
        self.assertIn("lumencia_academy", worlds)
        chars = self.get(f"/worlds/{worlds['hero_chronicle']['id']}/entities?category=character")["entities"]
        self.assertEqual(len(chars), 21, [c["name"] for c in chars])
        self.assertIn("Selphina", {c["name"] for c in chars})

    def test_portraits_matched(self):
        chars = self.get("/assets/characters")["characters"]
        selphina = [c for c in chars if c["id"] == "selphina"]
        self.assertTrue(selphina, "Selphina has no portraits")
        self.assertEqual(sorted(int(k) for k in selphina[0]["slots"]), [1, 2, 3, 4, 5, 6])

    def test_interface_pages_served(self):
        for path in ("/", "/next/"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("<div id=\"root\">", r.text, path)

    def test_narration_languages_listed(self):
        langs = {l["code"] for l in self.get("/narration-languages")["languages"]}
        self.assertEqual(langs, {"en", "fr"})

    def test_developer_folders_are_not_offered_as_portrait_folders(self):
        names = {f["name"] for f in self.get("/onboarding")["image_folders"]}
        self.assertNotIn("DEVONLY", names)


class InterfaceSwitchTest(AppTestCase):
    import_packs = False

    def test_root_opens_the_interface_and_former_addresses_lead_to_it(self):
        from story.config import FRONTEND_DIST
        if not (FRONTEND_DIST / "index.html").is_file():
            self.skipTest("interface not built")
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="root"', r.text)
        self.assertIn('src="/assets/', r.text)  # built with base "/"
        self.assertEqual(self.client.get("/library").status_code, 200)  # unknown paths get the app too
        for former in ("/old", "/next", "/next/", "/next/index.html"):
            r = self.client.get(former, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers["location"]), (307, "/"), former)


class PortraitsPerWorldTest(AppTestCase):
    """v0.5: both shipped packs have a character with the id "lily" (and "beelzebub"). Each world must show its own
    pictures, never the other pack's."""

    def test_same_character_id_in_two_packs_keeps_its_own_portraits(self):
        from story.models import AssetManifestEntry, AssetRoot
        with self.ctx.db.session() as s:
            roots = {r.id: r for r in s.query(AssetRoot)}
            folder_of = {e.id: roots[e.root_id].path for e in s.query(AssetManifestEntry)}
            self.assertTrue(all(r.world_id for r in roots.values()), "pack image folders must belong to their world")
        for slug, folder in (("hero_chronicle", "hero_chronicle_images"), ("lumencia_academy", "lumencia_images")):
            world = self.world(slug)
            chars = {c["id"]: c for c in self.get(f"/assets/characters?world_id={world['id']}")["characters"]}
            for cid in ("lily", "beelzebub"):
                slots = chars[cid]["slots"]
                self.assertTrue(slots, f"{slug}: {cid} has no portrait")
                for asset_id in slots.values():
                    self.assertIn(folder, folder_of[asset_id], f"{slug}: {cid} uses a picture from another pack")


class LibraryCardTest(AppTestCase):
    """pack.json format 2 (v0.5): summary and tags per language reach the world; no cover gives a clean 404."""

    def test_library_card(self):
        for slug, tag_fr in (("hero_chronicle", "Isekai"), ("lumencia_academy", "Académie")):
            w = self.world(slug)
            lib = w["data_json"]["library"]
            self.assertTrue(lib["summary"]["en"] and lib["summary"]["fr"])
            self.assertIn(tag_fr, lib["tags"]["fr"])
            if not lib.get("cover"):
                self.assertEqual(self.client.get(f"/api/worlds/{w['id']}/cover").status_code, 404)

    def test_format_1_still_loads(self):
        import json
        import tempfile
        from pathlib import Path
        from story.services import pack_manifest
        with tempfile.TemporaryDirectory() as d:
            Path(d, "pack.json").write_text(json.dumps({"format_version": 1, "id": "old_pack", "name": "Old"}), "utf-8")
            m, rep = pack_manifest.load(Path(d))
            self.assertIsNotNone(m, rep)
            self.assertEqual(m["library"], {})


class OpeningsTest(AppTestCase):
    """v0.5: Hero's Chronicle has two openings (Avalon, the Demon King), Lumencia Academy one (Enrollment, 1 March)."""

    def test_pack_openings(self):
        hc = {s["id"]: s for s in self.world("hero_chronicle")["data_json"]["starters"]}
        self.assertEqual(set(hc), {"the_hero_summoned", "the_hero_and_the_demon_king"})
        self.assertIn("Avalon", hc["the_hero_summoned"]["blueprint"])
        self.assertIn("Beelzebub", hc["the_hero_and_the_demon_king"]["blueprint"])
        self.assertEqual(hc["the_hero_and_the_demon_king"]["i18n"]["name"]["fr"], "Début alternatif : le Roi Démon")
        self.assertEqual(hc["the_hero_summoned"]["name"], "The Summoned Hero")  # the engine keeps the English text
        self.assertEqual(self.get("/settings").get("starter_presets"), [])  # no generic openings any more
        for s in hc.values():
            self.assertEqual((s["scene"]["day"], s["scene"]["month"], s["scene"]["year"]), (1, 3, 1301))
        la = {s["id"]: s for s in self.world("lumencia_academy")["data_json"]["starters"]}
        self.assertEqual(set(la), {"enrollment"})
        self.assertEqual((la["enrollment"]["scene"]["day"], la["enrollment"]["scene"]["month"]), (1, 3))


class FirstRunTest(AppTestCase):
    """v0.5 first-run assistant: the setting that remembers it, and the graphics card endpoint (never fails)."""

    def test_onboarding_setting_and_gpu(self):
        self.assertFalse(self.get("/settings")["onboarding_done"])
        r = self.client.put("/api/settings", json={"onboarding_done": True})
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertTrue(self.get("/settings")["onboarding_done"])
        g = self.get("/system/gpu")
        self.assertIsInstance(g["gpus"], list)
