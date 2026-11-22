"""Phase 7.5: token figures of every provider in one shape, per-story accounting, the estimate corrected with the real
counts, and no scene analysis for a short reply that has nothing to analyse."""
import time

from support import AppTestCase
from story.providers.adapters import _usage


class UsageShapesTest(AppTestCase):
    import_packs = False

    def test_provider_shapes(self):
        self.assertEqual(_usage({"usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0.01,
                                           "prompt_tokens_details": {"cached_tokens": 800}}}),
                         {"prompt_tokens": 1000, "completion_tokens": 200, "cached_tokens": 800, "cost": 0.01})
        # Anthropic counts the cache apart from input_tokens
        self.assertEqual(_usage({"usage": {"input_tokens": 50, "cache_read_input_tokens": 900,
                                           "cache_creation_input_tokens": 50, "output_tokens": 300}}),
                         {"prompt_tokens": 1000, "completion_tokens": 300, "cached_tokens": 900})
        # OpenAI Responses: input_tokens already includes the cached part
        self.assertEqual(_usage({"usage": {"input_tokens": 1000, "output_tokens": 5,
                                           "input_tokens_details": {"cached_tokens": 600}}})["prompt_tokens"], 1000)
        self.assertEqual(_usage({"prompt_eval_count": 1200, "eval_count": 300, "done": True}),
                         {"prompt_tokens": 1200, "completion_tokens": 300})  # Ollama
        self.assertEqual(_usage({"usage": {"prompt_cache_hit_tokens": 700, "prompt_tokens": 900}})["cached_tokens"], 700)
        self.assertIsNone(_usage({"choices": []}))

    def test_every_paid_request_counts(self):
        # v0.6.2 (Kurio's DeepSeek test: $0.015 shown, $0.017 on OpenRouter): an adapter adds up every request it paid
        # for (a reply asked twice, a repaired analysis), and a side job adds only what it has not added yet
        from story.providers.adapters import MockAdapter
        from story.services import usage as usage_svc
        a = MockAdapter(None, None)
        first = {"prompt_tokens": 10, "cost": 0.004}
        a.last_usage = first
        a.last_usage = first  # a stream that hands back the same figures is not paid twice
        a.last_usage = {"prompt_tokens": 12, "cost": 0.003}
        a.last_usage = None
        self.assertAlmostEqual(a.spent_cost, 0.007)
        story = self.new_story("Cost", world_slug=None)
        usage_svc.record(self.ctx, story["id"], "analysis", a)
        usage_svc.record(self.ctx, story["id"], "analysis", a)  # nothing new since the first record
        side = self.get(f"/stories/{story['id']}/usage")["side"]["analysis"]
        self.assertEqual(side["requests"], 2)
        self.assertAlmostEqual(side["cost"], 0.007)


class StoryUsageTest(AppTestCase):
    def test_accounting_calibration_and_light_analysis(self):
        story = self.new_story("Usage")
        sid = story["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        r = self.post(f"/stories/{sid}/turns", {"content": "I look around."})
        mid = r["assistant_message_id"]
        self.wait_reply(sid, mid)
        time.sleep(0.5)
        u = self.get(f"/stories/{sid}/usage")
        self.assertEqual(u["narration"]["requests"], 2)
        self.assertEqual(u["narration"]["unreported"], 2)  # the mock reports no figures
        self.assertIsNone(u["last"]["input"])
        self.assertGreater(u["last"]["estimated_input"], 300)
        self.assertGreaterEqual(u["side"]["analysis"]["requests"], 1)

        # the provider says the prompt was 25 % bigger than estimated: the story's budget shrinks accordingly
        from story.models import Message
        from story.services import context_builder, story_tree, usage
        with self.ctx.db.session() as s:
            m = s.get(Message, mid)
            est = m.generation_metadata_json["context"]["total_tokens"]
            m.generation_metadata_json = {**m.generation_metadata_json, "usage": {"prompt_tokens": int(est * 1.25)}}
        with self.ctx.db.session() as s:
            self.assertAlmostEqual(usage.calibrate(s, mid), 1.25, places=2)
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            base = context_builder.build(s, st, story_tree.get_branch(s, st)).manifest
        self.assertEqual(base["token_ratio"], 1.25)
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            st.settings_json = {**st.settings_json, "token_ratio": 1.0}
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            plain = context_builder.build(s, st, story_tree.get_branch(s, st)).manifest
        self.assertLess(base["budget_tokens"], plain["budget_tokens"])

        # place and time known, nobody in the scene, a short reply: no analysis request
        from story.models import StoryState, TurnAnalysis
        with self.ctx.db.session() as s:
            row = s.query(StoryState).filter_by(story_id=sid).order_by(StoryState.state_version.desc()).first()
            sc = {**row.state_json.get("scene", {}), "location": "Old bridge", "time": "evening", "present": []}
            row.state_json = {**row.state_json, "scene": sc}
        before = self.get(f"/stories/{sid}/usage")["side"]["analysis"]["requests"]
        r = self.post(f"/stories/{sid}/turns", {"content": "I wait quietly."})
        self.wait_reply(sid, r["assistant_message_id"])
        time.sleep(0.5)
        with self.ctx.db.session() as s:
            ta = s.query(TurnAnalysis).filter_by(message_id=r["assistant_message_id"]).one()
            self.assertEqual(ta.status, "skipped")
            self.assertIn("short reply", ta.error)
        self.assertEqual(self.get(f"/stories/{sid}/usage")["side"]["analysis"]["requests"], before)
