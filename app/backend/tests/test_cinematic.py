"""v0.6 "Cinematic" narration style (OOC.AI-like): its instructions reach the narrator with the protagonist's name, its
length target is in words, it is the default for new stories, and a stored list of presets receives it once."""
import json
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (puts the backend on sys.path)
from support import AppTestCase


class CinematicPresetTest(AppTestCase):
    def build(self, story_id):
        from story.models import Story
        from story.services import context_builder, story_tree
        with self.ctx.db.session() as db:
            s = db.get(Story, story_id)
            return context_builder.build(db, s, story_tree.get_branch(db, s), context_limit=16384,
                                         params={"max_tokens": 380})

    def test_new_story_uses_cinematic_with_the_heros_name(self):
        av = self.post("/avatars", {"name": "Kaïs", "profile": {"pronouns": "he/him"}})
        st = self.new_story("Ciné", world_slug="hero_chronicle", avatar_id=av["id"],
                            output_length="short (1–2 paragraphs)")
        self.assertEqual(st["settings_json"]["preset_id"], "cinematic")
        system = self.build(st["id"]).system
        self.assertIn("Style preset — Cinematic:", system)
        self.assertIn("call the protagonist Kaïs", system)
        self.assertNotIn("{name}", system)
        self.assertIn("Target response length: short (about 80–150 words)", system)
        self.assertNotIn("short (1–2 paragraphs)", system)

    def test_other_presets_keep_their_paragraph_target(self):
        st = self.new_story("Équilibré", preset_id="balanced", output_length="short (1–2 paragraphs)")
        system = self.build(st["id"]).system
        self.assertIn("Style preset — Balanced:", system)
        self.assertIn("Target response length: short (1–2 paragraphs)", system)

    def test_display_setting_accepts_cinematic(self):
        self.assertEqual(self.get("/settings")["dialogue_style"], "cinematic")
        r = self.client.put("/api/settings", json={"dialogue_style": "emphasis"})
        self.assertLess(r.status_code, 400, r.text)
        self.assertGreaterEqual(self.client.put("/api/settings", json={"dialogue_style": "neon"}).status_code, 400)
        self.client.put("/api/settings", json={"dialogue_style": "cinematic"})

    def test_an_edited_preset_list_still_offers_cinematic_to_the_narrator(self):
        # a stored list without "cinematic" (saved before v0.6): the built-in instructions are still found
        self.client.put("/api/settings", json={"narration_presets": [
            {"id": "balanced", "name": "Balanced", "instructions": "Mine."}]})
        try:
            st = self.new_story("Liste", preset_id="cinematic")
            self.assertIn("Style preset — Cinematic:", self.build(st["id"]).system)
        finally:
            from story.services.settings_service import NARRATION_PRESETS
            self.client.put("/api/settings", json={"narration_presets": NARRATION_PRESETS})


class MigrationTest(unittest.TestCase):
    def test_0011_appends_cinematic_to_a_stored_list_once(self):
        import sqlalchemy as sa
        from story.db import run_migrations
        tmp = Path(tempfile.mkdtemp(prefix="storycore_mig_"))
        engine = sa.create_engine(f"sqlite:///{tmp / 'm.db'}")
        run_migrations(engine, "0010")
        with engine.begin() as c:
            c.execute(sa.text("INSERT INTO app_settings (key, value_json) VALUES ('narration_presets', :v)"),
                      {"v": json.dumps([{"id": "mine", "name": "Mine", "instructions": "x"}])})
        run_migrations(engine)
        run_migrations(engine)  # already at head: nothing more
        with engine.connect() as c:
            value = c.execute(sa.text("SELECT value_json FROM app_settings WHERE key = 'narration_presets'")).scalar()
        presets = json.loads(value) if isinstance(value, str) else value
        self.assertEqual([p["id"] for p in presets], ["mine", "cinematic"])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
