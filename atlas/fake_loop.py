from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from atlas.tool_protocol import ToolCall, ToolCallError, parse_tool_call


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
    error: ToolCallError | None = None


def run_fake_tool_loop(
    initial_prompt: str,
    adapter: FakeTgenieAdapter,
    tools: Mapping[str, ToolHandler],
) -> FakeToolLoopResult:
    status_events = ["waiting-for-model"]
    model_response = adapter.send(initial_prompt)

    while True:
        status_events.append("parsing-tool-call")
        try:
            parsed = parse_tool_call(model_response, available_tools=tools.keys())
        except ValueError:
            status_events.append("final-response")
            return FakeToolLoopResult(
                final_response=model_response,
                status_events=status_events,
            )

        if isinstance(parsed, ToolCallError):
            status_events.append("error")
            return FakeToolLoopResult(
                final_response=None,
                status_events=status_events,
                error=parsed,
            )

        status_events.append("executing-tool")
        tool_result = tools[parsed.tool](parsed.args)
        status_events.append("waiting-for-model")
        model_response = adapter.send(format_tool_result(parsed, tool_result))


def format_tool_result(tool_call: ToolCall, result: Any) -> str:
    payload = {
        "type": "atlas.tool_result",
        "tool": tool_call.tool,
        "result": result,
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
