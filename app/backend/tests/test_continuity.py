"""Phase 7.6: checks that cost no tokens — repeated phrasing, a dead character who speaks, the time going back — and
the contradiction with a pinned memory reported by the scene analysis that runs anyway."""
import json
import time

from support import AppTestCase
from story.services import continuity


class ContinuityUnitTest(AppTestCase):
    import_packs = False

    def test_repeated_phrases(self):
        a = "A shiver runs down her spine as the wind howls. She turns to the gate."
        b = "Morning comes. A shiver runs down her spine as the bells ring out over the city."
        c = "The guards laugh. A shiver runs down her spine again, colder this time."
        found = continuity.repeated_phrases([a, b, c])
        self.assertTrue(any("shiver runs down her spine" in p for p in found), found)
        self.assertEqual(len([p for p in found if "shiver" in p]), 1)  # one run, not five shifted copies
        fr = ["Ses yeux s'illuminent d'une lueur nouvelle quand il parle.", "Elle sourit. Ses yeux s'illuminent d'une lueur nouvelle."]
        self.assertTrue(continuity.repeated_phrases(fr))
        self.assertEqual(continuity.repeated_phrases(["One short line.", "Another one entirely."]), [])
        # two replies that open with the same four words
        openings = continuity.repeated_phrases(["Then she smiles softly at the crowd.", "Then she smiles softly, and turns."])
        self.assertEqual(openings, ["then she smiles softly …"])

    def test_time_went_back(self):
        self.assertTrue(continuity.time_went_back("evening", "morning"))
        self.assertTrue(continuity.time_went_back("soir", "matin"))
        self.assertTrue(continuity.time_went_back("18:30", "09:00"))
        self.assertFalse(continuity.time_went_back("morning", "afternoon"))
        self.assertFalse(continuity.time_went_back("après-midi", "soir"))
        self.assertFalse(continuity.time_went_back("night", "02:00"))  # the clock went on past midnight
        self.assertFalse(continuity.time_went_back("", "morning"))
        self.assertEqual(continuity.time_rank("après-midi"), 15 * 60)


class ContinuityStoryTest(AppTestCase):
    def turn(self, sid, text):
        r = self.post(f"/stories/{sid}/turns", {"content": text})
        self.wait_reply(sid, r["assistant_message_id"])
        time.sleep(0.4)
        return r["assistant_message_id"]

    def alerts(self, mid):
        from story.models import Message
        with self.ctx.db.session() as s:
            return (s.get(Message, mid).generation_metadata_json or {}).get("continuity_alerts") or []

    def test_repetition_dead_speaker_and_pinned_contradiction(self):
        story = self.new_story("Continuity")
        sid = story["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        for t in ("I walk to the gate.", "I wait by the well.", "I look at the sky."):
            first = self.turn(sid, t)

        # the mock narrator always says the same thing: the next request asks to vary it
        from story.services import context_builder, story_tree
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            b = story_tree.get_branch(s, st)
            built = context_builder.build(s, st, b)
        rep = next((x for x in built.manifest["sections"] if x["key"] == "repetition"), None)
        self.assertIsNotNone(rep, [x["key"] for x in built.manifest["sections"]])
        self.assertIn("Vary your wording", built.messages[-1].content + built.system)
        self.client.put("/api/settings", json={"anti_repetition": False})
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            keys = [x["key"] for x in context_builder.build(s, st, story_tree.get_branch(s, st)).manifest["sections"]]
        self.client.put("/api/settings", json={"anti_repetition": True})
        self.assertNotIn("repetition", keys)

        # the journal records Arbel's death; later she speaks (portrait tag): a notice under the reply
        from story.models import StoryEvent
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            b = story_tree.get_branch(s, st)
            s.add(StoryEvent(story_id=sid, branch_id=b.id, branch_sequence=story_tree.next_event_sequence(s, b),
                             event_type="death", title="Arbel falls", summary="Arbel died at the gate.",
                             entity_ids_json=["arbel"], verification_status="recorded_unverified",
                             evidence_kind="witnessed", source_message_ids_json=[first], dedupe_key="test-death"))
        mid = self.turn(sid, '[Arbel:1] "You came back," Arbel says.')
        dead = [a for a in self.alerts(mid) if a["kind"] == "dead_speaks"]
        self.assertEqual([a["character_id"] for a in dead], ["arbel"], self.alerts(mid))

        # a pinned memory goes to the scene analysis, which reports a clear contradiction in its warnings
        self.post(f"/stories/{sid}/facts", {"content": "Arbel never left the North.", "pinned": True})
        from story.providers import adapters
        orig, seen = adapters.MockAdapter.complete, {}

        async def fake(self_, model, system, messages, params, json_mode=False, json_schema=None):
            out = await orig(self_, model, system, messages, params, json_mode, json_schema)
            if json_mode and '"suggestions"' in (system or "") and "PINNED MEMORIES" in messages[-1].content:
                seen["prompt"] = messages[-1].content
                d = json.loads(out)
                d["warnings"] = ["contradicts: Arbel is in the South here"]
                return json.dumps(d)
            return out

        adapters.MockAdapter.complete = fake
        try:
            mid = self.turn(sid, "I meet Arbel in the southern market.")
        finally:
            adapters.MockAdapter.complete = orig
        self.assertIn("Arbel never left the North.", seen.get("prompt", ""))
        self.assertEqual([a["text"] for a in self.alerts(mid) if a["kind"] == "contradiction"],
                         ["contradicts: Arbel is in the South here"])
