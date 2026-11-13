"""Provider adapters without network (simulated servers)."""
import asyncio
import json
import unittest

import httpx

import support  # noqa: F401
from story.providers.adapters import OpenAICompatAdapter
from story.providers.base import ChatMessage

SCHEMA = {"type": "object", "properties": {"speakers": {"type": "array"}, "suggestions": {"type": "array"}}}


def lm_studio(log):
    """Behaves like LM Studio: refuses JSON mode, honours a JSON Schema, answers in prose otherwise."""
    def handler(req: httpx.Request):
        rf = json.loads(req.content).get("response_format")
        log.append((rf or {}).get("type"))
        if rf and rf.get("type") == "json_object":
            return httpx.Response(400, json={"error": "'response_format.type' must be 'json_schema' or 'text'"})
        content = '{"speakers": [], "suggestions": []}' if rf else "Sure! Here is the analysis."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})
    return httpx.MockTransport(handler)


class StructuredOutputTest(unittest.TestCase):
    def run_case(self, url, cfg=None):
        log = []
        adapter = OpenAICompatAdapter(url, None, cfg or {}, transport=lm_studio(log))
        out = asyncio.run(adapter.complete("m", "sys", [ChatMessage("user", "x")], {"max_tokens": 50},
                                          json_mode=True, json_schema=SCHEMA))
        return out, log

    def test_local_server_gets_a_json_schema(self):
        out, log = self.run_case("http://localhost:1234/v1")
        self.assertEqual(log, ["json_schema"])
        self.assertTrue(out.startswith("{"))

    def test_refused_json_mode_falls_back_to_the_schema(self):
        out, log = self.run_case("http://192.168.1.20:1234/v1")
        self.assertEqual(log, ["json_object", "json_schema"])
        self.assertTrue(out.startswith("{"))

    def test_forced_json_mode_still_recovers(self):
        out, log = self.run_case("http://localhost:1234/v1", {"structured_output": "json_object"})
        self.assertEqual(log, ["json_object", "json_schema"])
