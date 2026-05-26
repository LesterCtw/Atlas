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
                message="Tool call JSON 格式錯誤，請重送單一合法的 Atlas tool call。",
            )
        if isinstance(payload, dict) and payload.get("type") == TOOL_CALL_TYPE:
            tool_payloads.append(payload)

    if len(tool_payloads) > 1:
        return ToolCallError(
            code="multiple-tool-calls",
            message="一次只能執行單一 Atlas tool call，請拆成下一輪再重送。",
        )

    if len(tool_payloads) == 1:
        payload = tool_payloads[0]
        if "tool" not in payload:
            return ToolCallError(
                code="missing-tool",
                message="Tool call 缺少 tool name，請重送完整 tool call。",
            )
        tool = payload["tool"]
        if available_tools is not None and tool not in available_tools:
            return ToolCallError(
                code="unknown-tool",
                message=f"未知工具：{tool}。請改用 Atlas 目前支援的工具。",
            )
        if "args" not in payload:
            return ToolCallError(
                code="missing-args",
                message="Tool call 缺少 args object，請重送完整參數。",
            )
        args = payload["args"]
        if not isinstance(args, dict):
            return ToolCallError(
                code="invalid-args",
                message="Tool call 的 args 必須是 JSON object。",
            )
        return ToolCall(tool=tool, args=args)

    raise ValueError("No Atlas tool call found.")
