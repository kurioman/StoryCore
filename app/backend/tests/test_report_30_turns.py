"""v0.6 test report "30 tours" (19/11/2026): one test (or more) per bug B1-B15 that the engine can check."""
import asyncio
import time
import unittest

import support  # noqa: F401  (puts the backend on sys.path)
from support import AppTestCase

from story.services import extraction, reply_cleanup, speaker_guard, world_state
from story.services.entities import Entity, EntityIndex
from story.services.live_speakers import LiveSpeakers


def _wait(fut, timeout: float = 10.0) -> None:
    end = time.time() + timeout
    while time.time() < end and not fut.done():
        time.sleep(0.05)


class MemoryCaptureTest(AppTestCase):
    """B1: a stopped capture never stays "running"; B2: it resumes at the next reply, one exchange at a time."""

    def _story_with_turns(self, title: str, turns: int = 3) -> tuple[str, str]:
        st = self.new_story(title, world_slug="hero_chronicle")
        sid = st["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        for i in range(turns):
            t = self.post(f"/stories/{sid}/turns", {"content": f"I walk on, step {i}."})
            self.wait_reply(sid, t["assistant_message_id"])
        bid = self.get(f"/stories/{sid}")["active_branch_id"]
        return sid, bid

    def _runs(self, sid: str) -> list[dict]:
        return self.get(f"/stories/{sid}/extract/runs")["runs"]

    def test_cancelled_capture_is_recorded_and_resumes_small(self):
        sid, bid = self._story_with_turns("Capture B1")
        svc = self.ctx.extraction
        original = svc._request
        sizes: list[int] = []

        async def slow(resolved, head, part, extra, budget):
            sizes.append(len(part))
            await asyncio.sleep(60)

        async def quick_failure(resolved, head, part, extra, budget):
            sizes.append(len(part))
            return None, [{"attempt": 1, "ok": False, "category": "parse", "seconds": 0}], part, ("bad json", "parse")

        try:
            svc._request = slow
            fut = self.ctx.spawn(svc.run(sid, bid, "automatic_batch"))
            for _ in range(100):
                if sizes:
                    break
                time.sleep(0.05)
            self.assertTrue(sizes, "the capture never started")
            fut.cancel()  # what runtime.stop_side_requests does when the player sends the next message
            _wait(fut)
            time.sleep(0.2)
            runs = self._runs(sid)
            self.assertFalse([r for r in runs if r["status"] == "running"], "a stopped capture stayed 'running'")
            self.assertEqual(runs[0]["status"], "cancelled")
            self.assertTrue(runs[0]["finished_at"])
            with self.ctx.db.session() as db:
                self.assertTrue(extraction.was_cancelled(db, bid))
                self.assertIsNone(extraction.pause_reason(db, bid, runs[0]["start_seq"]),
                                  "a stopped capture must not pause automatic capture")
            # B2: the next automatic run sends one exchange, not six messages again
            svc._request = quick_failure
            fut = self.ctx.spawn(svc.run(sid, bid, "automatic_batch"))
            _wait(fut)
            self.assertEqual(sizes[-1], extraction.RESUME_CHUNK_MESSAGES)
        finally:
            svc._request = original

    def test_resume_at_next_reply_without_waiting_for_a_batch(self):
        from story.models import ExtractionCursor, MemoryExtractionRun, Message, now_iso
        from story.services import turns as turns_svc
        sid, bid = self._story_with_turns("Capture B2", turns=1)
        time.sleep(1.0)  # let the side requests of the last reply finish
        with self.ctx.db.session() as db:
            msg_id = db.get(Message, self.get(f"/stories/{sid}/messages")["messages"][-1]["id"]).id
            db.add(MemoryExtractionRun(story_id=sid, branch_id=bid, start_seq=0, end_seq=1, capture_method="automatic_batch",
                                       status="cancelled", started_at="9999-01-01T00:00:00+00:00", finished_at=now_iso()))
            cur = db.get(ExtractionCursor, bid)
            if cur is None:
                cur = ExtractionCursor(branch_id=bid, story_id=sid, last_seq=-1)
                db.add(cur)
            cur.assistant_turns_since = 0
            db.get(Message, msg_id).generation_metadata_json = {}
        self.assertEqual(turns_svc.post_process(self.ctx, msg_id), bid,
                         "a stopped capture must come back at the next reply, not after another batch of turns")

    def test_startup_turns_running_captures_into_cancelled(self):
        from story.models import MemoryExtractionRun
        from story.services.runtime import recover_interrupted
        sid, bid = self._story_with_turns("Capture restart", turns=0)
        with self.ctx.db.session() as db:
            db.add(MemoryExtractionRun(story_id=sid, branch_id=bid, start_seq=0, end_seq=1, capture_method="automatic_batch",
                                       status="running"))
        recover_interrupted(self.ctx.db)
        runs = self._runs(sid)
        self.assertEqual(runs[0]["status"], "cancelled")
        with self.ctx.db.session() as db:
            self.assertIsNone(extraction.pause_reason(db, bid, 0))


INDEX = EntityIndex([Entity("sylvia", "Sylvia", "character"), Entity("seria", "Seria", "character"),
                     Entity("lily", "Lily Lumina", "character"), Entity("diana", "Diana", "character"),
                     Entity("grandel", "Grandel", "location")])


def live_beats(text: str, tags=(), present=()) -> list[tuple[str, int]]:
    live = LiveSpeakers(INDEX, protagonist={"Kurio"}, portraits={}, held={}, present=set(present))
    return [(b["character_id"], b["paragraph"]) for b in live.compute(text, list(tags), final=True)]


class ClockAndPlaceTest(unittest.TestCase):
    """B3: the time of day and the day move with the narration; B5: a place only talked about is not a move."""

    def test_sunset_moves_the_clock_forward(self):
        reply = ("As the sun begins to set over Grandel, painting the sky in vivid oranges and pinks, you rise from your "
                 "bed and make your way to the grand dining hall.")
        up = world_state.with_cues(None, reply, {"time": "09:00"})
        self.assertEqual(up["changes"].get("time"), "evening")

    def test_the_next_morning_is_a_new_day(self):
        scene = {"time": "evening", "weekday": "Monday", "day": 1, "month": "March"}
        up = world_state.with_cues(None, "Le lendemain matin, vous vous levez et vous habillez.", scene)
        self.assertEqual(up["days_passed"], 1)
        self.assertEqual(up["changes"]["time"], "morning")
        self.assertEqual((up["changes"]["weekday"], up["changes"]["day"]), ("Tuesday", 2))

    def test_words_in_dialogue_and_going_back_change_nothing(self):
        said = '"Be ready to depart by dawn. Good night, hero."\n\nWith that, the sisters leave the hall.'
        self.assertFalse(world_state.with_cues(None, said, {"time": "evening"}).get("cues"))
        self.assertFalse(world_state.with_cues(None, "The morning sun warms the hall.", {"time": "evening"}).get("cues"))
        # the analysis' own time wins
        own = {"changes": {"time": "20:15"}, "days_passed": 0, "evidence": {"time": "at 20h15"}, "dropped": []}
        self.assertEqual(world_state.with_cues(own, "Night falls.", {"time": "evening"})["changes"]["time"], "20:15")

    def test_a_reworded_quote_still_counts_for_the_time(self):
        reply = "As the sun begins to set over Grandel, the palace grows quiet."
        raw = {"changes": [{"field": "time", "value": "evening", "evidence": "the sun sets over Grandel"}]}
        self.assertEqual(world_state.validate(raw, reply, "", {"time": "09:00"})["changes"].get("time"), "evening")

    def test_a_place_named_in_dialogue_is_not_a_move(self):
        reply = ('Sylvia sets down her glass. "There is a military outpost not far from here, near the border."\n\n'
                 "You listen quietly.")
        raw = {"changes": [{"field": "location", "value": "military outpost",
                            "evidence": "There is a military outpost not far from here"}]}
        out = world_state.validate(raw, reply, "", {"location": "dining hall"})
        self.assertNotIn("location", out["changes"])
        self.assertEqual(out["dropped"][0]["reason"], "only mentioned in dialogue")
        moved = "You ride through the gate and arrive at the military outpost near the border."
        raw = {"changes": [{"field": "location", "value": "military outpost", "evidence": "arrive at the military outpost"}]}
        self.assertEqual(world_state.validate(raw, moved, "", {"location": "road"})["changes"]["location"], "military outpost")


class SpeakersTest(unittest.TestCase):
    """B6: unknown speakers get no portrait; B7: a first name alone is not a lore character outside the scene;
    B8: narration wrapped in quotes is narration; B9: a mostly repeated reply is reported; B10: presence needs the text."""

    def test_maids_do_not_speak_with_the_princess_portrait(self):
        text = ("You hear the door click shut behind Princess Sylvia as she leaves.\n\n"
                "Just then, two maidservants enter, carrying trays of food and drink. They curtsy respectfully.\n\n"
                '"Welcome, honored guest! We are here to prepare your room."\n\n'
                '"Please let us know if there is anything else we can do for you."')
        self.assertEqual(live_beats(text), [])

    def test_an_unknown_named_person_gets_no_portrait(self):
        self.assertEqual(live_beats('Elric nods to Seria, his eyes narrowing.\n\n"Welcome to our outpost, sir."'), [])
        self.assertEqual(live_beats('Seria walks into the tent. "Captain, this is the hero."'), [("seria", 0)])
        # a line right after a paragraph about one lore character still gets her portrait
        self.assertEqual(live_beats('Seria crosses her arms.\n\n"We leave at dawn."'), [("seria", 1)])

    def test_a_first_name_alone_is_not_the_goddess(self):
        tag = [{"name": "Lily", "slot": 2, "offset": 0}]
        self.assertEqual(live_beats('"I\'m Lily, sir! And this is my sister Daisy."', tag), [])
        self.assertEqual(live_beats('"Welcome back, hero."', tag, present={"lily"}), [("lily", 0)])
        self.assertTrue(speaker_guard.name_may_mean(INDEX, "Lily Lumina", "lily", set()))
        self.assertFalse(speaker_guard.name_may_mean(INDEX, "Lily", "lily", set()))

    def test_narration_in_quotes_loses_its_quotes(self):
        reply = ('"The hero\'s toast raises smiles all around the table as glasses clink together. The meal passes '
                 'enjoyably, with lively conversation and laughter filling the air."\n\n'
                 '"Thank you all for joining me tonight," she says graciously.\n\n'
                 '"Your escort will arrive at your room in the morning. Be ready to depart by dawn. Good night, hero."\n\n'
                 '"You dismount and approach an elderly woman among the refugees, asking her what happened to her village."\n\n'
                 '"Our village was attacked by demons. They came in the night, burning everything in their path."')
        text, spans, report = reply_cleanup.clean(reply, [], names={"sylvia"})
        self.assertEqual(report.get("unquoted_narration"), 2)
        paras = text.split("\n\n")
        self.assertTrue(paras[0].startswith("The hero's toast"))
        self.assertTrue(paras[3].startswith("You dismount"))
        for k in (1, 2, 4):  # real lines keep their quotes
            self.assertTrue(paras[k].startswith('"'), paras[k])

    def test_a_mostly_repeated_reply_is_reported(self):
        earlier = ["The goddess snaps her fingers and text appears in the air before you, glowing softly in the white "
                   "space. Lines of golden script describe your new gift in careful detail.\n\nShe waits for your answer, "
                   "her hands folded in front of her, a patient smile on her lips as the light hums around you."]
        reply = earlier[0] + '\n\n"Well?" she asks.'
        text, spans, report = reply_cleanup.clean(reply, earlier)
        self.assertTrue(report.get("mostly_repeated"))
        self.assertTrue(text.strip())

    def test_presence_needs_the_text(self):
        reply = 'The maid curtsies again.\n\n"We are honored to serve you."'
        allowed = speaker_guard.may_appear(INDEX, reply, ["sylvia"])
        result = {"beats": [{"character_id": "diana", "beat": "present", "paragraph": 1},
                            {"character_id": "sylvia", "beat": "present", "paragraph": 0}],
                  "speakers": [], "dialogue": [], "active_speaker_id": None,
                  "cast": {"present": ["diana", "sylvia"], "speaking": [], "left": [], "mentioned": []}}
        self.assertEqual(speaker_guard.filter_result(result, allowed), ["diana"])
        self.assertEqual(result["cast"]["present"], ["sylvia"])
        self.assertIn("seria", speaker_guard.may_appear(INDEX, "Princess Seria listens intently.", []))


class LoreTitleTest(AppTestCase):
    """B4: an invented holder of a locked post ("Emperor Alaric" while the Empress is Diana) is reported."""

    def test_invented_emperor_is_reported(self):
        from story.services import roles
        from story.services.entities import build_index
        wid = self.world("hero_chronicle")["id"]
        with self.ctx.db.session() as db:
            index = build_index(db, wid)
            reg = roles.build_registry(db, wid, index)
            found = roles.detect_conflicts("The Empire is ruled by Emperor Alaric and his two daughters.", reg, index)
            self.assertEqual([c["text"] for c in found], ["Emperor Alaric"])
            self.assertIn("Diana", found[0]["message"])
            fr = roles.detect_conflicts("Il sert l'empereur Alaric depuis vingt ans.", reg, index)
            self.assertEqual([c["text"] for c in fr], ["empereur Alaric"])
            for fine in ("Empress Diana receives you.", "The Dragon Emperor Azra laughs.", "King Arthur of legend.",
                         "Kurio bows.", "Princess Sylvia smiles."):
                self.assertEqual(roles.detect_conflicts(fine, reg, index), [], fine)


if __name__ == "__main__":
    unittest.main()
