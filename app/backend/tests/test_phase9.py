"""Phase 9 (v0.6): no replayed scenes, replies of a sane length, a context budget that follows the model."""
import asyncio
import unittest

import support  # noqa: F401  (puts the backend on sys.path)
from support import AppTestCase

from story.services import reply_cleanup
from story.services.runtime import length_cap, story_params

PREV = ("The noble student looms over you. \"So, gutter trash,\" he sneers, \"you think you can just waltz in here?\"\n\n"
        "His companions laugh mockingly behind him, their gazes scornful and dismissive. They clearly expect you to cower "
        "before his insults.")


class CleanupTest(unittest.TestCase):
    def test_copied_paragraph_and_menu_are_removed(self):
        reply = ("Professor Caldwin steps between you both, her voice cutting through the noise of the crowded hall.\n\n"
                 "His companions laugh mockingly behind him, their gazes scornful and dismissive. They clearly expect you "
                 "to cower before his insults.\n\n\"Enough,\" she says. \"Knight candidates, follow me to the training "
                 "grounds.\"\n\nWhat would you like to do next?")
        text, spans, report = reply_cleanup.clean(reply, [PREV])
        self.assertNotIn("companions laugh", text)
        self.assertNotIn("What would you like", text)
        self.assertTrue(text.startswith("Professor Caldwin") and text.endswith("grounds.\""), text)
        self.assertEqual(report["repeated_paragraphs"], 1)
        i = reply.index("\"Enough")
        self.assertEqual(text[reply_cleanup.move_offset(i, spans):][:7], "\"Enough")
        self.assertIsNone(reply_cleanup.move_offset(reply.index("His companions"), spans))

    def test_a_paragraph_said_twice_in_one_reply(self):
        para = "The bells of the academy ring out across the courtyard as the students gather near the old fountain."
        text, _spans, report = reply_cleanup.clean(f"{para}\n\nA girl waves at you.\n\n{para}", [])
        self.assertEqual(text.count("bells of the academy"), 1)
        self.assertEqual(report["repeated_paragraphs"], 1)

    def test_nothing_new_keeps_the_reply(self):
        self.assertEqual(reply_cleanup.clean(PREV, [PREV])[0], PREV)  # never an empty reply
        fresh = "A new scene: rain on the windows of the library, and a voice behind you."
        self.assertEqual(reply_cleanup.clean(fresh, [PREV]), (fresh, [], {}))

    def test_a_reply_that_writes_the_next_turn_is_cut(self):
        # seen live: a GGUF without chat template -> the model wrote "Human:" and copied the app's per-turn context
        text, spans, report = reply_cleanup.clean("Artemis nods. \"Follow me.\"\nHuman: [Story context for this turn: "
                                                  "written by the app]\n## Scene", [])
        self.assertEqual(text, "Artemis nods. \"Follow me.\"")
        self.assertTrue(report["leaked_turn_cut"])

    def test_reply_cut_by_the_ceiling_ends_on_a_full_sentence(self):
        text, _s, report = reply_cleanup.clean("She draws her sword. The duel begins at once, and the crowd falls "
                                               "silent. He lunges toward her with a", [], cut_by_length=True)
        self.assertTrue(text.endswith("silent."), text)
        self.assertTrue(report["trimmed_unfinished_sentence"])


class ParamsTest(unittest.TestCase):
    def test_length_cap_and_local_repetition_penalty(self):
        class S:
            settings_json = {"output_length": "medium (3–4 paragraphs)", "max_tokens": 8000, "preset_id": "balanced"}
        self.assertEqual(length_cap("short (1–2 paragraphs)"), 380)
        self.assertIsNone(length_cap(""))
        local = story_params({"max_tokens": 1024}, S(), hosted=False, context_limit=32768)
        self.assertEqual(local["max_tokens"], 650)
        self.assertEqual(local["repeat_penalty"], 1.08)
        hosted = story_params({}, S(), hosted=True, context_limit=None)
        self.assertNotIn("repeat_penalty", hosted)

    def test_lm_studio_gets_repeat_penalty_by_its_own_name(self):
        from story.providers.adapters import OpenAICompatAdapter
        local = OpenAICompatAdapter("http://localhost:1234/v1", None)
        body = local._body("m", "sys", [], {"repeat_penalty": 1.08, "max_tokens": 10}, False)
        self.assertEqual(body.get("repeat_penalty"), 1.08)
        self.assertIn("<|im_end|>", body["stop"])  # local servers stop at the end markers of a turn
        cloud = OpenAICompatAdapter("https://openrouter.ai/api/v1", "k")
        self.assertNotIn("stop", cloud._body("m", "sys", [], {}, False))
        self.assertEqual(cloud._body("m", "sys", [], {"repeat_penalty": 1.08}, False).get("repetition_penalty"), 1.08)


class BudgetTest(AppTestCase):
    def test_budget_follows_the_model_window(self):
        from story.models import Story
        from story.services import context_builder, story_tree
        st = self.new_story("Budget", world_slug="hero_chronicle")
        with self.ctx.db.session() as db:
            s = db.get(Story, st["id"])
            b = story_tree.get_branch(db, s)
            big = context_builder.build(db, s, b, context_limit=16384, params={"max_tokens": 650}).manifest
            small = context_builder.build(db, s, b, context_limit=None, params={"max_tokens": 650}).manifest
        self.assertGreater(big["budget_tokens"], 12000)
        self.assertLessEqual(small["budget_tokens"], 10000)

    def test_narration_first_stops_side_requests(self):
        st = self.new_story("Priority", world_slug="hero_chronicle")
        sid = st["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        gens, ctx = self.ctx.generations, self.ctx

        async def slow_side_request():
            await asyncio.sleep(60)

        fut = ctx.spawn(slow_side_request())  # stands for a scene analysis still running on the local server
        gens.side_tasks.setdefault(sid, set()).add(fut)
        turn = self.post(f"/stories/{sid}/turns", {"content": "I look around."})
        self.wait_reply(sid, turn["assistant_message_id"])
        import time
        for _ in range(50):
            if fut.done():
                break
            time.sleep(0.05)
        self.assertTrue(fut.cancelled(), "the side request was not stopped when the player sent a message")

    def test_continue_never_repeats(self):
        cmds = self.get("/commands")
        items = cmds.get("commands", cmds) if isinstance(cmds, dict) else cmds
        cont = next(c for c in items if c["name"] == "continue")
        self.assertIn("Never repeat", cont["template"])


if __name__ == "__main__":
    unittest.main()
