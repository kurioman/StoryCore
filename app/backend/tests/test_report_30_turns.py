"""v0.6 test report "30 tours" (19/11/2026): one test (or more) per bug B1-B15 that the engine can check."""
import asyncio
import time
import unittest

import support  # noqa: F401  (puts the backend on sys.path)
from support import AppTestCase

from story.services import extraction


def _wait(fut, timeout: float = 10.0) -> None:
    end = time.time() + timeout
    while time.time() < end and not fut.done():
        time.sleep(0.05)


class MemoryCaptureTest(AppTestCase):
    """B1: a stopped capture never stays "running"; B2: it resumes at the next reply, one exchange at a time."""

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


if __name__ == "__main__":
    unittest.main()
