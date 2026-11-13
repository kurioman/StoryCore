"""Concrete provider adapters: mock, Ollama, Anthropic, OpenAI (Responses), OpenAI-compatible (Chat Completions)."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator

import httpx

from .structured import strict_schema, structured_error
from .base import (FRIENDLY, ChatMessage, ModelInfo, ProviderAdapter, ProviderError, error_from_exception,
                   error_from_status, iter_sse, normalize_alternating, parse_json, stream_truncated)


# =========================================================================== mock
class MockAdapter(ProviderAdapter):
    """Offline demo provider. Output is clearly labelled and deterministic; it never pretends to be a real model."""

    provider_type = "mock"
    label = "Mock provider"
    supported_params = ["max_tokens"]

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("mock-narrator", "Mock narrator (offline demo)", context_length=8192)]

    async def test_connection(self, model_id: str | None = None) -> dict[str, Any]:
        return {"ok": True, "message": "Mock provider is built in and always available (offline demo output).", "model_count": 1}

    def _reply(self, messages: list[ChatMessage]) -> str:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        snippet = re.sub(r"\s+", " ", last).strip()[:160]
        return (
            "*[Mock provider — offline demo text, not a real model]*\n\n"
            f"The scene responds to your action: “{snippet}”. Lantern light flickers across the stone corridor, "
            "and somewhere above, a bell marks the hour. A passer-by glances your way, curious but silent.\n\n"
            "What do you do next?"
        )

    async def stream_chat(self, model, system, messages, params) -> AsyncIterator[str]:
        delay = float(self.config.get("delay", 0.03))
        text = self._reply(messages)
        for tok in re.findall(r"\S+\s*", text):
            if delay:
                await asyncio.sleep(delay)
            yield tok

    async def complete(self, model, system, messages, params, json_mode: bool = False,
                       json_schema: dict[str, Any] | None = None) -> str:
        if json_mode and '"suggestions"' in (system or ""):
            # Explicitly labelled demo turn analysis (no speakers: the mock cannot read the story)
            return json.dumps({"speakers": [], "active_speaker": None, "discoveries": [], "suggestions": [
                {"text": "*I look around carefully.* [Mock demo draft]", "approach": "Cautious", "kind": "observation"},
                {"text": '"Excuse me, could I ask you something?" [Mock demo draft]', "approach": "Curious", "kind": "dialogue"},
                {"text": "*I step back and give myself a moment.* [Mock demo draft]", "approach": "Reserved", "kind": "action"}]})
        if json_mode:
            # A schema-valid, explicitly labelled mock extraction so the pipeline can be exercised offline.
            ids = re.findall(r"\[msg:([0-9a-f\-]{36})\]", messages[-1].content if messages else "")
            return json.dumps({
                "events": [{
                    "title": "[Mock] Exchange recorded",
                    "summary": "Mock extraction placeholder — configure a real extraction model for meaningful events.",
                    "event_type": "other", "importance": 1, "confidence": 0.1, "evidence_kind": "witnessed",
                    "source_message_ids": ids[-1:], "entities": [],
                }] if ids else [],
                "facts": [], "state_changes": [], "contradictions": [], "character_moods": [],
            })
        return "[Mock recap] The mock provider cannot summarise real content. Configure a real model to generate recaps."


# =========================================================================== ollama
class OllamaAdapter(ProviderAdapter):
    provider_type = "ollama"
    label = "Ollama"
    supports_json_schema = True  # /api/chat "format" accepts a JSON schema (structured outputs)
    # "think": per-profile switch for thinking-capable models (true/false); unset = off for story replies (v1.6.4), because hidden
    # reasoning shares the output limit with the story
    supported_params = ["temperature", "top_p", "top_k", "max_tokens", "context_size", "repeat_penalty", "seed", "think"]
    _thinking_models: dict[str, bool] = {}  # model -> has the "thinking" capability (from /api/show), per process
    connection_hint = ("Is Ollama installed and running? Get it from https://ollama.com/download, start it, "
                       "then press Test again.")

    def __init__(self, base_url, api_key, config=None, transport=None):
        super().__init__(base_url or "http://localhost:11434", api_key, config, transport)
        self.is_cloud = not _is_local_url(self.base_url)  # v1.6: an Ollama server elsewhere is not local or offline

    def _options(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self.filter_params(params)
        p.pop("think", None)  # a top-level request field, not a model option
        mapping = {"max_tokens": "num_predict", "context_size": "num_ctx"}
        return {mapping.get(k, k): v for k, v in p.items()}

    @staticmethod
    def _think(params: dict[str, Any]) -> bool | None:
        v = (params or {}).get("think")
        if isinstance(v, str):
            v = {"true": True, "on": True, "false": False, "off": False}.get(v.strip().lower())
        return v if isinstance(v, bool) else None

    async def _supports_thinking(self, model: str) -> bool:
        if model not in self._thinking_models:
            try:
                OllamaAdapter._thinking_models[model] = "thinking" in (await self.show(model)).get("capabilities", [])
            except (ProviderError, ValueError):
                return False  # unknown: never send "think" (older Ollama / models reject it)
        return self._thinking_models[model]

    async def version(self) -> str:
        data = await self._get_json("/api/version", timeout=4.0)
        return str(data.get("version", "unknown"))

    async def list_models(self) -> list[ModelInfo]:
        data = await self._get_json("/api/tags")
        out = []
        for m in data.get("models", []):
            d = m.get("details") or {}
            out.append(ModelInfo(id=m.get("name") or m.get("model"), display_name=m.get("name") or "",
                                 size_bytes=m.get("size"),
                                 details={"parameter_size": d.get("parameter_size"), "quantization": d.get("quantization_level"),
                                          "family": d.get("family"), "modified_at": m.get("modified_at")}))
        return out

    async def running_models(self) -> list[str]:
        try:
            data = await self._get_json("/api/ps", timeout=5.0)
        except ProviderError:
            return []
        return [m.get("name") for m in data.get("models", []) if m.get("name")]

    async def test_connection(self, model_id: str | None = None) -> dict[str, Any]:
        ver = await self.version()
        models = await self.list_models()
        msg = f"Ollama {ver} is running with {len(models)} installed model(s)."
        if not models:
            msg += " Download a model below to start."
        return {"ok": True, "message": msg, "model_count": len(models), "version": ver}

    async def show(self, model: str) -> dict[str, Any]:
        try:
            async with self.client(httpx.Timeout(20.0)) as c:
                r = await c.post(self.base_url + "/api/show", json={"model": model})
        except Exception as e:
            raise error_from_exception(e, self.label, self.connection_hint)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)
        data = r.json()
        info = data.get("model_info") or {}
        ctx = next((v for k, v in info.items() if k.endswith(".context_length")), None)
        return {"details": data.get("details") or {}, "parameters": data.get("parameters", ""),
                "context_length": ctx, "capabilities": data.get("capabilities") or [], "license": (data.get("license") or "")[:300]}

    async def delete(self, model: str) -> None:
        try:
            async with self.client(httpx.Timeout(30.0)) as c:
                r = await c.request("DELETE", self.base_url + "/api/delete", json={"model": model})
        except Exception as e:
            raise error_from_exception(e, self.label, self.connection_hint)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)

    async def pull(self, model: str) -> AsyncIterator[dict[str, Any]]:
        """Yield real NDJSON progress objects from POST /api/pull."""
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
        try:
            async with self.client(timeout) as c:
                async with c.stream("POST", self.base_url + "/api/pull", json={"model": model, "stream": True}) as r:
                    if r.status_code >= 400:
                        body = (await r.aread()).decode("utf-8", "replace")
                        raise error_from_status(r.status_code, body, self.label)
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        obj = parse_json(line)
                        if obj is None:
                            continue
                        if obj.get("error"):
                            raise ProviderError("bad_request", f"Ollama could not download '{model}': {obj['error']}", obj["error"])
                        yield obj
        except ProviderError:
            raise
        except Exception as e:
            raise error_from_exception(e, self.label, self.connection_hint)

    async def stream_chat(self, model, system, messages, params) -> AsyncIterator[str]:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": m.role, "content": m.content} for m in messages if m.content.strip()]
        body: dict[str, Any] = {"model": model, "messages": msgs, "stream": True}
        if await self._supports_thinking(model):
            body["think"] = bool(self._think(params))
        opts = self._options(params)
        if opts:
            body["options"] = opts
        try:
            async with self.client() as c:
                async with c.stream("POST", self.base_url + "/api/chat", json=body) as r:
                    if r.status_code >= 400:
                        text = (await r.aread()).decode("utf-8", "replace")
                        raise error_from_status(r.status_code, text, self.label)
                    finished = False
                    wrote = thought = False
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        obj = parse_json(line)
                        if obj is None:
                            continue
                        if obj.get("error"):
                            raise ProviderError("bad_request", f"Ollama: {obj['error']}", obj["error"])
                        msg = obj.get("message") or {}
                        thought = thought or bool(msg.get("thinking"))
                        piece = msg.get("content") or ""
                        if piece:
                            wrote = True
                            yield piece
                        if obj.get("done"):
                            finished = True
                            self.last_finish = {"reason": obj.get("done_reason")}
                            if not wrote and thought and obj.get("done_reason") == "length":
                                # thinking models spend num_predict on reasoning first (seen with qwen3:14b)
                                raise ProviderError(
                                    "invalid_response",
                                    "Ollama: the model used its whole output budget for reasoning before writing the "
                                    "reply. Raise 'Max output tokens' or set 'Thinking' to Off for this model "
                                    "(Settings → Providers & models), then retry.", "done_reason=length, thinking only")
                            break
                    if not finished:
                        raise stream_truncated(self.label)
        except ProviderError:
            raise
        except Exception as e:
            raise error_from_exception(e, self.label, self.connection_hint)

    async def complete(self, model, system, messages, params, json_mode: bool = False,
                       json_schema: dict[str, Any] | None = None) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": m.role, "content": m.content} for m in messages]
        body: dict[str, Any] = {"model": model, "messages": msgs, "stream": False}
        if json_mode:
            body["format"] = json_schema or "json"
            # structured extraction gains nothing from reasoning, and thinking tokens share num_predict with the answer
            # (observed with qwen3:14b: empty or cut-off JSON); explicit profile settings still win
            think = self._think(params)
            if await self._supports_thinking(model):
                body["think"] = False if think is None else think
        opts = self._options(params)
        if opts:
            body["options"] = opts
        try:
            async with self.client() as c:
                r = await c.post(self.base_url + "/api/chat", json=body)
        except Exception as e:
            raise error_from_exception(e, self.label, self.connection_hint)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)
        data = r.json()
        text = ((data.get("message") or {}).get("content")) or ""
        if json_mode and data.get("done_reason") == "length":
            raise structured_error("truncated", self.label, f"done_reason=length, {len(text)} chars")
        if json_mode and not text.strip():
            raise structured_error("empty_output", self.label, f"done_reason={data.get('done_reason')}")
        return text


# =========================================================================== anthropic
class AnthropicAdapter(ProviderAdapter):
    provider_type = "anthropic"
    supports_json_schema = True  # the adapter picks native schema / JSON mode / prompt-only itself
    label = "Anthropic"
    supported_params = ["temperature", "top_p", "top_k", "max_tokens"]
    is_cloud = True
    API_VERSION = "2023-06-01"

    def __init__(self, base_url, api_key, config=None, transport=None):
        super().__init__(base_url or "https://api.anthropic.com", api_key, config, transport)

    def headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("auth", "Anthropic: no API key saved. Add one in Settings → Providers.")
        return {"x-api-key": self.api_key, "anthropic-version": self.API_VERSION, "content-type": "application/json"}

    async def list_models(self) -> list[ModelInfo]:
        data = await self._get_json("/v1/models?limit=1000")
        return [ModelInfo(m["id"], m.get("display_name") or m["id"]) for m in data.get("data", [])]

    def _body(self, model, system, messages, params, stream: bool) -> dict[str, Any]:
        p = self.filter_params(params)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": int(p.pop("max_tokens", 1024)),
            "messages": [{"role": m.role, "content": m.content} for m in normalize_alternating(messages)],
            "stream": stream,
        }
        if system:
            body["system"] = system
        body.update(p)
        return body

    async def stream_chat(self, model, system, messages, params) -> AsyncIterator[str]:
        body = self._body(model, system, messages, params, True)
        try:
            async with self.client() as c:
                async with c.stream("POST", self.base_url + "/v1/messages", json=body, headers=self.headers()) as r:
                    if r.status_code >= 400:
                        text = (await r.aread()).decode("utf-8", "replace")
                        raise error_from_status(r.status_code, text, self.label)
                    finished = False
                    async for _event, data in iter_sse(r):
                        obj = parse_json(data)
                        if not isinstance(obj, dict):
                            continue
                        t = obj.get("type")
                        if t == "content_block_delta" and (obj.get("delta") or {}).get("type") == "text_delta":
                            yield obj["delta"].get("text", "")
                        elif t == "message_delta":
                            self.last_finish = {"reason": (obj.get("delta") or {}).get("stop_reason")}
                        elif t == "error":
                            err = obj.get("error") or {}
                            cat = "rate_limit" if err.get("type") == "rate_limit_error" else (
                                "unavailable" if err.get("type") == "overloaded_error" else "bad_request")
                            raise ProviderError(cat, f"Anthropic: {FRIENDLY[cat]}", json.dumps(err)[:1000])
                        elif t == "message_stop":
                            finished = True
                            break
                    if not finished:
                        raise stream_truncated(self.label)
        except ProviderError:
            raise
        except Exception as e:
            raise error_from_exception(e, self.label)

    async def complete(self, model, system, messages, params, json_mode: bool = False,
                       json_schema: dict[str, Any] | None = None) -> str:
        body = self._body(model, system, messages, params, False)
        # Messages API structured outputs; models/accounts without it answer 400 and we fall back to prompt-only JSON
        native = bool(json_mode and json_schema and self.config.get("structured_outputs", True))
        if native:
            body["output_config"] = {"format": {"type": "json_schema", "schema": strict_schema(json_schema)}}
        try:
            async with self.client() as c:
                r = await c.post(self.base_url + "/v1/messages", json=body, headers=self.headers())
                if r.status_code == 400 and native:
                    body.pop("output_config")
                    r = await c.post(self.base_url + "/v1/messages", json=body, headers=self.headers())
        except Exception as e:
            raise error_from_exception(e, self.label)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if json_mode:
            if data.get("stop_reason") == "refusal":
                raise structured_error("refusal", self.label, "stop_reason=refusal")
            if data.get("stop_reason") == "max_tokens":
                raise structured_error("truncated", self.label, f"stop_reason=max_tokens, {len(text)} chars")
            if not text.strip():
                raise structured_error("empty_output", self.label, f"stop_reason={data.get('stop_reason')}")
        return text


# =========================================================================== openai (Responses API)
class OpenAIAdapter(ProviderAdapter):
    """OpenAI's current recommended Responses API (/v1/responses)."""

    provider_type = "openai"
    supports_json_schema = True  # the adapter picks native schema / JSON mode / prompt-only itself
    label = "OpenAI"
    supported_params = ["temperature", "top_p", "max_tokens"]
    is_cloud = True

    def __init__(self, base_url, api_key, config=None, transport=None):
        super().__init__(base_url or "https://api.openai.com/v1", api_key, config, transport)

    def headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("auth", "OpenAI: no API key saved. Add one in Settings → Providers.")
        h = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.config.get("organization"):
            h["OpenAI-Organization"] = self.config["organization"]
        return h

    async def list_models(self) -> list[ModelInfo]:
        data = await self._get_json("/models")
        return sorted((ModelInfo(m["id"], m["id"]) for m in data.get("data", [])), key=lambda m: m.id)

    def _body(self, model, system, messages, params, stream):
        p = self.filter_params(params)
        body: dict[str, Any] = {
            "model": model,
            "input": [{"role": m.role, "content": m.content} for m in messages if m.content.strip()],
            "stream": stream,
            "store": False,
        }
        if system:
            body["instructions"] = system
        if "max_tokens" in p:
            body["max_output_tokens"] = int(p.pop("max_tokens"))
        body.update(p)
        return body

    async def stream_chat(self, model, system, messages, params) -> AsyncIterator[str]:
        body = self._body(model, system, messages, params, True)
        try:
            async with self.client() as c:
                async with c.stream("POST", self.base_url + "/responses", json=body, headers=self.headers()) as r:
                    if r.status_code >= 400:
                        text = (await r.aread()).decode("utf-8", "replace")
                        raise error_from_status(r.status_code, text, self.label)
                    finished = False
                    async for _event, data in iter_sse(r):
                        obj = parse_json(data)
                        if not isinstance(obj, dict):
                            continue
                        t = obj.get("type", "")
                        if t == "response.output_text.delta":
                            yield obj.get("delta", "")
                        elif t in ("response.failed", "error"):
                            err = obj.get("error") or (obj.get("response") or {}).get("error") or obj
                            raise ProviderError("bad_request", f"OpenAI: {FRIENDLY['bad_request']}", json.dumps(err)[:1000])
                        elif t == "response.completed":
                            finished = True
                            break
                    if not finished:
                        raise stream_truncated(self.label)
        except ProviderError:
            raise
        except Exception as e:
            raise error_from_exception(e, self.label)

    async def complete(self, model, system, messages, params, json_mode: bool = False,
                       json_schema: dict[str, Any] | None = None) -> str:
        body = self._body(model, system, messages, params, False)
        if json_mode:
            # Structured Outputs (strict JSON Schema) where available, otherwise JSON mode; a 400 downgrades once
            body["text"] = ({"format": {"type": "json_schema", "name": "structured_output", "strict": True,
                                        "schema": strict_schema(json_schema)}}
                            if json_schema and self.config.get("structured_outputs", True) else {"format": {"type": "json_object"}})
        try:
            async with self.client() as c:
                r = await c.post(self.base_url + "/responses", json=body, headers=self.headers())
                if r.status_code == 400 and json_mode and body["text"]["format"]["type"] == "json_schema":
                    body["text"] = {"format": {"type": "json_object"}}
                    r = await c.post(self.base_url + "/responses", json=body, headers=self.headers())
        except Exception as e:
            raise error_from_exception(e, self.label)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)
        data = r.json()
        parts, refused = [], None
        for item in data.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    parts.append(c.get("text", ""))
                elif c.get("type") == "refusal":
                    refused = c.get("refusal") or "refused"
        text = data.get("output_text") or "".join(parts)
        if json_mode:
            if refused:
                raise structured_error("refusal", self.label, str(refused)[:300])
            if data.get("status") == "incomplete":
                reason = (data.get("incomplete_details") or {}).get("reason")
                raise structured_error("truncated" if reason == "max_output_tokens" else "empty_output", self.label,
                                       f"status=incomplete, reason={reason}")
            if not text.strip():
                raise structured_error("empty_output", self.label, f"status={data.get('status')}")
        return text


# =========================================================================== openai-compatible
class OpenAICompatAdapter(ProviderAdapter):
    """Chat Completions (/chat/completions): the de-facto API of OpenRouter, LM Studio, llama.cpp, vLLM, etc."""

    provider_type = "openai_compat"
    supports_json_schema = True  # the adapter picks native schema / JSON mode / prompt-only itself
    label = "OpenAI-compatible"
    # "think" is OpenRouter's reasoning switch for story replies (see stream_chat); other servers ignore it
    supported_params = ["temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty", "seed",
                        "top_k", "repeat_penalty", "think"]

    def __init__(self, base_url, api_key, config=None, transport=None):
        super().__init__(base_url, api_key, config, transport)
        self.label = self.config.get("label") or "OpenAI-compatible"
        self.is_cloud = not _is_local_url(self.base_url)

    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        for k, v in (self.config.get("extra_headers") or {}).items():
            if k.lower() not in ("authorization",):
                h[str(k)] = str(v)
        return h

    async def list_models(self) -> list[ModelInfo]:
        route = self.config.get("models_route") or "/models"
        data = await self._get_json(route)
        items = data.get("data", data if isinstance(data, list) else [])
        return [ModelInfo(m["id"], m.get("name") or m["id"], context_length=m.get("context_length"), details=_listed_price(m))
                for m in items if m.get("id")]

    async def _test_openrouter(self, model_id: str | None) -> dict[str, Any]:
        """OpenRouter's model list is public, so it says nothing about the key (v1.6: a wrong key used to report
        "Connected"). ``/key`` checks the key itself and runs no model, so this costs nothing."""
        if not self.api_key:
            raise ProviderError("auth", f"{self.label}: no API key saved yet. Paste your key, save it, then test again.")
        info = (await self._get_json("/key")).get("data") or {}
        models = await self.list_models()
        msg = "Your key works."
        left = info.get("limit_remaining")
        if isinstance(left, (int, float)):
            msg += f" Remaining on this key's limit: ${left:.2f}."
        if model_id:
            if not any(m.id == model_id for m in models):
                raise ProviderError("not_found", f"{self.label}: your key works, but {model_id} is not in the catalog right now. "
                                                 "Choose another model; your stories keep their selection until you do.")
            msg += f" {model_id} is available."
        return {"ok": True, "message": msg, "model_count": len(models), "billable": False}

    async def test_connection(self, model_id: str | None = None) -> dict[str, Any]:
        if self.is_openrouter:
            return await self._test_openrouter(model_id)
        try:
            models = await self.list_models()
            return {"ok": True, "message": f"Connected. {len(models)} model(s) listed.", "model_count": len(models)}
        except ProviderError as e:
            if not model_id or self.is_cloud or e.category in ("auth", "network", "timeout"):
                raise  # a remote server may bill: a real request only through the explicit model test (probe)
        # local server without a model list: a 1-token generation against the manual model costs nothing
        await self.complete(model_id, "", [ChatMessage("user", "Reply with OK.")], {"max_tokens": 4})
        return {"ok": True, "message": "Connected (model listing unsupported; a test generation with the manual model succeeded).",
                "model_count": 0}

    async def probe(self, model_id: str) -> dict[str, Any]:
        body = self._body(model_id, "", [ChatMessage("user", "Reply with OK.")], {"max_tokens": 16}, False)
        if self.is_openrouter:
            body["reasoning"] = {"enabled": False}
        try:
            async with self.client() as c:
                r = await c.post(self.base_url + "/chat/completions", json=body, headers=self.headers())
        except Exception as e:
            raise error_from_exception(e, self.label)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)
        data = r.json()
        if isinstance(data.get("error"), dict):
            raise ProviderError("invalid_response", f"{self.label}: {FRIENDLY['invalid_response']}", json.dumps(data["error"])[:1000])
        usage = _usage(data)
        cost = f" Reported cost: ${usage['cost']:.6f}." if isinstance((usage or {}).get("cost"), (int, float)) else ""
        return {"ok": True, "message": f"{model_id} answered a short test request.{cost}", "usage": usage, "billable": True}

    def _body(self, model, system, messages, params, stream):
        p = self.filter_params(params)
        p.pop("think", None)  # never a body field: stream_chat turns it into OpenRouter's reasoning option
        if "repeat_penalty" in p:
            p["repetition_penalty"] = p.pop("repeat_penalty")
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": m.role, "content": m.content} for m in messages if m.content.strip()]
        body: dict[str, Any] = {"model": model, "messages": msgs, "stream": stream}
        body.update(p)
        if self.is_openrouter:
            body["usage"] = {"include": True}  # OpenRouter's own token and cost figures, shown under the reply (v1.6)
        return body

    async def stream_chat(self, model, system, messages, params) -> AsyncIterator[str]:
        body = self._body(model, system, messages, params, True)
        # v1.6.1: hidden reasoning shares max_tokens with the story, and reasoning came first: the owner's GLM-5 replies spent
        # all 1,024 tokens on it, leaving "The". Off for narration unless the model's Thinking setting turns it on.
        if self.is_openrouter and OllamaAdapter._think(params) is not True:
            body["reasoning"] = {"enabled": False}
        self.last_finish = {"reasoning": "off" if "reasoning" in body else "model default"}
        try:
            async with self.client() as c:
                for rejected_once in (False, True):
                    async with c.stream("POST", self.base_url + "/chat/completions", json=body, headers=self.headers()) as r:
                        if r.status_code >= 400:
                            text = (await r.aread()).decode("utf-8", "replace")
                            if r.status_code == 400 and not rejected_once and "reasoning" in body and "reasoning" in text.lower():
                                body.pop("reasoning")  # a model that cannot switch it off: refused, so nothing was generated
                                self.last_finish["reasoning"] = "model default"
                                continue
                            raise error_from_status(r.status_code, text, self.label)
                        finished = False
                        async for _event, data in iter_sse(r):
                            if data.strip() == "[DONE]":
                                finished = True
                                break
                            obj = parse_json(data)
                            if not isinstance(obj, dict):
                                continue
                            self.last_finish.update({k: obj[v] for k, v in (("generation_id", "id"), ("provider", "provider")) if obj.get(v)})
                            if obj.get("error"):  # HTTP stayed 200: the failure arrives inside the stream
                                raise ProviderError("stream_error", f"{self.label}: {FRIENDLY['stream_error']}", json.dumps(obj["error"])[:1000])
                            self.last_usage = _usage(obj) or self.last_usage
                            for ch in obj.get("choices", []):
                                piece = (ch.get("delta") or {}).get("content")
                                if piece:
                                    yield piece
                                reason = ch.get("finish_reason")
                                if reason == "error":
                                    raise ProviderError("stream_error", f"{self.label}: {FRIENDLY['stream_error']}", "finish_reason=error")
                                if reason:
                                    finished = True  # some servers end without a [DONE] line
                                    self.last_finish.update(reason=reason, native=ch.get("native_finish_reason"))
                        if not finished:
                            raise stream_truncated(self.label)
                        return
        except ProviderError:
            raise
        except Exception as e:
            raise error_from_exception(e, self.label)

    async def complete(self, model, system, messages, params, json_mode: bool = False,
                       json_schema: dict[str, Any] | None = None) -> str:
        body = self._body(model, system, messages, params, False)
        mode = self.structured_mode()
        if json_mode and mode != "prompt":
            body["response_format"] = (self._schema_format(json_schema)
                                       if json_schema and mode == "json_schema" else {"type": "json_object"})
        if json_mode and self.is_openrouter and self.config.get("structured_reasoning_off", True):
            # OpenRouter's normalised reasoning switch: a structured answer gains nothing from hidden reasoning, which
            # shares max_tokens with it (live: z-ai/glm-5 spent 658 of 940 tokens reasoning; with it off: 0 of 288)
            body["reasoning"] = {"enabled": False}
        try:
            async with self.client() as c:
                r = await c.post(self.base_url + "/chat/completions", json=body, headers=self.headers())
                # unsupported options: downgrade one step at a time (schema -> JSON mode -> none; reasoning switch off)
                # LM Studio and llama.cpp reject {"type": "json_object"} but accept a JSON Schema: try the schema
                # before giving up on constrained output (without it a small local model often wraps the JSON in prose)
                tried = {(body.get("response_format") or {}).get("type")}
                while r.status_code == 400 and json_mode and ("reasoning" in body or "response_format" in body):
                    kind = (body.get("response_format") or {}).get("type")
                    if "reasoning" in body and "reasoning" in r.text.lower():
                        body.pop("reasoning")
                    elif kind == "json_schema" and "json_object" not in tried:
                        body["response_format"] = {"type": "json_object"}
                    elif kind == "json_object" and json_schema and "json_schema" not in tried:
                        body["response_format"] = self._schema_format(json_schema)
                    elif "response_format" in body:
                        body.pop("response_format")
                    else:
                        body.pop("reasoning")
                    tried.add((body.get("response_format") or {}).get("type"))
                    r = await c.post(self.base_url + "/chat/completions", json=body, headers=self.headers())
        except Exception as e:
            raise error_from_exception(e, self.label)
        if r.status_code >= 400:
            raise error_from_status(r.status_code, r.text, self.label)
        data = r.json()
        if isinstance(data.get("error"), dict):  # some gateways report upstream failures inside a 200 body
            raise ProviderError("invalid_response", f"{self.label}: {FRIENDLY['invalid_response']}", json.dumps(data["error"])[:1000])
        ch = (data.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        text = msg.get("content") or ""
        if json_mode:
            if msg.get("refusal") or ch.get("finish_reason") == "content_filter":
                raise structured_error("refusal", self.label, str(msg.get("refusal") or "finish_reason=content_filter")[:300])
            if ch.get("finish_reason") == "length":
                raise structured_error("truncated", self.label, f"finish_reason=length, {len(text)} chars, "
                                       f"usage={json.dumps(data.get('usage') or {})[:300]}")
            if not text.strip():
                raise structured_error("empty_output", self.label, f"finish_reason={ch.get('finish_reason')}, "
                                       f"usage={json.dumps(data.get('usage') or {})[:300]}")
        return text

    @property
    def is_openrouter(self) -> bool:
        return "openrouter.ai" in (self.base_url or "")

    def structured_mode(self) -> str:
        """Capability for JSON answers: explicit provider setting, else JSON Schema for OpenRouter (it validates or
        forwards it per model) and plain JSON mode for unknown OpenAI-compatible servers. Never more than configured."""
        cfg = self.config.get("structured_output")
        if cfg in ("json_schema", "json_object", "prompt"):
            return cfg
        if self.config.get("json_mode") is False:
            return "prompt"
        # local servers (LM Studio, llama.cpp, Ollama's OpenAI endpoint) constrain output with a JSON Schema grammar;
        # LM Studio refuses plain JSON mode outright
        return "json_schema" if self.is_openrouter or _is_local_url(self.base_url) else "json_object"

    @staticmethod
    def _schema_format(json_schema: dict[str, Any]) -> dict[str, Any]:
        return {"type": "json_schema", "json_schema": {"name": "structured_output", "strict": False,
                                                       "schema": strict_schema(json_schema)}}


def _listed_price(m: dict[str, Any]) -> dict[str, Any]:
    """USD per 1M tokens when the listing gives real prices (OpenRouter's catalog does; most servers do not)."""
    p = m.get("pricing") if isinstance(m.get("pricing"), dict) else {}
    try:
        i, o = float(p["prompt"]), float(p["completion"])
    except (KeyError, TypeError, ValueError):
        return {}
    return {"price_in": round(i * 1e6, 4), "price_out": round(o * 1e6, 4)} if i >= 0 and o >= 0 else {}


def _usage(data: dict[str, Any]) -> dict[str, Any] | None:
    """Token counts and cost exactly as the provider reported them (never estimated here)."""
    u = data.get("usage")
    if not isinstance(u, dict):
        return None
    out = {k: u.get(k) for k in ("prompt_tokens", "completion_tokens", "cost") if u.get(k) is not None}
    thought = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if thought is not None:
        out["reasoning_tokens"] = thought
    return out or None


def _is_local_url(url: str) -> bool:
    return bool(re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:\d+)?(/|$)", url or ""))


ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "mock": MockAdapter,
    "ollama": OllamaAdapter,
    "anthropic": AnthropicAdapter,
    "openai": OpenAIAdapter,
    "openai_compat": OpenAICompatAdapter,
}

PROVIDER_PRESETS = [
    {"provider_type": "ollama", "display_name": "Ollama (local)", "base_url": "http://localhost:11434", "needs_key": False},
    {"provider_type": "anthropic", "display_name": "Anthropic Claude", "base_url": "https://api.anthropic.com", "needs_key": True},
    {"provider_type": "openai", "display_name": "OpenAI", "base_url": "https://api.openai.com/v1", "needs_key": True},
    {"provider_type": "openai_compat", "display_name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "needs_key": True},
    {"provider_type": "openai_compat", "display_name": "LM Studio (local)", "base_url": "http://localhost:1234/v1", "needs_key": False},
    {"provider_type": "openai_compat", "display_name": "Custom OpenAI-compatible", "base_url": "", "needs_key": False},
]
