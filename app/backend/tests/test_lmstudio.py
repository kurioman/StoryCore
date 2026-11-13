"""LM Studio in one click: detection through a fake LM Studio server, then the connection and profile it creates."""
import httpx

from support import AppTestCase
from story.services import lmstudio

MODELS = {"data": [
    {"id": "qwen2.5-14b-instruct", "type": "llm", "state": "loaded", "max_context_length": 32768,
     "loaded_context_length": 4096, "quantization": "Q4_K_M", "arch": "qwen2"},
    {"id": "mistral-nemo-12b", "type": "llm", "state": "not-loaded", "max_context_length": 131072},
    {"id": "nomic-embed-text", "type": "embeddings", "state": "not-loaded"},
]}


def fake_lmstudio(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v0/models":
        return httpx.Response(200, json=MODELS)
    return httpx.Response(404)


def refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


class LMStudioTest(AppTestCase):
    import_packs = False

    def tearDown(self):
        lmstudio.TRANSPORT = None

    def test_not_running(self):
        lmstudio.TRANSPORT = httpx.MockTransport(refused)
        r = self.get("/lmstudio/detect")
        self.assertFalse(r["reachable"])
        self.assertIn("Developer", r["message"])

    def test_detect_and_setup(self):
        lmstudio.TRANSPORT = httpx.MockTransport(fake_lmstudio)
        found = self.get("/lmstudio/detect")
        self.assertTrue(found["reachable"])
        self.assertEqual([m["id"] for m in found["models"]], ["qwen2.5-14b-instruct", "mistral-nemo-12b"])
        self.assertEqual(found["models"][0]["loaded_context"], 4096)

        done = self.post("/lmstudio/setup", {"model_id": "qwen2.5-14b-instruct"})
        self.assertTrue(done["provider_created"])
        self.assertEqual(done["context_limit"], 4096)
        self.assertEqual(done["max_tokens"], 1024)  # small local window: short replies
        self.assertTrue(any(n["code"] == "small_context" for n in done["notes"]))
        self.assertEqual(self.get("/settings")["default_model_profile_id"], done["profile_id"])

        # the not-loaded model has no loaded length: its maximum is used, roomy window, longer replies
        big = self.post("/lmstudio/setup", {"model_id": "mistral-nemo-12b"})
        self.assertFalse(big["provider_created"])
        self.assertEqual(big["provider_id"], done["provider_id"])
        self.assertEqual(big["context_limit"], 131072)
        self.assertEqual(big["max_tokens"], 3000)
        self.assertTrue(any(n["code"] == "not_loaded" for n in big["notes"]))

        # again: the same profile is reused, not duplicated
        again = self.post("/lmstudio/setup", {"model_id": "qwen2.5-14b-instruct"})
        self.assertEqual(again["profile_id"], done["profile_id"])
        providers = [p for p in self.get("/providers")["providers"] if p["provider_type"] == "openai_compat"]
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0]["base_url"], "http://localhost:1234/v1")

    def test_unknown_model(self):
        lmstudio.TRANSPORT = httpx.MockTransport(fake_lmstudio)
        r = self.client.post("/api/lmstudio/setup", json={"model_id": "nope"})
        self.assertEqual(r.status_code, 404)
