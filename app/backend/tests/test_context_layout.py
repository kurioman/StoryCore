"""Phase 7.3: the "stable" layout (per-turn sections with the player's message, old messages leaving in steps), short
lore cards for characters who stay, and the prompt-cache markers for Claude."""
from support import AppTestCase
from story.providers import ChatMessage
from story.services import context_builder as cb


class ContextLayoutTest(AppTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # no capture, no summaries: the request only changes because of the story itself
        cls.client.put("/api/settings", json={"event_capture_mode": "off", "scene_summaries_enabled": False})

    def build(self, sid, budget=None):
        """The request as it is sent when the latest reply is written (that reply left out: the player's turn last)."""
        from story.services import story_tree
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            if budget:
                st.settings_json = {**(st.settings_json or {}), "context_budget_tokens": budget}
        with self.ctx.db.session() as s:
            st = story_tree.get_story(s, sid)
            b = story_tree.get_branch(s, st)
            return cb.build(s, st, b, exclude_message_ids={b.head_message_id})

    def turn(self, sid, text):
        r = self.post(f"/stories/{sid}/turns", {"content": text})
        self.wait_reply(sid, r["assistant_message_id"])

    def test_stable_layout_and_steps(self):
        story = self.new_story("Layout")
        sid = story["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        self.turn(sid, "I look at the fountain.")
        built = self.build(sid)
        self.assertEqual(built.manifest["layout"], "stable")
        last = built.messages[-1].content
        self.assertTrue(last.startswith(cb.TURN_OPEN), last[:200])
        self.assertTrue(last.split(cb.TURN_CLOSE + "\n")[1].startswith("I look at the fountain."), last[-300:])
        self.assertIn("## Narration rules", last)
        self.assertNotIn("Narration rules", built.system)
        self.assertNotIn("Protagonist's current state", built.system)
        placement = {x["key"]: x.get("placement") for x in built.manifest["sections"]}
        self.assertEqual(placement["core"], "system")
        self.assertEqual(placement.get("narration_rules"), "turn")
        self.assertIn("## Narration rules", built.instructions)  # side requests still get everything

        # a long game with a small budget: the first message sent changes only in steps, the system prompt never
        starts, systems, sent = [], set(), []
        for i in range(22):
            self.turn(sid, f"Step {i}: I keep walking along the river and watch the boats.")
            b = self.build(sid, budget=5200)
            items = next(x for x in b.manifest["sections"] if x["key"] == "messages")["items"]
            starts.append(items[0]["id"])
            sent.append(len(items))
            systems.add(b.system)
        self.assertGreater(min(sent[-8:]), 6, sent)  # room for more than the minimum (else the minimum slides)
        changes = sum(1 for a, c in zip(starts, starts[1:]) if a != c)
        self.assertGreater(changes, 0)  # old messages do leave
        self.assertLessEqual(changes, len(starts) // 3, sent)  # ...but in steps, not every turn
        self.assertEqual(len(systems), 1)

        # classic: everything in the system prompt, as before
        self.client.put("/api/settings", json={"context_layout": "classic"})
        try:
            b = self.build(sid)
            self.assertIn("Narration rules", b.system)
            self.assertFalse(b.messages[-1].content.startswith(cb.TURN_OPEN))
        finally:
            self.client.put("/api/settings", json={"context_layout": "stable"})
        self.assertEqual(self.client.put("/api/settings", json={"context_layout": "odd"}).status_code, 400)

    def test_short_lore_cards(self):
        story = self.new_story("Cards")
        sid = story["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        self.turn(sid, "I greet Arbel, the knight.")

        def arbel_lore(b):
            lore = next((x for x in b.manifest["sections"] if x["key"] == "lore"), {"items": []})
            return [i for i in lore["items"] if "Arbel" in i.get("label", "")]

        first = arbel_lore(self.build(sid))
        self.assertTrue(first and all(i.get("included", True) for i in first), first)  # she arrives: full entry
        for t in ("Arbel nods at me.", "I ask Arbel about the North.", "I follow Arbel to the gate."):
            self.turn(sid, t)
        later = arbel_lore(self.build(sid))
        self.assertTrue(later and all(i.get("reason") == "short card (already in the scene)" for i in later), later)
        self.client.put("/api/settings", json={"lore_short_cards": False})
        try:
            self.assertTrue(all(i.get("included", True) for i in arbel_lore(self.build(sid))))
        finally:
            self.client.put("/api/settings", json={"lore_short_cards": True})

    def test_claude_cache_markers(self):
        from story.providers.adapters import AnthropicAdapter, OpenAICompatAdapter
        msgs = [ChatMessage("user", "a"), ChatMessage("assistant", "b"), ChatMessage("user", "c")]
        body = AnthropicAdapter("https://api.anthropic.com", "k")._body("claude-x", "SYS", msgs, {"max_tokens": 10}, False)
        self.assertEqual(body["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(body["messages"][1]["content"][0]["cache_control"], {"type": "ephemeral"})
        self.assertIsInstance(body["messages"][2]["content"], str)
        orr = OpenAICompatAdapter("https://openrouter.ai/api/v1", "k")
        body = orr._body("anthropic/claude-sonnet-4.5", "SYS", msgs, {}, False)
        self.assertEqual(body["messages"][0]["content"][0]["cache_control"], {"type": "ephemeral"})
        body = orr._body("z-ai/glm-5", "SYS", msgs, {}, False)
        self.assertEqual(body["messages"][0]["content"], "SYS")  # other models: plain (they cache by themselves)
