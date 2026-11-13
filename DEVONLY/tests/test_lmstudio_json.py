"""Simulates LM Studio: refuses response_format json_object (400), honours json_schema, answers in prose otherwise."""
import asyncio, json, sys
import httpx
sys.path.insert(0, sys.argv[1])
from story.providers.adapters import OpenAICompatAdapter
from story.providers.base import ChatMessage

def make(log):
    def handler(req: httpx.Request):
        body = json.loads(req.content); rf = body.get("response_format"); log.append((rf or {}).get("type"))
        if rf and rf.get("type") == "json_object":
            return httpx.Response(400, json={"error": "'response_format.type' must be 'json_schema' or 'text'"})
        content = '{"speakers": [], "suggestions": []}' if rf else 'Sure! Here is the analysis you asked for.'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})
    return httpx.MockTransport(handler)

schema = {"type": "object", "properties": {"speakers": {"type": "array"}, "suggestions": {"type": "array"}}}
async def run(url, cfg=None):
    log = []
    a = OpenAICompatAdapter(url, None, cfg or {}, transport=make(log))
    out = await a.complete("m", "sys", [ChatMessage("user", "x")], {"max_tokens": 50}, json_mode=True, json_schema=schema)
    return out, log
ok = True
for url, cfg, want in [("http://localhost:1234/v1", {}, ["json_schema"]),
                       ("http://192.168.1.20:1234/v1", {}, ["json_object", "json_schema"]),
                       ("http://localhost:1234/v1", {"structured_output": "json_object"}, ["json_object", "json_schema"])]:
    out, log = asyncio.run(run(url, cfg))
    good = log == want and out.startswith("{")
    ok &= good
    print("OK " if good else "FAIL", url, cfg, log, out[:40])
sys.exit(0 if ok else 1)
