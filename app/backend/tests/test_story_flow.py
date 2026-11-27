"""A whole story with the Mock narrator: create, opening scene, turns, analysis, savepoint, export, delete."""
from support import AppTestCase


class StoryFlowTest(AppTestCase):
    def test_full_story(self):
        world = self.get(f"/worlds/{self.world('hero_chronicle')['id']}")
        self.assertIn("the_hero_summoned", {s["id"] for s in world["data_json"]["starters"]})
        story = self.new_story("Flow", starter_id="the_hero_summoned")
        sid = story["id"]
        self.assertEqual(story["settings_json"].get("starter_id"), "the_hero_summoned")

        # opening scene
        start = self.post(f"/stories/{sid}/start")
        opening = self.wait_reply(sid, start["assistant_message_id"])
        self.assertEqual(opening["status"], "complete")
        self.assertIn("Whether you take it or not is up to you.", opening["content"])  # v0.7.6: the author's opening
        r = self.client.post(f"/api/stories/{sid}/start")
        self.assertEqual(r.status_code, 400, "a story can only start once")

        # two turns
        for text in ("I look around.", "I ask Lily why she chose me."):
            turn = self.post(f"/stories/{sid}/turns", {"content": text})
            reply = self.wait_reply(sid, turn["assistant_message_id"])
            self.assertEqual(reply["status"], "complete")
        msgs = self.get(f"/stories/{sid}/messages")["messages"]
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"] * 3)

        # the reply's scene header (chronology) and the context it was built from
        self.assertTrue(any(m.get("chrono") for m in msgs if m["role"] == "assistant"))
        ctx = self.get(f"/stories/{sid}/messages/{msgs[-1]['id']}/context")
        self.assertTrue(ctx["context"])

        # state and cast panels answer
        self.assertIn("state", self.get(f"/stories/{sid}/state"))
        self.get(f"/stories/{sid}/cast")

        # savepoint, then restore it as a new branch
        sp = self.post(f"/stories/{sid}/savepoints", {"label": "Before the choice"})
        self.assertEqual(len(self.get(f"/stories/{sid}/savepoints")["savepoints"]), 1)
        branch = self.post(f"/stories/{sid}/savepoints/{sp['id']}/restore", {"mode": "new_branch"})
        self.assertTrue(branch["branch_id"])

        # regenerate the last reply keeps one visible reply with alternatives
        last = self.get(f"/stories/{sid}/messages")["messages"][-1]
        regen = self.post(f"/stories/{sid}/messages/{last['id']}/regenerate")
        new_id = regen.get("assistant_message_id") or regen.get("id")
        if new_id:
            self.wait_reply(sid, new_id)

        # export, then delete (a backup zip is kept)
        r = self.client.get(f"/api/stories/{sid}/export")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.content), 200)
        r = self.client.delete(f"/api/stories/{sid}?confirm=true")
        self.assertLess(r.status_code, 400, r.text)
        self.assertNotIn(sid, {s["id"] for s in self.get("/stories")["stories"]})

    def test_free_form_story_without_world(self):
        story = self.new_story("Free", world_slug=None)
        start = self.post(f"/stories/{story['id']}/start")
        self.assertEqual(self.wait_reply(story["id"], start["assistant_message_id"])["status"], "complete")

    def test_invalid_story_requests(self):
        r = self.client.post("/api/stories", json={"title": "x", "world_id": "nope"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/stories", json={"title": "x", "max_tokens": 5})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/stories/does-not-exist").status_code, 404)
