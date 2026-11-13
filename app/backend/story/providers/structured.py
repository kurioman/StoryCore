"""Structured (JSON) output helpers shared by the provider adapters.

Each adapter decides which native mechanism it can use (strict JSON Schema, JSON mode, or prompt-only) and reports
problems with the *envelope* — output cut off by the token limit, a refusal, or no text at all — as a ``ProviderError``
before anyone tries to parse half a JSON object. Callers (scene analysis, memory capture) retry once on these.
"""
from __future__ import annotations

import copy
from typing import Any

from .base import ProviderError

STRUCTURED_FRIENDLY = {
    "truncated": "The model's structured answer was cut off by its output limit.",
    "refusal": "The model declined to produce the structured answer.",
    "empty_output": "The model returned no text for the structured answer (it may have spent its budget reasoning).",
}

# keywords outside the strict subset accepted by OpenAI strict mode / Anthropic structured outputs
_DROP = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "minLength", "maxLength",
         "pattern", "format", "default"}


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Copy of ``schema`` reduced to the portable strict subset: every object closed (additionalProperties false) with
    all properties required, numeric/length bounds removed (the application validates those itself)."""
    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        out = {k: walk(v) for k, v in node.items() if k not in _DROP}
        if out.get("type") == "object" and isinstance(out.get("properties"), dict):
            out["additionalProperties"] = False
            out["required"] = list(out["properties"].keys())
        return out

    return walk(copy.deepcopy(schema))


def structured_error(category: str, label: str, details: str = "") -> ProviderError:
    return ProviderError(category, f"{label}: {STRUCTURED_FRIENDLY[category]}", details)
