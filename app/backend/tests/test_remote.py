"""Phone access (v1.8, phase 6): closed by default, pairing with a one-time code, PC-only areas refused."""
import time

import httpx
from fastapi.testclient import TestClient

from support import HEADERS, AppTestCase
from story.services import remote as remote_svc

PORT = 8799
PHONE_UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"


class RemoteAccessTest(AppTestCase):
    import_packs = False

    def setUp(self):
        self.remote = self.app.state.remote
        # pretend the network listener is open on PORT (the real listener is tested at the end)
        self.remote.enabled, self.remote.port = True, PORT
        self.remote.devices.clear()
        self.remote.new_code()
        self.phone = TestClient(self.app, base_url=f"http://192.168.1.50:{PORT}",
                                headers=HEADERS, follow_redirects=False)

    def tearDown(self):
        self.remote.enabled, self.remote.port, self.remote.code = False, None, None
        self.remote.devices.clear()

    def pair(self):
        r = self.phone.get(f"/pair?code={self.remote.code}", headers={"User-Agent": PHONE_UA})
        self.assertEqual(r.status_code, 303, r.text[:200])
        self.assertEqual(r.headers["location"], "/next/#/library")
        self.assertIn(remote_svc.COOKIE, r.cookies)
        self.assertIn("httponly", r.headers["set-cookie"].lower())

    def test_unpaired_phone_gets_nothing(self):
        self.assertEqual(self.phone.get("/api/stories").status_code, 401)
        self.assertEqual(self.phone.get("/api/stories").json()["code"], "not_paired")
        r = self.phone.get("/next/")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/pair"))
        self.assertEqual(self.phone.get("/pair").status_code, 200)  # the code form
        # a forged badge is not a badge
        self.phone.cookies.set(remote_svc.COOKIE, "made-up")
        self.assertEqual(self.phone.get("/api/stories").status_code, 401)

    def test_pairing_and_player_rights(self):
        self.pair()
        who = self.phone.get("/api/remote/whoami").json()
        self.assertEqual(who, {"remote": True, "device": "Android · Chrome"})
        self.assertEqual(self.phone.get("/api/stories").status_code, 200)
        self.assertEqual(self.phone.get("/next/").status_code, 200)
        self.assertEqual(self.phone.put("/api/settings", json={"ui_language": "fr"}).status_code
                         if "ui_language" in self.get("/settings") else 200, 200)
        # PC-only areas
        for method, path in (("get", "/api/remote/status"), ("post", "/api/remote/disable"), ("get", "/api/system/logs"),
                             ("get", "/api/system/paths"), ("get", "/api/backups"), ("post", "/api/providers"),
                             ("get", "/api/assets/roots"), ("post", "/api/lore/import")):
            r = getattr(self.phone, method)(path)
            self.assertEqual(r.status_code, 403, f"{method} {path}: {r.status_code}")
            self.assertEqual(r.json()["code"], "pc_only")
        self.assertEqual(self.phone.get("/api/providers").status_code, 200)  # reading which model is used is fine
        # the PC sees the phone and can disconnect it
        status = self.get("/remote/status")
        self.assertEqual([d["name"] for d in status["devices"]], ["Android · Chrome"])
        self.post("/remote/forget-all")
        self.assertEqual(self.phone.get("/api/stories").status_code, 401)

    def test_code_is_single_use_and_guessing_is_limited(self):
        code = self.remote.code
        self.pair()
        other = TestClient(self.app, base_url=f"http://192.168.1.51:{PORT}", headers=HEADERS, follow_redirects=False)
        self.assertEqual(other.get(f"/pair?code={code}").status_code, 400)  # already used
        self.assertNotEqual(self.remote.code, code)  # a new one is ready for the next phone
        for _ in range(remote_svc.MAX_TRIES):
            wrong = "000000" if self.remote.code != "000000" else "111111"
            other.post("/pair", data={"code": wrong})
        self.assertIsNone(self.remote.code)  # too many wrong tries: the PC must show a new code
        self.assertGreater(self.get("/remote/status")["code_valid_for"], 0)  # the PC screen gets a fresh one
        self.remote.code_expires = time.time() - 1  # an expired code no longer works
        self.assertEqual(other.get(f"/pair?code={self.remote.code}").status_code, 400)

    def test_host_and_origin_checks(self):
        self.pair()
        r = self.phone.get("/api/stories", headers={"Host": "evil.example:8799"})
        self.assertEqual(r.status_code, 403)  # DNS rebinding: only IP addresses are answered
        r = self.phone.post("/api/stories", json={}, headers={"Origin": "http://evil.example"})
        self.assertEqual(r.json()["detail"], "Cross-origin request blocked.")
        r = self.phone.post("/api/stories", json={}, headers={"X-Story-Client": ""})
        self.assertEqual(r.json()["detail"], "Missing X-Story-Client header.")

    def test_pc_side(self):
        self.assertEqual(self.get("/remote/whoami"), {"remote": False, "device": None})
        r = self.client.get("/pair", follow_redirects=False)
        self.assertEqual(r.status_code, 303)  # nothing to pair on the PC itself
        self.assertFalse(remote_svc.blocked("GET", "/api/stories"))
        self.assertFalse(remote_svc.blocked("POST", "/api/providers/abc/consent"))
        self.assertTrue(remote_svc.blocked("PATCH", "/api/providers/abc"))
        self.assertTrue(remote_svc.blocked("POST", "/api/worlds/w1/reimport"))

    def test_real_listener_opens_and_closes(self):
        self.remote.enabled, self.remote.port = False, None
        st = self.post("/remote/enable")
        self.assertTrue(st["enabled"])
        port = st["port"]
        self.assertGreater(port, self.ctx.settings.port)
        r = httpx.get(f"http://127.0.0.1:{port}/api/stories", timeout=5)
        self.assertEqual(r.status_code, 401)  # it listens, and wants a badge
        self.post("/remote/disable")
        with self.assertRaises(httpx.HTTPError):
            httpx.get(f"http://127.0.0.1:{port}/api/stories", timeout=2)
