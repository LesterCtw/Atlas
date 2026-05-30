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


def find_json_object_contents(text: str) -> tuple[str, ...]:
    decoder = json.JSONDecoder()
    contents: list[str] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start == -1:
            break

        try:
            payload, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue

        if isinstance(payload, dict):
            contents.append(text[start:end])
        index = max(end, start + 1)

    return tuple(contents)


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


def parse_first_json_object(text: str) -> dict[str, Any]:
    matches = find_json_fence_contents(text)
    if matches:
        raw_json = matches[0]
    else:
        start = text.find("{")
        if start == -1:
            raise MissingJsonFenceError("No JSON object found.")
        try:
            payload, _end = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError as error:
            raise MalformedJsonFenceError("JSON object is malformed.") from error
        if not isinstance(payload, dict):
            raise JsonFencePayloadError("JSON payload must be an object.")
        return payload

    payload = load_json_fence_content(raw_json)
    if not isinstance(payload, dict):
        raise JsonFencePayloadError("JSON payload must be an object.")
    return payload


def format_json_fence(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
