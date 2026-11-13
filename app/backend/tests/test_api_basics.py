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
