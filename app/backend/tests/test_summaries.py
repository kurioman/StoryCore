"""Automatic memory summaries (v0.5 phase 7.1): written with memory capture or by the catch-up, never twice, tied to
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


class LayersTest(SummaryHelpers, AppTestCase):
    """Phase 7.2: scenes merge into chapters, chapters into the story so far; notes, threads, edits (capture off)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client.put("/api/settings", json={"event_capture_mode": "off"})

    def all_rows(self, sid):
        from story.models import MemorySummary
        with self.ctx.db.session() as s:
            return [r.to_dict() for r in s.query(MemorySummary).filter_by(story_id=sid)]

    def check_partition(self, sid):
        """What is active never overlaps and covers every summarised message."""
        rows = self.all_rows(sid)
        active = [r for r in rows if r["status"] == "active"]
        seen = set()
        for r in active:
            ids = set(r["message_ids_json"])
            self.assertFalse(ids & seen, f"overlap in {r['level']} #{r['start_seq']}")
            seen |= ids
        scene_ids = {i for r in rows if r["level"] == "scene" and r["status"] in ("active", "superseded")
                     for i in r["message_ids_json"]}
        self.assertEqual(seen, scene_ids)
        return active

    def test_layers_notes_threads_and_edits(self):
        from story.services import summaries
        saved = {k: getattr(summaries, k) for k in ("KEEP_SCENES", "CHAPTER_SCENES", "KEEP_CHAPTERS", "STORY_CHAPTERS",
                                                     "CHUNK_MESSAGES", "MIN_NEW")}
        summaries.KEEP_SCENES, summaries.CHAPTER_SCENES, summaries.KEEP_CHAPTERS, summaries.STORY_CHAPTERS = 3, 3, 2, 2
        summaries.CHUNK_MESSAGES, summaries.MIN_NEW = 4, 4
        try:
            story = self.new_story("Layers")
            sid = story["id"]
            self.play(sid, 30)
            self.catch_up(sid, max_chunks=30, max_merges=30)
            active = self.check_partition(sid)
            levels = [r["level"] for r in sorted(active, key=lambda r: r["start_seq"])]
            self.assertEqual(levels[0], "story", levels)
            self.assertIn("chapter", levels)
            self.assertEqual(levels[-1], "scene")
            self.assertLessEqual(levels.count("scene"), summaries.KEEP_SCENES + summaries.CHAPTER_SCENES - 1)
            self.assertLessEqual(levels.count("chapter"), summaries.KEEP_CHAPTERS + summaries.STORY_CHAPTERS - 1)
            story_row = next(r for r in active if r["level"] == "story")
            self.assertTrue(story_row["content"].startswith("[Mock story so far]"))

            # notes and threads come from every scene, merged or not
            with self.ctx.db.session() as s:
                path_ids = {m["id"] for m in self.path(sid)}
                scenes = summaries.scenes(s, sid, path_ids)
                self.assertTrue(all(r.data_json.get("notes") for r in scenes))
                threads = summaries.open_threads(scenes)
                opened = sum(len(r.data_json.get("threads_opened") or []) for r in scenes)
                resolved = sum(len(r.data_json.get("threads_resolved") or []) for r in scenes)
                self.assertGreater(resolved, 0)
                self.assertEqual(len(threads), opened - resolved)
                mem = summaries.character_memory(scenes, [], "the mock innkeeper smiles")
                self.assertEqual(mem[0][0], "Mock Innkeeper")
                self.assertEqual(len(mem[0][1]), 3)

            # the context: story so far first, open threads, no "no summary" warning
            from story.services import context_builder, story_tree
            with self.ctx.db.session() as s:
                st = story_tree.get_story(s, sid)
                st.settings_json = {**(st.settings_json or {}), "context_budget_tokens": 4500}
            with self.ctx.db.session() as s:
                st = story_tree.get_story(s, sid)
                built = context_builder.build(s, st, story_tree.get_branch(s, st))
            keys = [x["key"] for x in built.manifest["sections"]]
            self.assertIn("scene_summaries", keys)
            self.assertIn("threads", keys)
            self.assertIn("- Story so far (#", built.system)
            self.assertFalse([w for w in built.manifest["warnings"] if "have no summary yet" in w], built.manifest["warnings"])

            # editing a message inside the story so far: the layers covering it are redone, the partition holds
            target = self.path(sid)[2]
            self.assertIn(target["id"], story_row["message_ids_json"])
            r = self.client.patch(f"/api/stories/{sid}/messages/{target['id']}", json={"content": target["content"] + " !"})
            self.assertLess(r.status_code, 400, r.text[:300])
            stale = {x["level"] for x in self.all_rows(sid) if x["status"] == "stale"}
            self.assertEqual(stale, {"scene", "chapter", "story"})
            self.check_partition(sid)
            self.catch_up(sid, max_chunks=10, max_merges=30)
            self.check_partition(sid)
            covered = {i for x in self.all_rows(sid) if x["status"] == "active" for i in x["message_ids_json"]}
            self.assertIn(target["id"], covered)
        finally:
            for k, v in saved.items():
                setattr(summaries, k, v)


class MemoryPanelTest(SummaryHelpers, AppTestCase):
    """Phase 7.4: the memory panel, settling threads, editing, closing a chapter now, the player recap."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client.put("/api/settings", json={"event_capture_mode": "off"})

    def test_panel_chapter_and_player_recap(self):
        story = self.new_story("Panel")
        sid = story["id"]
        self.play(sid, 8)
        self.assertTrue(wait_for(lambda: len(self.rows(sid)) >= 2))
        time.sleep(1)
        self.play(sid, 1, start=False)  # two new messages: they wait for a full chunk
        time.sleep(0.5)
        mem = self.get(f"/stories/{sid}/memory")
        self.assertTrue(mem["enabled"])
        self.assertEqual(mem["summarised_messages"] + mem["pending_messages"], mem["messages"])
        self.assertGreater(mem["pending_messages"], 0)  # the newest wait for a full chunk
        self.assertEqual(mem["characters"][0]["name"], "Mock Innkeeper")
        self.assertTrue(mem["threads"])

        # edit a summary, settle a thread by hand (it leaves the narrator's context too), reopen it
        first = mem["layers"][0]
        r = self.client.patch(f"/api/stories/{sid}/memory/{first['id']}", json={"content": "Edited by the player."})
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.json()["layers"][0]["source"], "edited")
        key = mem["threads"][0]["key"]
        after = self.post(f"/stories/{sid}/memory/threads/close", {"key": key})
        self.assertNotIn(key, [t["key"] for t in after["threads"]])
        self.assertIn(key, [t["key"] for t in after["closed_threads"]])
        after = self.post(f"/stories/{sid}/memory/threads/reopen", {"key": key})
        self.assertIn(key, [t["key"] for t in after["threads"]])

        # /chapter: the newest messages are summarised now and every scene becomes one titled chapter
        out = self.post(f"/stories/{sid}/memory/summarise", {"chapter": True, "title": "Act I"})
        mem = out["memory"]
        self.assertEqual(mem["pending_messages"], 0, mem)
        self.assertEqual([x["level"] for x in mem["layers"]], ["chapter"])
        self.assertEqual(mem["layers"][0]["title"], "Act I")
        self.assertIn("Edited by the player.", [x["content"] for x in self.rows(sid, "superseded")])

        # the player recap: written once, shown again at once until the story moves on
        a = self.post(f"/stories/{sid}/player-recap")
        self.assertFalse(a["cached"])
        self.assertIn("[Mock recap for the player]", a["text"])
        self.assertTrue(self.post(f"/stories/{sid}/player-recap")["cached"])
        self.assertFalse(self.post(f"/stories/{sid}/player-recap", {"refresh": True})["cached"])
        self.play(sid, 1, start=False)
        self.assertFalse(self.post(f"/stories/{sid}/player-recap")["cached"])

        names = {c["name"]: c for c in self.get("/commands")["commands"]}
        self.assertIn("chapitre", names["chapter"]["aliases_json"])
