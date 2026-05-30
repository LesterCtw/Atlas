from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from atlas.json_fences import format_json_fence
from atlas.tool_protocol import ToolBatch, ToolCall, ToolCallError, parse_tool_call
from atlas.tool_loop_events import ToolLoopEvent


ToolHandler = Callable[[dict[str, Any]], Any]


class FakeTgenieAdapter:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.sent_messages: list[str] = []

    def send(self, message: str) -> str:
        self.sent_messages.append(message)
        if not self._responses:
            raise RuntimeError("Fake tGenie adapter has no response left.")
        return self._responses.pop(0)

    def inject(self, message: str) -> None:
        self.sent_messages.append(message)


@dataclass(frozen=True)
class FakeToolLoopResult:
    final_response: str | None
    status_events: list[str]
    events: tuple[ToolLoopEvent, ...] = ()
    error: ToolCallError | None = None


def run_fake_tool_loop(
    initial_prompt: str,
    adapter: FakeTgenieAdapter,
    tools: Mapping[str, ToolHandler],
) -> FakeToolLoopResult:
    status_events = ["waiting-for-model"]
    events: list[ToolLoopEvent] = [ToolLoopEvent(kind="user_prompt", message=initial_prompt)]
    model_response = adapter.send(initial_prompt)

    while True:
        status_events.append("parsing-tool-call")
        try:
            parsed = parse_tool_call(
                model_response,
                available_tools=tools.keys(),
                batch_tools=tools.keys(),
            )
        except ValueError:
            status_events.append("final-response")
            events.append(ToolLoopEvent(kind="assistant_final", message=model_response))
            return FakeToolLoopResult(
                final_response=model_response,
                status_events=status_events,
                events=tuple(events),
            )

        if isinstance(parsed, ToolCallError):
            status_events.append("error")
            events.append(
                ToolLoopEvent(
                    kind="tool_call_error",
                    message=model_response,
                    error_code=parsed.code,
                    error_message=parsed.message,
                )
            )
            return FakeToolLoopResult(
                final_response=None,
                status_events=status_events,
                events=tuple(events),
                error=parsed,
            )

        if isinstance(parsed, ToolBatch):
            events.append(
                ToolLoopEvent(
                    kind="assistant_tool_batch",
                    message=model_response,
                    tool="atlas.tool_batch",
                    args={"calls": [_batch_call_to_dict(call) for call in parsed.calls]},
                )
            )
            status_events.append("executing-tool-batch")
            batch_results = []
            for call in parsed.calls:
                tool_result = tools[call.tool](call.args)
                result = tool_result if isinstance(tool_result, dict) else {"value": tool_result}
                batch_results.append({"id": call.id, "tool": call.tool, "result": result})
            status_events.append("sending-tool-batch-result")
            tool_result_message = format_tool_batch_result(batch_results)
            events.append(
                ToolLoopEvent(
                    kind="tool_batch_result",
                    message=tool_result_message,
                    tool="atlas.tool_batch",
                    result={"results": batch_results},
                )
            )
            status_events.append("waiting-for-model")
            model_response = adapter.send(tool_result_message)
            continue

        events.append(
            ToolLoopEvent(
                kind="assistant_tool_call",
                message=model_response,
                tool=parsed.tool,
                args=dict(parsed.args),
            )
        )
        status_events.append("executing-tool")
        tool_result = tools[parsed.tool](parsed.args)
        tool_result_message = format_tool_result(parsed, tool_result)
        events.append(
            ToolLoopEvent(
                kind="tool_result",
                message=tool_result_message,
                tool=parsed.tool,
                result=tool_result if isinstance(tool_result, dict) else {"value": tool_result},
            )
        )
        status_events.append("waiting-for-model")
        model_response = adapter.send(tool_result_message)


def _batch_call_to_dict(call: Any) -> dict[str, Any]:
    return {"id": call.id, "tool": call.tool, "args": dict(call.args)}


def format_tool_result(tool_call: ToolCall, result: Any) -> str:
    payload = {
        "type": "atlas.tool_result",
        "tool": tool_call.tool,
        "result": result,
    }
    return format_json_fence(payload)


def format_tool_batch_result(results: list[dict[str, Any]]) -> str:
    payload = {
        "type": "atlas.tool_batch_result",
        "results": results,
    }
    return format_json_fence(payload)
