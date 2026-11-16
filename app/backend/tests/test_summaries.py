"""Automatic memory summaries (v1.8 phase 7.1): written with memory capture or by the catch-up, never twice, tied to
their messages (edits, branches), and sent for the messages that no longer fit the context."""
import time

from support import AppTestCase


def wait_for(pred, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


class SummaryHelpers:
    def play(self, story_id, turns, start=True):
        if start:
            r = self.post(f"/stories/{story_id}/start")
            self.wait_reply(story_id, r["assistant_message_id"])
        for i in range(turns):
            r = self.post(f"/stories/{story_id}/turns", {"content": f"Turn {i}: I walk on and look around the square."})
            self.wait_reply(story_id, r["assistant_message_id"])

    def rows(self, story_id, status="active"):
        from story.models import MemorySummary
        with self.ctx.db.session() as s:
            return [r.to_dict() for r in s.query(MemorySummary).filter_by(story_id=story_id, status=status)
                    .order_by(MemorySummary.start_seq)]

    def path(self, story_id):
        return [m for m in self.get(f"/stories/{story_id}/messages")["messages"]
                if m["kind"] in ("story", "ooc") and m["content"].strip()]

    def assert_no_overlap(self, rows):
        seen = set()
        for r in rows:
            ids = set(r["message_ids_json"])
            self.assertFalse(ids & seen, "a message is summarised twice")
            seen |= ids
        return seen

    def catch_up(self, story_id, **kw):
        from story.services import summaries
        return self.client.portal.call(lambda: summaries.catch_up(self.ctx, story_id, automatic=False, **kw))


class SummariesWithCaptureTest(SummaryHelpers, AppTestCase):
    """Default settings: batch memory capture writes the summary in its own request."""

    def test_capture_writes_summaries_in_the_same_request(self):
        story = self.new_story("Long walk")
        self.play(story["id"], 9)
        from story.models import ExtractionCursor
        self.assertTrue(wait_for(lambda: len(self.rows(story["id"])) >= 2), self.rows(story["id"]))
        rows = self.rows(story["id"])
        self.assertTrue(all(r["source"] == "capture" for r in rows), [r["source"] for r in rows])
        self.assertTrue(all(r["content"].startswith("[Mock summary]") for r in rows))
        covered = self.assert_no_overlap(rows)
        # every message memory capture has read is summarised
        with self.ctx.db.session() as s:
            cur = s.query(ExtractionCursor).filter_by(story_id=story["id"]).one()
            last = cur.last_seq
        read = {m["id"] for m in self.path(story["id"]) if m["seq"] <= last}
        self.assertTrue(read and read <= covered)

    def test_capture_without_summary_is_caught_up(self):
        story = self.new_story("Gap")
        self.play(story["id"], 6)
        self.assertTrue(wait_for(lambda: len(self.rows(story["id"])) >= 1))
        # a model that left the field empty: drop the summaries, the catch-up writes them for what capture has read
        from story.models import MemorySummary
        with self.ctx.db.session() as s:
            s.query(MemorySummary).filter_by(story_id=story["id"]).delete()
        out = self.catch_up(story["id"], max_chunks=5)
        self.assertEqual(out["status"], "succeeded", out)
        rows = self.rows(story["id"])
        self.assertTrue(rows and all(r["source"] == "summary" for r in rows))
        self.assert_no_overlap(rows)


class SummariesWithoutCaptureTest(SummaryHelpers, AppTestCase):
    """Memory capture off: the catch-up summarises by itself, oldest first, waiting for a worthwhile chunk."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client.put("/api/settings", json={"event_capture_mode": "off"})

    def test_catch_up_edit_branch_and_context(self):
        story = self.new_story("Without capture")
        sid = story["id"]
        self.play(sid, 2)  # 6 messages: the newest wait for a full chunk... exactly 6 is enough
        self.assertTrue(wait_for(lambda: len(self.rows(sid)) == 1), self.rows(sid))
        first = self.rows(sid)[0]
        self.assertEqual(first["source"], "summary")
        self.assertEqual(len(first["message_ids_json"]), 6)
        self.play(sid, 1, start=False)  # 2 more: not enough for another request
        time.sleep(1)
        self.assertEqual(len(self.rows(sid)), 1)
        self.play(sid, 12, start=False)
        self.assertTrue(wait_for(lambda: sum(len(r["message_ids_json"]) for r in self.rows(sid)) >= 24), self.rows(sid))
        rows = self.rows(sid)
        self.assert_no_overlap(rows)
        self.assertTrue(all(len(r["message_ids_json"]) <= 10 for r in rows))
        self.assertEqual([r["start_seq"] for r in rows], sorted(r["start_seq"] for r in rows))

        # editing a summarised message: its summary is stale, then written again
        target = self.path(sid)[3]
        r = self.client.patch(f"/api/stories/{sid}/messages/{target['id']}", json={"content": target["content"] + " (edited)"})
        self.assertLess(r.status_code, 400, r.text[:300])
        stale = self.rows(sid, "stale")
        self.assertEqual(len(stale), 1)
        self.assertIn(target["id"], stale[0]["message_ids_json"])
        self.catch_up(sid, max_chunks=3)
        fresh = [r for r in self.rows(sid) if target["id"] in r["message_ids_json"]]
        self.assertEqual(len(fresh), 1)

        # a path without one of its messages (another branch) does not see that summary
        from story.services import summaries
        with self.ctx.db.session() as s:
            all_ids = {m["id"] for m in self.path(sid)}
            seen = summaries.visible(s, sid, all_ids - {target["id"]})
            self.assertFalse(any(target["id"] in r.message_ids_json for r in seen))

        # the context: a small budget leaves old messages out; their summaries are sent instead
        from story.services import context_builder, story_tree
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            st.settings_json = {**(st.settings_json or {}), "context_budget_tokens": 4500}
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            built = context_builder.build(s, st, story_tree.get_branch(s, st))
        sec = next((x for x in built.manifest["sections"] if x["key"] == "scene_summaries"), None)
        self.assertIsNotNone(sec, [x["key"] for x in built.manifest["sections"]])
        self.assertIn("[Mock summary]", built.system)
        first_sent = int(next(x for x in built.manifest["sections"] if x["key"] == "messages")["items"][0]["label"]
                         .split()[0].lstrip("#"))
        with self.ctx.db.session() as s:
            from story.models import MemorySummary
            for item in sec["items"]:
                self.assertLess(s.get(MemorySummary, item["id"]).start_seq, first_sent)
        self.assertGreater(built.manifest["omitted_messages"], 0)
        self.assertFalse([w for w in built.manifest["warnings"] if "have no summary yet" in w], built.manifest["warnings"])

    def test_switched_off(self):
        self.client.put("/api/settings", json={"scene_summaries_enabled": False})
        try:
            story = self.new_story("No memory")
            self.play(story["id"], 4)
            time.sleep(1)
            self.assertEqual(self.rows(story["id"]), [])
        finally:
            self.client.put("/api/settings", json={"scene_summaries_enabled": True})
