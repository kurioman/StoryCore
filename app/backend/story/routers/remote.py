"""Phone access (v1.8, phase 6): switched on and off from the PC; ``/pair`` is where a phone gets its badge."""
from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..services.remote import BADGE_TTL, COOKIE, RemoteAccess

router = APIRouter(tags=["remote"])
pair_router = APIRouter()


def _remote(request: Request) -> RemoteAccess:
    return request.app.state.remote


@router.get("/remote/whoami")
def whoami(request: Request) -> dict[str, Any]:
    """Tells the interface whether it runs on a paired phone (PC-only screens are then hidden)."""
    remote = _remote(request)
    if remote.is_network_request(request.scope):
        dev = remote.device_for(request.cookies.get(COOKIE))
        return {"remote": True, "device": dev.name if dev else None}
    return {"remote": False, "device": None}


@router.get("/remote/status")
def status(request: Request) -> dict[str, Any]:
    remote = _remote(request)
    if remote.enabled and remote.code_valid_for() == 0:
        remote.new_code()  # the PC screen always has a usable code to show
    return remote.status()


@router.post("/remote/enable")
async def enable(request: Request) -> dict[str, Any]:
    remote = _remote(request)
    await remote.enable(request.app)
    return remote.status()


@router.post("/remote/disable")
async def disable(request: Request) -> dict[str, Any]:
    remote = _remote(request)
    await remote.disable()
    return remote.status()


@router.post("/remote/new-code")
def new_code(request: Request) -> dict[str, Any]:
    remote = _remote(request)
    if not remote.enabled:
        raise ValueError("Phone access is off.")
    remote.new_code()
    return remote.status()


@router.post("/remote/forget-all")
def forget_all(request: Request) -> dict[str, Any]:
    remote = _remote(request)
    remote.devices.clear()
    return remote.status()


@router.delete("/remote/devices/{device_id}")
def forget(device_id: str, request: Request) -> dict[str, Any]:
    remote = _remote(request)
    remote.forget(device_id)
    return remote.status()


# ---------------------------------------------------------------------------------------------- pairing page
TEXT = {
    "en": {"title": "Connect this phone", "lead": "Type the 6-digit code shown on your computer (StoryCore → Play on a phone).",
           "button": "Connect", "bad": "This code is not valid. Check the code on the computer (it changes after 10 minutes "
           "or after a few wrong tries).", "off": "Phone access is off on the computer."},
    "fr": {"title": "Connecter ce téléphone", "lead": "Tapez le code à 6 chiffres affiché sur votre ordinateur "
           "(StoryCore → Jouer sur téléphone).", "button": "Se connecter", "bad": "Ce code n'est pas valide. Vérifiez le "
           "code sur l'ordinateur (il change après 10 minutes ou après quelques essais ratés).",
           "off": "L'accès depuis un téléphone est désactivé sur l'ordinateur."},
}


def _lang(request: Request) -> dict[str, str]:
    accept = (request.headers.get("accept-language") or "").lower()
    return TEXT["fr"] if accept.startswith("fr") else TEXT["en"]


def _page(t: dict[str, str], error: str | None = None) -> HTMLResponse:
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    body = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>StoryCore</title>
<style>
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0b1224;color:#e6ebf5;
font-family:system-ui,sans-serif}}main{{width:min(360px,90vw);text-align:center}}h1{{font-size:1.4rem;letter-spacing:.04em}}
p{{color:#a8b3c9;line-height:1.5}}input{{width:100%;box-sizing:border-box;font-size:2rem;letter-spacing:.4em;text-align:center;
padding:.5rem;border-radius:.6rem;border:1px solid #33426a;background:#121c36;color:#fff}}
button{{margin-top:1rem;width:100%;padding:.8rem;font-size:1.05rem;border:0;border-radius:.6rem;background:#d4a64a;color:#1a1306;
font-weight:600}}.err{{color:#ff8f8f}}</style></head><body><main><h1>StoryCore</h1><h2>{t['title']}</h2><p>{t['lead']}</p>{err}
<form method="post" action="/pair"><input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6"
pattern="[0-9]{{6}}" required autofocus><button type="submit">{t['button']}</button></form></main></body></html>"""
    return HTMLResponse(body, status_code=200 if not error else 400, headers={"Cache-Control": "no-store"})


def _try_pair(request: Request, code: str | None):
    remote = _remote(request)
    t = _lang(request)
    if not remote.is_network_request(request.scope):
        return RedirectResponse("/", status_code=303)  # on the PC itself there is nothing to pair
    if not code:
        return _page(t)
    token = remote.pair(code, request.headers.get("user-agent", ""))
    if token is None:
        return _page(t, t["bad"] if remote.enabled else t["off"])
    resp = RedirectResponse("/#/library", status_code=303)
    resp.set_cookie(COOKIE, token, max_age=BADGE_TTL, httponly=True, samesite="lax", path="/")
    return resp


@pair_router.get("/pair", include_in_schema=False)
def pair_get(request: Request, code: str | None = None):
    return _try_pair(request, code)


@pair_router.post("/pair", include_in_schema=False)
async def pair_post(request: Request):
    form = await request.form()
    return _try_pair(request, str(form.get("code") or ""))
