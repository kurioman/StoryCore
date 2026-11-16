"""Codex (v1.8): discovered characters and places per story, locked entries without spoilers."""
from support import AppTestCase


class CodexTest(AppTestCase):
    def test_codex_follows_the_story(self):
        story = self.new_story("Codex", starter_id="the_hero_summoned")
        start = self.post(f"/stories/{story['id']}/start")
        self.wait_reply(story["id"], start["assistant_message_id"])
        cx = self.get(f"/stories/{story['id']}/codex")
        self.assertTrue(cx["enabled"])
        chars = cx["characters"]
        self.assertEqual(cx["counts"]["characters"]["total"], len(chars))
        lily = next(c for c in chars if c.get("id") == "lily")  # present in the opening scene
        self.assertIn(lily["status"], ("encountered", "known"))
        self.assertTrue(lily["portrait"])
        self.assertIn("summary", lily)
        locked = [c for c in chars if c["status"] == "locked"]
        self.assertTrue(locked)
        self.assertTrue(all(set(c) == {"status"} for c in locked), "a locked card must not reveal a name or an id")
        self.assertFalse(any(p["status"] == "visited" for p in cx["places"]))

        # the scene moves to Avalon: the place becomes visited, with its description
        st = self.get(f"/stories/{story['id']}/state")
        state = st["state"]
        state["scene"]["location"] = "Avalon"
        self.client.put(f"/api/stories/{story['id']}/state", json={"state": state, "summary": "test"})
        places = {p.get("id"): p for p in self.get(f"/stories/{story['id']}/codex")["places"]}
        self.assertEqual(places["avalon"]["status"], "visited")
        self.assertIn("royal palace", places["avalon"]["summary"])
        # nothing secret: narrator-only notes never appear
        everything = str(self.get(f"/stories/{story['id']}/codex"))
        self.assertNotIn("soul-bound", everything)
