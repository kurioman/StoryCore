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

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client.put("/api/settings", json={"auto_recaps": False})  # the memory capture of v0.6 (phase 2: recaps)

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

        time.sleep(1.0)  # the captures after the replies (mock narrator) may already have processed everything
        with self.ctx.db.session() as db:
            from story.models import ExtractionCursor
            cur = db.get(ExtractionCursor, bid)
            if cur is not None:
                cur.last_seq = -1
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
        self.assertFalse(world_state.with_cues(None, "The afternoon sun warms the hall.", {"time": "evening"}).get("cues"))
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


class InterfaceDataTest(AppTestCase):
    """B15: build folders are never offered as lore packs; B9: the notices under a reply reach the screen."""

    def test_work_and_release_folders_are_not_lore_packs(self):
        import json as _json
        import tempfile
        from pathlib import Path
        from story.services import lore_import
        root = Path(tempfile.mkdtemp(prefix="storycore_b15_"))
        for rel in ("Lorepack/my_pack", "_work/release/stage/Lorepack/my_pack", "_release/x/my_pack", "DEVONLY/old_pack"):
            d = root / rel
            d.mkdir(parents=True)
            (d / "pack.json").write_text(_json.dumps({"format_version": 2, "id": "my_pack", "name": "My pack"}), "utf-8")
        found = [Path(c["path"]).relative_to(root).as_posix() for c in lore_import.discover(root)]
        self.assertEqual(found, ["Lorepack/my_pack"])

    def test_continuity_notices_are_sent_to_the_screen(self):
        st = self.new_story("Notices", world_slug="hero_chronicle")
        sid = st["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        from story.models import Message
        with self.ctx.db.session() as db:
            m = db.get(Message, r["assistant_message_id"])
            m.generation_metadata_json = {**(m.generation_metadata_json or {}), "continuity_alerts": [
                {"kind": "mostly_repeated", "generated": 546, "kept": 55, "nothing_left": False}]}
        msgs = self.get(f"/stories/{sid}/messages")["messages"]
        mine = next(x for x in msgs if x["id"] == r["assistant_message_id"])
        self.assertEqual(mine["generation"]["continuity_alerts"][0]["kind"], "mostly_repeated")


class SecondTestFixesTest(unittest.TestCase):
    """Test 2 (30 turns in English, 19/11/2026): place, presence, name labels, copied notes, the clock."""

    def test_arrivals_in_the_narration_move_the_scene(self):
        cases = {
            "When your vision clears, you find yourself standing in the center of an opulent throne room.": "throne room",
            "She leads you through a set of ornate double doors into a large bedchamber with a four-poster bed.": "bedchamber",
            "He steps aside to allow you to enter the lavish dining hall, where a long table groans.": "dining hall",
            "You make your way down to the palace gardens in search of the princesses.": "palace gardens",
        }
        for text, place in cases.items():
            self.assertEqual(world_state.place_cue(text, {"location": "Pure White Space"})[0], place, text)
        for text in ('"You should enter the castle," she says.', "Seria tells you to enter the castle tomorrow.",
                     "You step into the room.", "You make your way to the grand dining hall."):
            self.assertIsNone(world_state.place_cue(text, {"location": "dining hall"}), text)

    def test_a_reworded_quote_counts_for_the_place(self):
        reply = "When your vision clears, you find yourself standing in the center of an opulent throne room."
        raw = {"changes": [{"field": "location", "value": "throne room", "evidence": "you find yourself in an opulent throne room"}]}
        self.assertEqual(world_state.validate(raw, reply, "", {"location": "white space"})["changes"].get("location"),
                         "throne room")

    def test_sleep_then_dawn_is_a_new_day_and_nonsense_times_are_refused(self):
        scene = {"time": "morning", "weekday": "Tuesday", "day": 2, "month": "March"}
        up = world_state.with_cues(None, "The morning air is crisp as you walk out, in the early dawn light.", scene,
                                   player_turn="I spend the afternoon with the strategists, then go to bed early.")
        self.assertEqual((up["days_passed"], up["changes"]["time"], up["changes"]["weekday"]), (1, "dawn", "Wednesday"))
        evening = world_state.with_cues(None, "The morning sun warms the courtyard.", {"time": "evening"})
        self.assertEqual(evening["days_passed"], 1)
        self.assertIsNone(world_state.clean_value("time", "past"))
        self.assertEqual(world_state.clean_value("time", "late evening"), "late evening")

    def test_name_labels_do_not_carry_an_old_name(self):
        from story.services.turn_analysis import attribute_dialogue
        text = ('Lily nods at your decision.\n\n"And your curse... May it serve as a reminder."\n\nWith that, she waves '
                'her hand.\n\nYou find yourself in a throne room. A woman sits there.\n\n"So, the hero has arrived."\n\n'
                'Her voice echoes through the hall.\n\n"Welcome to the Central Empire, Kai."')
        lines = [{"character_id": "lily", "text": '"And your curse... May it serve as a reminder."'},
                 {"character_id": "diana", "text": '"So, the hero has arrived."'}]
        got = {a["paragraph"]: a["character_id"] for a in attribute_dialogue(text, INDEX, {"lily", "diana"}, None, lines)}
        self.assertEqual(got, {1: "lily", 4: "diana", 6: None})
        text2 = ('"Ah, there he is. Captain Lyndon!"\n\nThe captain strides over.\n\n"Your Highness. What can I do?"\n\n'
                 'He addresses Seria with a respectful nod.\n\n"Who might this be?"')
        got2 = attribute_dialogue(text2, INDEX, {"seria"}, None, [{"character_id": "seria", "text": '"Ah, there he is. Captain Lyndon!"'}])
        self.assertEqual([a["character_id"] for a in got2], ["seria", None, None])
        self.assertEqual(live_beats(text2, present={"seria"}), [])

    def test_a_silent_presence_needs_a_name_in_the_reply(self):
        reply = 'The old woman looks up at you.\n\n"Who are you?"'
        allowed = speaker_guard.may_appear(INDEX, reply, ["lily", "seria"])
        result = {"beats": [{"character_id": "lily", "beat": "present", "paragraph": 0}],
                  "speakers": [], "dialogue": [], "active_speaker_id": None,
                  "cast": {"present": ["lily"], "speaking": [], "left": [], "mentioned": []}}
        self.assertEqual(speaker_guard.filter_result(result, allowed, speaker_guard.named_here(INDEX, reply)), ["lily"])
        self.assertEqual(result["beats"], [])

    def test_copied_notes_are_removed(self):
        reply = ('"This way, if you please."\n(Portraits: right before each line spoken by a named character, write '
                 'their tag [Name:N], e.g. "Hello." N = 1 neutral … 6 shy.)\n\nShe smiles.\n\n'
                 "(OOC: Please continue with Kurio's actions and dialogue.)")
        text, spans, report = reply_cleanup.clean(reply, [])
        self.assertEqual(text, '"This way, if you please."\n\nShe smiles.')
        self.assertEqual(report["instruction_lines"], 2)
        self.assertEqual(reply_cleanup.clean("He smiles (a rare sight).", [])[0], "He smiles (a rare sight).")


class CaptureFirstTest(AppTestCase):
    """B2 again: with memory behind, the capture runs before the scene analysis."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client.put("/api/settings", json={"auto_recaps": False})  # the memory capture of v0.6 (phase 2: recaps)

    def test_capture_goes_first_when_behind(self):
        from story.models import MemoryExtractionRun, now_iso
        from story.services import turn_analysis
        st = self.new_story("Capture first", world_slug="hero_chronicle")
        sid = st["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        time.sleep(1.0)
        bid = self.get(f"/stories/{sid}")["active_branch_id"]
        with self.ctx.db.session() as db:  # the last capture was stopped by the player's message
            db.add(MemoryExtractionRun(story_id=sid, branch_id=bid, start_seq=0, end_seq=1, capture_method="automatic_batch",
                                       status="cancelled", started_at="9999-01-01T00:00:00+00:00", finished_at=now_iso()))
        order: list[str] = []
        svc, orig_run, orig_an = self.ctx.extraction, self.ctx.extraction.run, turn_analysis.analyse

        async def run(*a, **k):
            order.append("capture")
            return {"status": "succeeded"}

        async def analyse(*a, **k):
            order.append("analysis")
            return {"status": "succeeded"}
        try:
            svc.run, turn_analysis.analyse = run, analyse
            with self.ctx.db.session() as db:
                self.assertTrue(extraction.behind(db, bid))
            t = self.post(f"/stories/{sid}/turns", {"content": "I keep walking."})
            self.wait_reply(sid, t["assistant_message_id"])
            for _ in range(60):
                if len(order) >= 2:
                    break
                time.sleep(0.1)
            self.assertEqual(order[:2], ["capture", "analysis"])
        finally:
            svc.run, turn_analysis.analyse = orig_run, orig_an


if __name__ == "__main__":
    unittest.main()
