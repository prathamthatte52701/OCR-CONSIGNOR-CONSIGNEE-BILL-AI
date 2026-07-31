"""Robust JSON extraction from an LLM response that may wrap the object in markdown fences
or add stray commentary."""

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_object(raw: str) -> dict[str, Any]:
    fence_match = _FENCE_RE.search(raw)
    candidate = fence_match.group(1) if fence_match else raw

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        object_match = _OBJECT_RE.search(candidate)
        if object_match is None:
            raise ValueError(f"No JSON object found in response: {raw[:200]!r}") from None
        parsed = json.loads(object_match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    return parsed
