from __future__ import annotations

import json
import re
from typing import Any


_JSON_FENCE_PATTERN = re.compile(r"```json\s*(.*?)```", re.DOTALL)


class JsonFenceError(ValueError):
    pass


class MissingJsonFenceError(JsonFenceError):
    pass


class MalformedJsonFenceError(JsonFenceError):
    pass


class JsonFencePayloadError(JsonFenceError):
    pass


def find_json_fence_contents(text: str) -> tuple[str, ...]:
    return tuple(_JSON_FENCE_PATTERN.findall(text))


def load_json_fence_content(raw_json: str) -> Any:
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise MalformedJsonFenceError("Fenced JSON is malformed.") from error


def parse_first_json_fence_object(text: str) -> dict[str, Any]:
    matches = find_json_fence_contents(text)
    if not matches:
        raise MissingJsonFenceError("No fenced JSON block found.")

    payload = load_json_fence_content(matches[0])
    if not isinstance(payload, dict):
        raise JsonFencePayloadError("Fenced JSON payload must be an object.")
    return payload


def format_json_fence(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
