"""Bug report zip: useful content, and never a key or story text."""
import io
import json
import zipfile

from support import AppTestCase

SECRET = "sk-or-v1-THISISASECRETKEY1234567890"
STORY_TEXT = "The lighthouse keeper whispers the forbidden name."


class BugReportTest(AppTestCase):
    def test_report_content_and_privacy(self):
        # a provider with a key, and a story with a recognisable sentence
        p = self.post("/providers", {"provider_type": "openai_compat", "display_name": "OpenRouter",
                                     "base_url": "https://user:pw@openrouter.ai/api/v1?token=abc", "api_key": SECRET})
        story = self.new_story("Secret title")
        start = self.post(f"/stories/{story['id']}/start")
        self.wait_reply(story["id"], start["assistant_message_id"])
        turn = self.post(f"/stories/{story['id']}/turns", {"content": STORY_TEXT})
        self.wait_reply(story["id"], turn["assistant_message_id"])
        # even a careless log line holding the key is masked in the report
        log = self.ctx.settings.logs_dir / "app.log"
        log.write_text(f"2026-11-13 INFO story: test line with {SECRET} inside\n", encoding="utf-8")

        r = self.client.get("/api/system/bug-report")
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertIn("attachment", r.headers["content-disposition"])
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = set(z.namelist())
        for expected in ("README.txt", "system.json", "settings.json", "providers.json", "generations.json",
                         "stories.json", "lore_packs.json", "integrity.json"):
            self.assertIn(expected, names)
        everything = "\n".join(z.read(n).decode("utf-8", errors="replace") for n in names)
        self.assertIn("logs/app.log", names)
        self.assertIn("test line with [REDACTED] inside", z.read("logs/app.log").decode())
        self.assertNotIn(SECRET, everything)
        self.assertNotIn("THISISASECRETKEY", everything)
        self.assertNotIn("lighthouse keeper", everything)
        self.assertNotIn("Secret title", everything)
        self.assertNotIn("user:pw", everything)
        self.assertNotIn("token=abc", everything)

        providers = json.loads(z.read("providers.json"))
        orouter = [x for x in providers if x["name"] == "OpenRouter"][0]
        self.assertTrue(orouter["has_api_key"])
        self.assertEqual(orouter["base_url"], "https://openrouter.ai/api/v1")
        system = json.loads(z.read("system.json"))
        self.assertIn("app_version", system)
        gens = json.loads(z.read("generations.json"))
        self.assertTrue(gens and all("status" in g for g in gens))
        stories = json.loads(z.read("stories.json"))
        self.assertTrue(any(s["id"] == story["id"] and s["messages"] == 4 for s in stories))

    def test_report_with_description_and_context(self):
        story = self.new_story("Secret title")
        start = self.post(f"/stories/{story['id']}/start")
        self.wait_reply(story["id"], start["assistant_message_id"])
        r = self.client.post("/api/system/bug-report", json={
            "description": "Les images de Hero's Chronicle apparaissent dans l'autre pack.",
            "story_id": story["id"], "page": "/story/x"})
        self.assertEqual(r.status_code, 200, r.text[:300])
        z = zipfile.ZipFile(io.BytesIO(r.content))
        self.assertIn("description.txt", z.namelist())
        self.assertIn("images de Hero's Chronicle", z.read("description.txt").decode("utf-8"))
        context = json.loads(z.read("context.json"))
        self.assertEqual(context["page"], "/story/x")
        self.assertEqual(context["story"]["id"], story["id"])
        self.assertNotIn("Secret title", z.read("context.json").decode("utf-8"))
        # no description and no story: the zip is still made, without those two files
        r = self.client.post("/api/system/bug-report", json={})
        self.assertEqual(r.status_code, 200, r.text[:300])
        names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        self.assertNotIn("description.txt", names)
