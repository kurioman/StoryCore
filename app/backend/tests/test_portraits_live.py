"""v0.6 portraits: who speaks is found while the reply is written (no tag needed), shown at once, and put back into the
history sent to the model as portrait tags (services/live_speakers.py, services/portrait_tags.py)."""
from __future__ import annotations

import asyncio
import json
import unittest

from support import AppTestCase

from story.providers import adapters
from story.services.entities import Entity, EntityIndex
from story.services.live_speakers import LiveSpeakers

INDEX = EntityIndex([Entity("lily", "Lily Ashford", "character"), Entity("selphina", "Selphina", "character"),
                     Entity("kurio", "Kurio", "character"), Entity("academy", "Lumencia Academy", "location")])


def found(text: str) -> list[tuple[str, int]]:
    live = LiveSpeakers(INDEX, protagonist={"Kurio"}, portraits={}, held={})
    return [(b["character_id"], b["paragraph"]) for b in live.compute(text, [], final=True)]


class DetectionTest(unittest.TestCase):
    def test_french_and_english_attributions(self):
        cases = {
            "« Bonjour », dit Lily.": [("lily", 0)],
            "« Tu viens ? » demande doucement Selphina.": [("selphina", 0)],
            "Lily, rougissante, murmure : « Merci. »": [("lily", 0)],
            "Lily regarde Selphina qui dit : « Assez ! »": [("selphina", 0)],
            "« Viens ! » lance Lily à Selphina.": [("lily", 0)],
            '"Come," Lily said.': [("lily", 0)],
            "Selphina se tourne vers vous.\n\n« Tu viens ? » dit-elle.": [("selphina", 1)],
            "« Lily est partie », soupire Selphina.": [("selphina", 0)],
            "« Salut », dit Lily. « Bonsoir », répond Selphina.": [("lily", 0), ("selphina", 0)],
        }
        for text, want in cases.items():
            self.assertEqual(found(text), want, text)

    def test_the_protagonist_never_gets_a_portrait(self):
        self.assertEqual(found("Lily vous regarde.\n\n« D'accord », répondez-vous."), [])
        self.assertEqual(found("« Allons-y », dit Kurio."), [])
        self.assertEqual(found("Lily marche dans le couloir."), [])
        # live with Rocinante: the narrator wrote the player's line; "you call out" is not in any verb list
        self.assertEqual(found('You make your way over to Lily, a smile on your face. "Lily! You made it too?" you call out.'), [])
        self.assertEqual(found("Vous rejoignez Lily. « Te voilà ! » lancez-vous."), [])
        self.assertEqual(found('You smile at Lily: "Hi."'), [])
        self.assertEqual(found('"Hi," you say. "Oh, hello," Lily answers.'), [("lily", 0)])

    def test_streaming_shows_the_speaker_before_the_end_without_guessing_early(self):
        live = LiveSpeakers(INDEX, protagonist={"Kurio"}, portraits={}, held={})
        text = "Lily entre.\n\n« Salut », dit Selphina en souriant."
        events = []
        for i in range(1, len(text) + 1):
            b = live.feed(text[:i], [])
            if b is not None:
                events.append((i, [(x["character_id"], x["paragraph"]) for x in b]))
        # one event, as soon as "Selphina" is written (never Lily from the previous paragraph first)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][1], [("selphina", 1)])
        self.assertLess(events[0][0], len(text))

    def test_a_tag_wins_for_its_paragraph(self):
        live = LiveSpeakers(INDEX, protagonist={"Kurio"}, portraits={}, held={})
        beats = live.compute("Elle sourit.\n\n« Oui », dit Selphina.", [{"name": "Lily", "slot": 4, "offset": 14}])
        self.assertEqual([(b["character_id"], b["paragraph"], b["slot"], b["source"]) for b in beats],
                         [("lily", 1, 4, "tag")])


REPLY = ("La porte de la bibliothèque grince. Une jeune femme aux cheveux argentés lève les yeux.\n\n"
         "« Oh ! Je ne vous attendais pas si tôt », dit Selphina en souriant.\n\n"
         "Elle referme le livre et se lève.\n\n"
         "« Vous voulez bien m'accompagner ? » demande Selphina.")


class LivePortraitFlowTest(AppTestCase):
    def setUp(self):
        self.orig = adapters.MockAdapter._reply, adapters.MockAdapter.complete, adapters.MockAdapter.stream_chat
        self.seen = []
        seen, orig_stream = self.seen, self.orig[2]

        async def complete(_self, model, system, messages, params, json_mode=False, json_schema=None):
            if json_mode and '"suggestions"' in (system or ""):
                await asyncio.sleep(0.5)
                return json.dumps({"speakers": [{"character": "Selphina", "expression": 6, "evidence": "demande Selphina",
                                                 "line": "Vous voulez bien m'accompagner ?", "confidence": 0.9}],
                                   "active_speaker": "Selphina", "suggestions": []})
            return json.dumps({"events": [], "facts": [], "state_changes": [], "contradictions": [], "character_moods": []})

        async def stream_chat(_self, model, system, messages, params):
            seen.append(messages)
            async for x in orig_stream(_self, model, system, messages, params):
                yield x
        adapters.MockAdapter._reply = lambda _self, messages: REPLY
        adapters.MockAdapter.complete = complete
        adapters.MockAdapter.stream_chat = stream_chat

    def tearDown(self):
        adapters.MockAdapter._reply, adapters.MockAdapter.complete, adapters.MockAdapter.stream_chat = self.orig

    def test_untagged_reply_gets_portraits_and_teaches_the_tags(self):
        sid = self.new_story("portraits")["id"]
        r = self.post(f"/stories/{sid}/turns", {"content": "J'entre."})
        self.wait_reply(sid, r["assistant_message_id"])
        # the detected speaker is stored with the reply and shown before (and after) the scene analysis
        import time
        end = time.time() + 10
        while time.time() < end:
            sc = self.get(f"/stories/{sid}/scene")
            if sc["speakers"] and [b["paragraph"] for b in sc["beats"]] == [1, 3] and sc["speakers"][0]["expression"] == 6:
                break
            time.sleep(0.2)
        self.assertEqual([s["character_id"] for s in sc["speakers"]], ["selphina"])
        self.assertEqual([b["paragraph"] for b in sc["beats"]], [1, 3])  # both lines keep a portrait after the analysis
        r2 = self.post(f"/stories/{sid}/turns", {"content": "Je la suis."})
        self.wait_reply(sid, r2["assistant_message_id"])
        sent = self.seen[-1]
        earlier = [m for m in sent if m.role == "assistant"][-1].content
        self.assertIn("[Selphina:6] « Oh !", earlier)
        self.assertIn("[Selphina:6] « Vous voulez", earlier)
        self.assertIn("e.g. [Selphina:2]", sent[-1].content)  # the short note next to the player's message

    def test_tags_switched_off_leave_the_history_untouched(self):
        self.client.put("/api/settings", json={"portrait_tags_enabled": False})
        try:
            sid = self.new_story("no tags")["id"]
            r = self.post(f"/stories/{sid}/turns", {"content": "J'entre."})
            self.wait_reply(sid, r["assistant_message_id"])
            import time
            time.sleep(1)
            r2 = self.post(f"/stories/{sid}/turns", {"content": "Je la suis."})
            self.wait_reply(sid, r2["assistant_message_id"])
            sent = self.seen[-1]
            self.assertNotIn("[Selphina:", "\n".join(m.content for m in sent))
            self.assertNotIn("(Portraits:", sent[-1].content)
            self.assertTrue(self.get(f"/stories/{sid}/scene")["speakers"])  # the portraits are still shown
        finally:
            self.client.put("/api/settings", json={"portrait_tags_enabled": True})


if __name__ == "__main__":
    unittest.main()
