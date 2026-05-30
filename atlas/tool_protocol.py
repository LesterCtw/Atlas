from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from atlas.json_fences import (
    MalformedJsonFenceError,
    find_json_fence_contents,
    find_json_object_contents,
    load_json_fence_content,
)


TOOL_CALL_TYPE = "atlas.tool_call"
TOOL_BATCH_TYPE = "atlas.tool_batch"
DEFAULT_MAX_TOOL_BATCH_CALLS = 5


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolBatchCall:
    id: str
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolBatch:
    calls: tuple[ToolBatchCall, ...]


@dataclass(frozen=True)
class ToolCallError:
    code: str
    message: str


def parse_tool_call(
    model_response: str,
    available_tools: Collection[str] | None = None,
    batch_tools: Collection[str] | None = None,
    max_batch_calls: int = DEFAULT_MAX_TOOL_BATCH_CALLS,
) -> ToolCall | ToolBatch | ToolCallError:
    tool_payloads: list[dict[str, Any]] = []
    raw_json_contents = find_json_fence_contents(model_response)
    if not raw_json_contents:
        raw_json_contents = find_json_object_contents(model_response)

    for raw_json in raw_json_contents:
        try:
            payload = load_json_fence_content(raw_json)
        except MalformedJsonFenceError:
            return ToolCallError(
                code="malformed-json",
                message="Tool call JSON is invalid. Send one valid JSON Atlas tool request.",
            )
        if isinstance(payload, dict) and payload.get("type") in {TOOL_CALL_TYPE, TOOL_BATCH_TYPE}:
            tool_payloads.append(payload)

    if (
        not tool_payloads
        and (TOOL_CALL_TYPE in model_response or TOOL_BATCH_TYPE in model_response)
        and "{" in model_response
    ):
        return ToolCallError(
            code="malformed-json",
            message="Tool call JSON is invalid. Send one valid JSON Atlas tool request.",
        )

    if len(tool_payloads) > 1:
        return ToolCallError(
            code="multiple-tool-calls",
            message="Only a single Atlas tool call or tool batch can run at a time. Send the next request in a later turn.",
        )

    if len(tool_payloads) == 1:
        payload = tool_payloads[0]
        if payload.get("type") == TOOL_BATCH_TYPE:
            return _parse_tool_batch_payload(
                payload,
                available_tools=available_tools,
                batch_tools=batch_tools,
                max_batch_calls=max_batch_calls,
            )
        return _parse_tool_call_payload(payload, available_tools=available_tools)

    raise ValueError("No Atlas tool call found.")


def _parse_tool_call_payload(
    payload: dict[str, Any],
    *,
    available_tools: Collection[str] | None,
) -> ToolCall | ToolCallError:
    if "tool" not in payload:
        return ToolCallError(
            code="missing-tool",
            message="Tool call is missing a tool name. Send a complete tool call.",
        )
    tool = payload["tool"]
    if not isinstance(tool, str) or not tool.strip():
        return ToolCallError(
            code="invalid-tool",
            message="Tool call tool name must be a non-empty string.",
        )
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


def _parse_tool_batch_payload(
    payload: dict[str, Any],
    *,
    available_tools: Collection[str] | None,
    batch_tools: Collection[str] | None,
    max_batch_calls: int,
) -> ToolBatch | ToolCallError:
    calls = payload.get("calls")
    if not isinstance(calls, list):
        return ToolCallError(
            code="invalid-batch-calls",
            message="Tool batch must include a calls array.",
        )
    if not calls:
        return ToolCallError(
            code="invalid-batch-calls",
            message="Tool batch calls array must not be empty.",
        )
    if len(calls) > max_batch_calls:
        return ToolCallError(
            code="batch-too-large",
            message=f"Tool batch can include at most {max_batch_calls} calls.",
        )

    parsed_calls: list[ToolBatchCall] = []
    seen_ids: set[str] = set()
    for index, call in enumerate(calls, start=1):
        if not isinstance(call, dict):
            return ToolCallError(
                code="invalid-batch-call",
                message=f"Tool batch call {index} must be an object.",
            )
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id.strip():
            return ToolCallError(
                code="invalid-batch-call-id",
                message=f"Tool batch call {index} must include a non-empty string id.",
            )
        if call_id in seen_ids:
            return ToolCallError(
                code="duplicate-batch-call-id",
                message=f"Tool batch call id must be unique: {call_id}.",
            )
        seen_ids.add(call_id)

        parsed = _parse_tool_call_payload(call, available_tools=available_tools)
        if isinstance(parsed, ToolCallError):
            return ToolCallError(
                code=parsed.code,
                message=f"Tool batch call {call_id}: {parsed.message}",
            )
        if batch_tools is not None and parsed.tool not in batch_tools:
            return ToolCallError(
                code="batch-tool-not-allowed",
                message=(
                    f"Tool cannot be used in atlas.tool_batch: {parsed.tool}. "
                    "Use a single atlas.tool_call instead."
                ),
            )
        parsed_calls.append(ToolBatchCall(id=call_id, tool=parsed.tool, args=parsed.args))

    return ToolBatch(calls=tuple(parsed_calls))
