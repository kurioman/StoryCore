"""Play from a phone on the same Wi-Fi (v0.5, phase 6).

StoryCore normally listens on 127.0.0.1 only. When the player switches "Play on a phone" on (on the PC), a second
listener is opened on every network interface (0.0.0.0) on its own port, serving the same app. Everything that
arrives on that listener must carry a device badge (an HttpOnly cookie) obtained by pairing with a one-time code
shown on the PC (as a QR code). Nothing is remembered on disk: closing StoryCore closes the listener and forgets
every badge, so the option is off again at the next start.

A paired phone is a *player*: it can play, read and change ordinary preferences, but the PC-only areas (providers'
keys, backups, imports, logs, folders, phone access itself) are refused on the network listener (see ``blocked``).
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import re
import secrets
import socket
import time
from dataclasses import dataclass, field

import uvicorn

log = logging.getLogger("story.remote")

COOKIE = "sc_device"
CODE_TTL = 600  # seconds a pairing code stays valid
MAX_TRIES = 5  # wrong codes before the current code is thrown away
BADGE_TTL = 12 * 3600  # a badge lasts at most one long evening, and never beyond a restart
IP_HOST = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")

# On the network listener, these API areas are refused (whatever the method)…
BLOCKED_ALWAYS = ("/api/remote/", "/api/system/", "/api/backups", "/api/import/", "/api/notes/import",
                  "/api/local-canon/import", "/api/assets/roots", "/api/assets/rescan-all", "/api/assets/upload",
                  "/api/assets/overrides", "/api/assets/slug-overrides", "/api/lore/import", "/api/ollama/",
                  "/api/lmstudio/", "/api/model-catalog/refresh")
# …and these only refuse changes (reading them is needed to show the current model, for example).
BLOCKED_CHANGES = ("/api/providers", "/api/model-profiles")
# Exceptions: what a phone may still do there.
ALLOWED = ("/api/remote/whoami",)
ALLOWED_CHANGES = re.compile(r"^/api/providers/[^/]+/consent$")  # agreeing to a cloud provider from the phone
REIMPORT = re.compile(r"^/api/worlds/[^/]+/reimport$")


def blocked(method: str, path: str) -> bool:
    """True when a paired phone may not use this API route."""
    if path in ALLOWED:
        return False
    if path.startswith(BLOCKED_ALWAYS) or REIMPORT.match(path):
        return True
    if method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith(BLOCKED_CHANGES):
        return not ALLOWED_CHANGES.match(path)
    return False


def lan_addresses() -> list[str]:
    """This computer's addresses on the local network, the most likely one first (no packet is sent)."""
    found: list[str] = []
    with contextlib.suppress(OSError):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.255.255", 1))  # UDP "connect" only picks the outgoing interface
            found.append(s.getsockname()[0])
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    out = []
    for ip in found:
        if ip not in out and not ip.startswith(("127.", "0.", "169.254.")):
            out.append(ip)
    return out


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise ValueError(f"No free network port found between {start} and {start + 49}.")


class _QuietServer(uvicorn.Server):
    """A second uvicorn server inside the main one's event loop: Ctrl+C stays with the main server."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


@dataclass
class Device:
    id: str
    name: str
    paired_at: float
    last_seen: float
    token_hash: str


@dataclass
class RemoteAccess:
    main_port: int
    port: int | None = None
    enabled: bool = False
    code: str | None = None
    code_expires: float = 0.0
    tries: int = 0
    devices: dict[str, Device] = field(default_factory=dict)
    _server: _QuietServer | None = None
    _task: asyncio.Task | None = None

    # ------------------------------------------------------------------ listener
    async def enable(self, app) -> None:
        if self.enabled:
            return
        port = free_port(self.main_port + 1)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, lifespan="off", log_level="warning",
                                timeout_graceful_shutdown=2)
        server = _QuietServer(config)
        task = asyncio.create_task(server.serve())
        for _ in range(100):  # wait until it really listens (or failed)
            if server.started or task.done():
                break
            await asyncio.sleep(0.05)
        if not server.started:
            server.should_exit = True
            raise ValueError("The network access could not be opened (the port may be blocked).")
        self._server, self._task, self.port, self.enabled = server, task, port, True
        self.new_code()
        log.info("phone access opened on port %s", port)

    async def disable(self) -> None:
        server, task = self._server, self._task
        self._server = self._task = None
        self.enabled = False
        self.code = None
        self.devices.clear()  # every badge becomes useless
        if server is not None:
            server.should_exit = True
        if task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(task, timeout=5)
            log.info("phone access closed")

    def is_network_request(self, scope) -> bool:
        server = scope.get("server")
        return bool(self.enabled and self.port and server and server[1] == self.port)

    # ------------------------------------------------------------------ pairing
    def new_code(self) -> str:
        self.code = f"{secrets.randbelow(1_000_000):06d}"
        self.code_expires = time.time() + CODE_TTL
        self.tries = 0
        return self.code

    def code_valid_for(self) -> int:
        if not self.code:
            return 0
        return max(0, int(self.code_expires - time.time()))

    def pair(self, code: str, user_agent: str) -> str | None:
        """Exchange the code for a badge (returns the badge, or None). The code works once."""
        if not self.enabled or not self.code or time.time() > self.code_expires:
            return None
        if not hmac.compare_digest(str(code).strip(), self.code):
            self.tries += 1
            if self.tries >= MAX_TRIES:
                self.code = None  # too many guesses: the PC must show a new code
            return None
        self.code = None
        token = secrets.token_urlsafe(32)
        now = time.time()
        dev = Device(id=secrets.token_hex(4), name=_device_name(user_agent), paired_at=now, last_seen=now,
                     token_hash=_hash(token))
        self.devices[dev.id] = dev
        self.new_code()  # a fresh code is ready for the next phone
        return token

    def device_for(self, token: str | None) -> Device | None:
        if not token:
            return None
        h = _hash(token)
        now = time.time()
        for dev in list(self.devices.values()):
            if now - dev.paired_at > BADGE_TTL:
                self.devices.pop(dev.id, None)
                continue
            if hmac.compare_digest(dev.token_hash, h):
                dev.last_seen = now
                return dev
        return None

    def forget(self, device_id: str) -> bool:
        return self.devices.pop(device_id, None) is not None

    def status(self) -> dict:
        urls = [f"http://{ip}:{self.port}" for ip in lan_addresses()] if self.enabled else []
        return {"enabled": self.enabled, "port": self.port, "urls": urls,
                "code": self.code if self.enabled else None, "code_valid_for": self.code_valid_for(),
                "devices": [{"id": d.id, "name": d.name, "paired_at": int(d.paired_at), "last_seen": int(d.last_seen)}
                            for d in self.devices.values()]}


def _hash(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def _device_name(ua: str) -> str:
    ua = ua or ""
    for needle, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
                         ("Macintosh", "Mac"), ("Linux", "Linux")):
        if needle in ua:
            browser = next((b for b in ("Firefox", "Edg", "Chrome", "Safari") if b in ua), "")
            browser = {"Edg": "Edge"}.get(browser, browser)
            return f"{name} · {browser}" if browser else name
    return "?"
