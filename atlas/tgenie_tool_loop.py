from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from atlas.fake_loop import format_tool_result
from atlas.tool_protocol import ToolCallError, parse_tool_call
from atlas.tool_runtime import ToolRuntime


SUPPORTED_TOOLS = {
    "file.list",
    "file.read",
    "file.search",
    "file.write",
    "shell.run",
}


class TgenieToolConversation(Protocol):
    async def send_single_turn(self, user_prompt: str) -> str:
        pass

    async def send_followup(self, message: str) -> str:
        pass


@dataclass(frozen=True)
class TgenieToolLoopResult:
    final_response: str | None
    status_events: list[str]
    error: ToolCallError | None = None


async def run_tgenie_tool_loop(
    *,
    initial_prompt: str,
    conversation: TgenieToolConversation,
    tool_runtime: ToolRuntime,
) -> TgenieToolLoopResult:
    status_events = ["waiting-for-model"]
    model_response = await conversation.send_single_turn(initial_prompt)

    while True:
        status_events.append("parsing-tool-call")
        try:
            parsed = parse_tool_call(model_response, available_tools=SUPPORTED_TOOLS)
        except ValueError:
            status_events.append("final-response")
            return TgenieToolLoopResult(final_response=model_response, status_events=status_events)

        if isinstance(parsed, ToolCallError):
            status_events.append("tool-call-error")
            status_events.append("sending-tool-error")
            status_events.append("waiting-for-model")
            model_response = await conversation.send_followup(format_tool_call_error(parsed))
            continue

        status_events.append("executing-tool")
        tool_result = tool_runtime.run(parsed.tool, parsed.args)
        status_events.append("sending-tool-result")
        tool_result_message = format_tool_result(parsed, tool_result.to_dict())
        status_events.append("waiting-for-model")
        model_response = await conversation.send_followup(tool_result_message)


def format_tool_call_error(error: ToolCallError) -> str:
    payload = {
        "type": "atlas.tool_call_error",
        "code": error.code,
        "message": error.message,
        "instruction": "Send one corrected atlas.tool_call fenced JSON block.",
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
