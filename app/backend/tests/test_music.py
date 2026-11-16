"""Music library (v1.8): add / tag / delete tracks, hidden [Music:tag] in replies, what a story plays."""
from support import AppTestCase

FAKE_MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 2000


class MusicTest(AppTestCase):
    def test_tags_vocabulary(self):
        r = self.get("/music/tags")
        ids = {t["id"] for t in r["tags"]}
        self.assertGreaterEqual(len(ids), 50)
        for t in ("action", "final_battle", "romance", "funny", "forest", "city", "inn", "tavern", "cave", "scary"):
            self.assertIn(t, ids)
        self.assertTrue(all(t["label"]["fr"] for t in r["tags"]))

    def test_tag_filter_removes_music_tags(self):
        from story.services.portrait_tags import TagFilter
        f = TagFilter()
        out = f.feed("[Mus") + f.feed("ic:Combat]\nThe blade [Selphina:4] \"Back!\"") + f.flush()
        self.assertNotIn("Music", out)
        self.assertTrue(out.startswith("The blade"))
        self.assertEqual(f.music[0]["tag"], "Combat")
        self.assertEqual(f.tags[0]["name"], "Selphina")

    def test_library_and_story_music(self):
        def upload(name):
            r = self.client.post("/api/music/tracks", files=[("files", (name, FAKE_MP3, "audio/mpeg"))])
            self.assertEqual(r.status_code, 200, r.text[:300])
            return r.json()["added"][0]
        fight, inn = upload("Steel Rain.mp3"), upload("Warm Hearth.mp3")
        bad = self.client.post("/api/music/tracks", files=[("files", ("notes.txt", b"hello", "text/plain"))])
        self.assertGreaterEqual(bad.status_code, 400)
        self.client.patch(f"/api/music/tracks/{fight['id']}", json={"tags": ["Combat", "action"]})
        self.client.patch(f"/api/music/tracks/{inn['id']}", json={"tags": ["tavern"], "title": "Warm hearth"})
        tracks = {t["id"]: t for t in self.get("/music/tracks")["tracks"]}
        self.assertEqual(tracks[fight["id"]]["tags"], ["combat", "action"])
        self.assertEqual(tracks[inn["id"]]["title"], "Warm hearth")
        r = self.client.get(f"/api/music/tracks/{inn['id']}/file")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, FAKE_MP3)

        story = self.new_story("Music", starter_id="the_hero_summoned")
        start = self.post(f"/stories/{story['id']}/start")
        self.wait_reply(story["id"], start["assistant_message_id"])
        now = self.get(f"/stories/{story['id']}/music")
        self.assertTrue(now["enabled"] and now["track"])  # no tag yet: still some music

        # the scene moves to a tavern: the tavern track
        state = self.get(f"/stories/{story['id']}/state")["state"]
        state["scene"]["location"] = "The Rusty Tavern"
        self.client.put(f"/api/stories/{story['id']}/state", json={"state": state, "summary": "test"})
        now = self.get(f"/stories/{story['id']}/music")
        self.assertEqual((now["tag"], now["source"], now["track"]["id"]), ("tavern", "location", inn["id"]))

        # the narrator wrote [Music:combat] in the latest reply: the combat track wins
        from story.models import Message
        with self.ctx.db.session() as s:
            m = s.get(Message, start["assistant_message_id"])
            m.generation_metadata_json = {**(m.generation_metadata_json or {}), "music_tags": [{"tag": "Combat", "offset": 0}]}
        now = self.get(f"/stories/{story['id']}/music")
        self.assertEqual((now["tag"], now["source"], now["track"]["id"]), ("combat", "narrator", fight["id"]))

        self.client.delete(f"/api/music/tracks/{inn['id']}")
        self.assertNotIn(inn["id"], {t["id"] for t in self.get("/music/tracks")["tracks"]})
        self.assertFalse((self.ctx.settings.music_dir / inn["file"]).exists())
