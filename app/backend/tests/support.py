"""Shared test helpers: a StoryCore app on a throw-away data folder, driven through its HTTP API.

The app runs in-process (FastAPI TestClient), with the built-in Mock narrator: no network, no model, no key. The real
lore packs from <project>/Lorepack are imported (read-only), so the tests also cover the packs that ship.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from story.config import Settings  # noqa: E402
from story.main import create_app  # noqa: E402

HEADERS = {"X-Story-Client": "1"}


class AppTestCase(unittest.TestCase):
    """One app per test class (starting it imports both lore packs, about a second)."""

    import_packs = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="storycore_test_"))
        # tests never touch the project's Music folder
        settings = Settings(data_dir=cls.tmp / "data", secrets_backend="memory", music_dir_override=cls.tmp / "music")
        cls.app = create_app(settings, testing=True)
        cls.client = TestClient(cls.app, headers=HEADERS)
        cls.client.__enter__()
        ctx = cls.app.state.ctx
        cls.ctx = ctx
        with ctx.db.session() as s:  # the mock narrator types instantly in tests
            from story.models import Provider
            for p in s.query(Provider).filter(Provider.provider_type == "mock"):
                p.nonsecret_config_json = {**(p.nonsecret_config_json or {}), "delay": 0}
        if cls.import_packs:
            from story.bundled import sync_lore_packs
            sync_lore_packs(ctx)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- API helpers
    def get(self, path: str, **kw):
        r = self.client.get("/api" + path, **kw)
        self.assertLess(r.status_code, 400, f"GET {path}: {r.status_code} {r.text[:300]}")
        return r.json()

    def post(self, path: str, json=None, expect_ok: bool = True):
        r = self.client.post("/api" + path, json=json if json is not None else {})
        if expect_ok:
            self.assertLess(r.status_code, 400, f"POST {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.content else None

    def world(self, slug: str) -> dict:
        worlds = self.get("/worlds")["worlds"]
        found = [w for w in worlds if w["slug"] == slug]
        self.assertTrue(found, f"world {slug} not imported; have {[w['slug'] for w in worlds]}")
        return found[0]

    def new_story(self, title: str = "Test story", world_slug: str | None = "hero_chronicle", **extra) -> dict:
        body = {"title": title, **extra}
        if world_slug:
            body["world_id"] = self.world(world_slug)["id"]
        return self.post("/stories", body)

    def wait_reply(self, story_id: str, message_id: str, timeout: float = 20) -> dict:
        """Wait until the assistant message is finished (and its scene analysis has run)."""
        end = time.time() + timeout
        while time.time() < end:
            msgs = self.get(f"/stories/{story_id}/messages")["messages"]
            m = next((x for x in msgs if x["id"] == message_id), None)
            if m and m["status"] not in ("streaming", "pending"):
                return m
            time.sleep(0.1)
        self.fail(f"reply {message_id} did not finish in {timeout}s")
