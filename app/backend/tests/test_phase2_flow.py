"""Phase 2: a whole turn with a local model that behaves like Rocinante 12B in the test of 19/11/2026 (code fence, the
app's label copied, the player's action told again, then the story and an info block). Simulated server, no network."""
import json
import time

import httpx

import support  # noqa: F401
from support import AppTestCase

REPLY = ("```\n[The player's turn]\nKurio raised a shield of mana in front of him.\n\n"
         "Lilia stepped beside him, sword drawn. [Lilia Valenheart:4] \"Stay behind me.\"\n\n"
         "The cultist hissed and fell back toward the stairs.\n"
         "<info>\nplace: old library tower\npresent: Lilia Valenheart\nLilia Valenheart: trust +1 (he stood his ground)\n"
         "hp: -10\nmood: Lilia Valenheart 4\n</info>")
SEEN: list[dict] = []


def fake_model(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content or b"{}")
    SEEN.append(body)
    if body.get("stream"):
        chunks = [REPLY[i:i + 7] for i in range(0, len(REPLY), 7)]
        sse = "".join("data: " + json.dumps({"choices": [{"delta": {"content": c}, "finish_reason": None}]}) + "\n\n"
                      for c in chunks)
        sse += "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                      "usage": {"prompt_tokens": 1000, "completion_tokens": 120,
                                                "prompt_tokens_details": {"cached_tokens": 800}}}) + "\n\n"
        sse += "data: [DONE]\n\n"
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "rocinante-test"}]})
    return httpx.Response(200, json={"choices": [{"message": {"content": "SUMMARY: Kurio fought.\nCHARACTERS:\n- none\n"
                                                                           "OPENED:\n- none\nRESOLVED:\n- none"},
                                                  "finish_reason": "stop"}]})


class Phase2FlowTest(AppTestCase):
    def test_turn_with_a_rocinante_like_reply(self):
        self.ctx.transport = httpx.MockTransport(fake_model)
        prov = self.post("/providers", {"provider_type": "openai_compat", "display_name": "Fake LM Studio",
                                        "base_url": "http://localhost:1234/v1"})
        pid = (prov.get("provider") or prov)["id"]
        prof = self.post("/model-profiles", {"provider_id": pid, "model_id": "rocinante-test", "context_limit": 16384,
                                             "make_default": True})
        story = self.new_story("Phase 2", world_slug="lumencia_academy")
        sid = story["id"]
        self.client.patch(f"/api/stories/{sid}", json={"settings": {"model_profile_id": (prof.get("profile") or prof)["id"]}})
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        player = "I raise a shield of mana in front of me."
        r = self.post(f"/stories/{sid}/turns", {"content": player})
        m = self.wait_reply(sid, r["assistant_message_id"])
        time.sleep(1.0)
        m = next(x for x in self.get(f"/stories/{sid}/messages")["messages"] if x["id"] == r["assistant_message_id"])
        text = m["content"]
        self.assertNotIn("```", text)
        self.assertNotIn("[The player", text)
        self.assertNotIn("<info>", text)
        self.assertNotIn("mood:", text)
        self.assertTrue(text.startswith("Lilia stepped beside him"), text)  # the echo of the player's action is gone
        lines = m["generation"]["info_table"]["lines"]
        self.assertTrue(any(l["kind"] == "relationship" and l["status"] == "applied" for l in lines), lines)
        from story.models import Story
        from story.services import state_service
        with self.ctx.db.session() as s:
            st = s.get(Story, sid)
            state = state_service.current(s, st.active_branch_id).state_json
        self.assertEqual(next(x for x in state["stats"] if x["label"] == "HP")["value"], 80)  # opening + this turn: -10 each
        self.assertEqual(state["scene"]["location"], "old library tower")
        # what the model received: third-person rules, the <context> block, no "[The player's turn]", no OOC note
        narr = [b for b in SEEN if b.get("stream")][-1]
        sent = json.dumps(narr["messages"], ensure_ascii=False)
        self.assertIn("third person", sent)
        self.assertIn("</context>", sent)
        self.assertNotIn("[The player's turn]", sent)
        self.assertNotIn("(OOC:", sent)
        self.assertIn("<info>", sent)  # the earlier reply carries its info block, so the model keeps writing it
        self.assertNotIn("```", json.dumps(narr["messages"][1:-1], ensure_ascii=False))
