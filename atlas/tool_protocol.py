from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any


TOOL_CALL_TYPE = "atlas.tool_call"


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolCallError:
    code: str
    message: str


_JSON_FENCE_PATTERN = re.compile(r"```json\s*(.*?)```", re.DOTALL)


def parse_tool_call(
    model_response: str,
    available_tools: Collection[str] | None = None,
) -> ToolCall | ToolCallError:
    tool_payloads: list[dict[str, Any]] = []

    for raw_json in _JSON_FENCE_PATTERN.findall(model_response):
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return ToolCallError(
                code="malformed-json",
                message="Tool call JSON is invalid. Send one valid JSON Atlas tool call.",
            )
        if isinstance(payload, dict) and payload.get("type") == TOOL_CALL_TYPE:
            tool_payloads.append(payload)

    if len(tool_payloads) > 1:
        return ToolCallError(
            code="multiple-tool-calls",
            message="Only a single Atlas tool call can run at a time. Send the next call in a later turn.",
        )

    if len(tool_payloads) == 1:
        payload = tool_payloads[0]
        if "tool" not in payload:
            return ToolCallError(
                code="missing-tool",
                message="Tool call is missing a tool name. Send a complete tool call.",
            )
        tool = payload["tool"]
        if available_tools is not None and tool not in available_tools:
            return ToolCallError(
                code="unknown-tool",
                message=f"Unknown tool: {tool}. Use one of the tools currently supported by Atlas.",
            )
        if "args" not in payload:
            return ToolCallError(
                code="missing-args",
                message="Tool call is missing an args object. Send complete arguments.",
            )
        args = payload["args"]
        if not isinstance(args, dict):
            return ToolCallError(
                code="invalid-args",
                message="Tool call args must be a JSON object.",
            )
        return ToolCall(tool=tool, args=args)

    raise ValueError("No Atlas tool call found.")
