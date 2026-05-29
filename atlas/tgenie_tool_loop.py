from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from atlas.fake_loop import format_tool_result
from atlas.tool_protocol import ToolCallError, parse_tool_call
from atlas.tool_runtime import ToolResult, ToolRuntime, ToolRuntimeError


SUPPORTED_TOOLS = {
    "file.list",
    "file.read",
    "file.search",
    "file.write",
    "pdf.attach",
    "shell.run",
}


class TgenieToolConversation(Protocol):
    async def send_single_turn(self, user_prompt: str) -> str:
        pass

    async def send_followup(self, message: str) -> str:
        pass

    async def attach_pdf(self, path: Path) -> None:
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

        if parsed.tool == "pdf.attach":
            status_events.append("uploading-pdf")
            tool_result, status_event = await execute_pdf_attach(
                conversation=conversation,
                tool_runtime=tool_runtime,
                args=parsed.args,
            )
            status_events.append(status_event)
        else:
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


async def execute_pdf_attach(
    *,
    conversation: TgenieToolConversation,
    tool_runtime: ToolRuntime,
    args: dict[str, Any],
) -> tuple[ToolResult, str]:
    try:
        attachment = tool_runtime.prepare_pdf_attachment(args)
        await conversation.attach_pdf(attachment.path)
    except Exception as error:
        timed_out = is_pdf_attach_timeout(error)
        return (
            ToolResult(
                ok=False,
                status="timeout" if timed_out else "error",
                error=format_pdf_attach_error(error),
            ),
            "pdf-upload-timeout" if timed_out else "pdf-upload-failed",
        )

    return (
        ToolResult(ok=True, status="uploaded", data={"path": attachment.relative_path}),
        "pdf-uploaded",
    )


def format_pdf_attach_error(error: Exception) -> str:
    if isinstance(error, ToolRuntimeError):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return "PDF file not found."
    if isinstance(error, IsADirectoryError):
        return "Path is a directory, not a PDF file."
    if isinstance(error, KeyError):
        return "PDF attach requires a path argument."
    return f"PDF attach failed: {error}"


def is_pdf_attach_timeout(error: Exception) -> bool:
    return isinstance(error, TimeoutError) or "timed out" in str(error).lower()
