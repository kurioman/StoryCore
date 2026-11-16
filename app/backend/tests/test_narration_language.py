"""v0.5 story language: the instruction reaches the narrator only for non-English stories."""
from support import AppTestCase


class NarrationLanguageTest(AppTestCase):
    def system_of(self, sid: str) -> str:
        return self.get(f"/stories/{sid}/context?full=true")["system"]

    def test_english_by_default(self):
        story = self.new_story("EN")
        system = self.system_of(story["id"])
        self.assertNotIn("Story language", system)

    def test_story_override_to_french(self):
        story = self.new_story("FR")
        r = self.client.patch(f"/api/stories/{story['id']}", json={"settings": {"narration_language": "fr"}})
        self.assertEqual(r.status_code, 200, r.text)
        system = self.system_of(story["id"])
        self.assertIn("# Story language: French", system)
        self.assertIn("Keep every portrait tag exactly in its format [Name:N]", system)
        # the language rule comes after the portrait-tag rule, near the end (highest priority)
        self.assertGreater(system.index("Story language"), system.index("Portrait tags"))

    def test_app_setting_applies_and_story_can_go_back_to_english(self):
        self.client.put("/api/settings", json={"narration_language": "fr"})
        try:
            a = self.new_story("App FR")
            self.assertIn("Story language: French", self.system_of(a["id"]))
            self.client.patch(f"/api/stories/{a['id']}", json={"settings": {"narration_language": "en"}})
            self.assertNotIn("Story language", self.system_of(a["id"]))
        finally:
            self.client.put("/api/settings", json={"narration_language": "en"})

    def test_turn_reminder_sent_with_the_player_message(self):
        story = self.new_story("FR turn")
        sid = story["id"]
        self.client.patch(f"/api/stories/{sid}", json={"settings": {"narration_language": "fr"}})
        start = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, start["assistant_message_id"])
        turn = self.post(f"/stories/{sid}/turns", {"content": "Je regarde autour de moi."})
        self.wait_reply(sid, turn["assistant_message_id"])
        # rebuild the request for that reply exactly as the engine sent it (without the reply itself)
        from story.models import Story
        from story.services import context_builder, story_tree
        with self.ctx.db.session() as db:
            s = db.get(Story, sid)
            built = context_builder.build(db, s, story_tree.get_branch(db, s),
                                          exclude_message_ids={turn["assistant_message_id"]})
            self.assertIn("Story language: French", built.system)
        # the opening request carries no reminder (small models copied such notes into the prologue)
        self.assertEqual(built.messages[0].content.count("Write your reply in French"), 0)
        last_user = [m for m in built.messages if m.role == "user"][-1]
        self.assertTrue(last_user.content.endswith("(Write your reply in French.)"), last_user.content[-120:])
