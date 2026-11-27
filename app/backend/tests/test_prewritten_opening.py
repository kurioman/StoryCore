"""v0.7.6 (Kurio's test of 0.7.5): an opening written by the author is shown as written, without the model; the
protagonist's card stays the narrator's knowledge."""
import unittest

import support  # noqa: F401  (puts the backend on sys.path)
from support import AppTestCase

from story.providers import adapters

CALLS = []
_orig = adapters.MockAdapter.stream_chat


async def _spy(self, model, system, messages, params):
    CALLS.append((system, messages))
    async for x in _orig(self, model, system, messages, params):
        yield x


class PrewrittenOpeningTest(AppTestCase):
    @classmethod
    def setUpClass(cls):
        adapters.MockAdapter.stream_chat = _spy
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        adapters.MockAdapter.stream_chat = _orig
        super().tearDownClass()

    def test_lumencia_enrollment_is_shown_word_for_word(self):
        w = self.world("lumencia_academy")
        av = self.post("/avatars", {"name": "Kai", "profile": {"abilities": "Shadow Step: a secret blink technique."}})
        s = self.post("/stories", {"title": "t", "world_id": w["id"], "starter_id": "enrollment", "avatar_id": av["id"]})
        CALLS.clear()
        r = self.post(f"/stories/{s['id']}/start")
        self.assertTrue(r.get("prewritten"))
        m = self.wait_reply(s["id"], r["assistant_message_id"])
        self.assertEqual(m["status"], "complete")
        self.assertTrue(m["content"].startswith("The chill of dawn had not yet fully lifted"))
        self.assertTrue(m["content"].endswith("\"Choose well. Your year begins now.\""))
        self.assertNotIn("[Emily:", m["content"])  # the portrait tags are read, not shown
        self.assertFalse(CALLS)  # no narrator request for the opening
        import time
        from story.models import Message
        for _ in range(50):  # the portraits are placed right after the reply is saved
            with self.ctx.db.session() as db:
                md = db.get(Message, m["id"]).generation_metadata_json or {}
            if md.get("portrait_tags"):
                break
            time.sleep(0.1)
        shown = {t["character_id"] for t in md.get("portrait_tags") or []}
        self.assertEqual(shown, {"emily", "artemis", "elena_caldwin", "aria"})
        # the next turn: the ceremony is not asked for again, and the card's secrets stay the narrator's
        t = self.post(f"/stories/{s['id']}/turns", {"content": "I think about the Magic wing."})
        self.wait_reply(s["id"], t["assistant_message_id"])
        system, msgs = CALLS[-1]
        everything = system + "\n".join(x.content for x in msgs)
        self.assertIn("Only you, the narrator, know this card", everything)
        self.assertNotIn("Entrance ceremony", everything)
        self.assertIn("The chill of dawn", everything)  # the opening is in the story so far
        self.assertNotIn("YOUR REPLY FOR THIS OPENING", everything)

    def test_hero_chronicle_openings_are_prewritten(self):
        w = self.world("hero_chronicle")
        for starter in ("the_hero_summoned", "the_hero_and_the_demon_king"):
            s = self.post("/stories", {"title": starter, "world_id": w["id"], "starter_id": starter})
            CALLS.clear()
            r = self.post(f"/stories/{s['id']}/start")
            m = self.wait_reply(s["id"], r["assistant_message_id"])
            self.assertTrue(r.get("prewritten"))
            self.assertFalse(CALLS)
            self.assertTrue(m["content"].startswith("───When consciousness returned"))
            self.assertTrue(m["content"].endswith("\"Whether you take it or not is up to you.\""))
            self.assertNotIn("[Lily:", m["content"])


if __name__ == "__main__":
    unittest.main()
