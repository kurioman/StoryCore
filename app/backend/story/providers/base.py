"""Provider adapter interface and shared error handling."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import httpx

# Every generation knob the app knows about. Adapters declare the subset they support;
# unsupported knobs are never sent.
ALL_PARAMS = ["temperature", "top_p", "top_k", "max_tokens", "context_size", "repeat_penalty",
              "frequency_penalty", "presence_penalty", "seed"]

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class ModelInfo:
    id: str
    display_name: str = ""
    context_length: Optional[int] = None
    size_bytes: Optional[int] = None
    details: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Plain-language provider failure. ``details`` is technical, secret-free text."""

    def __init__(self, category: str, message: str, details: str = "", status: int | None = None):
        super().__init__(message)
        self.category = category
        self.message = message
        self.details = details[:2000]
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "message": self.message, "details": self.details, "status": self.status}


FRIENDLY = {
    "auth": "The provider rejected the API key. Check the key in Settings → Providers.",
    "stream_error": "The provider stopped partway through the reply. Retry when ready.",
    "credits": "The account is out of credits or over its spending limit. Add credits or raise the key's limit on the provider's site, then retry.",
    "rate_limit": "The provider is rate-limiting requests. Wait a moment, then retry.",
    "not_found": "The provider could not find that model or endpoint. Check the model ID and base URL.",
    "context_overflow": "The request is larger than the model's context window. Lower the context budget or create a recap.",
    "bad_request": "The provider rejected the request. A generation setting may be unsupported by this model.",
    "unavailable": "The provider is temporarily unavailable. Retry in a moment.",
    "timeout": "The provider did not respond in time.",
    "network": "Could not reach the provider. Check the base URL and your network connection.",
    "cancelled": "Generation was cancelled.",
    "invalid_response": "The provider returned a response the app could not understand.",
}


def error_from_status(status: int, body: str, provider_label: str) -> ProviderError:
    low = body.lower()
    if status == 402 or (status == 403 and any(k in low for k in ("credit", "limit exceeded", "key limit"))):
        cat = "credits"
    elif status in (401, 403):
        cat = "auth"
    elif status == 404:
        cat = "not_found"
    elif status == 429:
        cat = "rate_limit"
    elif status in (400, 413, 422) and any(k in low for k in ("context", "too long", "too many tokens", "maximum length", "prompt is too long")):
        cat = "context_overflow"
    elif status in (400, 422):
        cat = "bad_request"
    elif status >= 500 or status == 529:
        cat = "unavailable"
    else:
        cat = "bad_request"
    return ProviderError(cat, f"{provider_label}: {FRIENDLY[cat]}", f"HTTP {status}: {body[:1500]}", status)


def stream_truncated(provider_label: str) -> ProviderError:
    """The provider closed the stream without its end-of-reply event: the reply is incomplete, not complete."""
    return ProviderError("network", f"{provider_label}: the connection closed before the reply finished. The text received so far was kept.",
                         "stream ended without a terminal event")


def error_from_exception(exc: Exception, provider_label: str, hint: str = "") -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError("timeout", f"{provider_label}: {FRIENDLY['timeout']}", type(exc).__name__)
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        msg = f"{provider_label}: {FRIENDLY['network']}"
        if hint:
            msg += " " + hint
        return ProviderError("network", msg, f"{type(exc).__name__}: {exc}")
    return ProviderError("invalid_response", f"{provider_label}: {FRIENDLY['invalid_response']}", f"{type(exc).__name__}: {exc}")


class ProviderAdapter:
    provider_type = "base"
    label = "Provider"
    supported_params: list[str] = []
    is_cloud = False
    supports_model_listing = True
    # complete(..., json_schema=...) constrains JSON output to a schema (otherwise callers rely on json_mode + validation)
    supports_json_schema = False
    connection_hint = ""
    last_usage: dict[str, Any] | None = None  # the provider's own usage figures for the latest request, when it sends them
    last_finish: dict[str, Any] | None = None  # how the latest stream ended, as the provider reported it (v1.6.1)

    def __init__(self, base_url: str | None, api_key: str | None, config: dict[str, Any] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.config = config or {}
        self._transport = transport

    # -- http helpers -------------------------------------------------------
    def client(self, timeout: httpx.Timeout | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout or DEFAULT_TIMEOUT, transport=self._transport)

    def headers(self) -> dict[str, str]:
        return {}

    async def _get_json(self, path: str, timeout: float = 15.0) -> Any:
        try:
            async with self.client(httpx.Timeout(timeout)) as c:
                r = await c.get(self.base_url + path, headers=self.headers())
        except Exception as e:
            raise error_from_exception(e, self.label, self.connection_hint)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)
        try:
            return r.json()
        except ValueError as e:
            raise ProviderError("invalid_response", f"{self.label}: {FRIENDLY['invalid_response']}", r.text[:500]) from e

    def filter_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in (params or {}).items() if k in self.supported_params and v is not None and v != ""}

    # -- interface ----------------------------------------------------------
    async def list_models(self) -> list[ModelInfo]:
        raise ProviderError("bad_request", f"{self.label} does not support model listing; enter a model ID manually.")

    async def test_connection(self, model_id: str | None = None) -> dict[str, Any]:
        """Is the provider reachable? Never runs a model: billable requests belong to ``probe``."""
        models = await self.list_models()
        return {"ok": True, "message": f"Connected. {len(models)} model(s) available.", "model_count": len(models)}

    async def probe(self, model_id: str) -> dict[str, Any]:
        """One tiny real request, only when the player explicitly asks for it (it can be billed)."""
        await self.complete(model_id, "", [ChatMessage("user", "Reply with OK.")], {"max_tokens": 16})
        return {"ok": True, "message": f"{model_id} answered a short test request."}

    def stream_chat(self, model: str, system: str, messages: list[ChatMessage], params: dict[str, Any]) -> AsyncIterator[str]:
        raise NotImplementedError

    def raise_if_cut_off(self, params: dict[str, Any]) -> None:
        """A stream that ended cleanly is not a finished reply. v1.6.1: ``finish_reason`` used to mean only "the stream is
        over", so a reply stopped by the output limit was saved as complete, then analysed and given suggestions."""
        fin, used = self.last_finish or {}, self.last_usage or {}
        reason = fin.get("reason")
        out, limit, thought = used.get("completion_tokens"), (params or {}).get("max_tokens"), used.get("reasoning_tokens")
        if reason is None and out and limit and int(out) >= int(limit):
            reason = "length"  # a server that sends no finish reason: the whole budget was used
        detail = f"finish_reason={reason}, native={fin.get('native')}, output={out}, reasoning={thought}, max_tokens={limit}"
        if reason in ("content_filter", "refusal"):
            raise ProviderError("refusal", f"{self.label}: the provider stopped this reply with its content filter.", detail)
        if reason in ("length", "max_tokens"):
            why = f"The model spent {thought} of its {out} output tokens on hidden reasoning before writing." \
                if thought and out and thought * 2 >= out else "It reached the output limit."
            raise ProviderError("truncated", f"{self.label}: the reply was cut off. {why} Retrying sends a new request"
                                             f"{', which is billed' if self.is_cloud else ''}. If it keeps happening, raise "
                                             "Max output tokens in Settings → Providers & models.", detail)

    async def complete(self, model: str, system: str, messages: list[ChatMessage], params: dict[str, Any],
                       json_mode: bool = False, json_schema: dict[str, Any] | None = None) -> str:
        out = []
        async for chunk in self.stream_chat(model, system, messages, params):
            out.append(chunk)
        return "".join(out)


async def iter_sse(response: httpx.Response) -> AsyncIterator[tuple[str | None, str]]:
    """Yield (event, data) pairs from a text/event-stream response."""
    event: str | None = None
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event, data_lines = None, []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield event, "\n".join(data_lines)


def parse_json(data: str) -> Any:
    try:
        return json.loads(data)
    except ValueError:
        return None


def normalize_alternating(messages: list[ChatMessage], opener: str = "(The story begins.)") -> list[ChatMessage]:
    """Merge consecutive same-role turns and ensure the first turn is from the user."""
    out: list[ChatMessage] = []
    for m in messages:
        if m.role not in ("user", "assistant") or not m.content.strip():
            continue
        if out and out[-1].role == m.role:
            out[-1] = ChatMessage(m.role, out[-1].content + "\n\n" + m.content)
        else:
            out.append(ChatMessage(m.role, m.content))
    if not out or out[0].role != "user":
        out.insert(0, ChatMessage("user", opener))
    return out
