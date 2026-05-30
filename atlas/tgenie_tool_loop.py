from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from atlas.fake_loop import format_tool_result
from atlas.json_fences import format_json_fence
from atlas.tool_protocol import ToolCallError, parse_tool_call
from atlas.tool_catalog import ATTACH_TOOL_NAMES, SUPPORTED_TOOL_NAMES
from atlas.tool_runtime import ToolResult, ToolRuntime, ToolRuntimeError


class TgenieToolConversation(Protocol):
    async def send_single_turn(self, user_prompt: str) -> str:
        pass

    async def send_followup(self, message: str) -> str:
        pass

    async def attach_file(self, path: Path) -> None:
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
    max_tool_calls: int = 20,
) -> TgenieToolLoopResult:
    status_events = ["waiting-for-model"]
    model_response = await conversation.send_single_turn(initial_prompt)
    tool_call_count = 0

    while True:
        status_events.append("parsing-tool-call")
        try:
            parsed = parse_tool_call(model_response, available_tools=SUPPORTED_TOOL_NAMES)
        except ValueError:
            status_events.append("final-response")
            return TgenieToolLoopResult(final_response=model_response, status_events=status_events)

        if isinstance(parsed, ToolCallError):
            status_events.append("tool-call-error")
            status_events.append("sending-tool-error")
            status_events.append("waiting-for-model")
            model_response = await conversation.send_followup(format_tool_call_error(parsed))
            continue

        if tool_call_count >= max_tool_calls:
            status_events.append("tool-loop-limit")
            return TgenieToolLoopResult(
                final_response=None,
                status_events=status_events,
                error=ToolCallError(
                    code="tool-loop-limit",
                    message="Atlas stopped because the model requested too many tool calls in one turn.",
                ),
            )
        tool_call_count += 1

        if parsed.tool in ATTACH_TOOL_NAMES:
            status_events.append(
                "uploading-pdf" if parsed.tool == "pdf.attach" else "uploading-attachment"
            )
            tool_result, status_event = await execute_file_attach(
                conversation=conversation,
                tool_runtime=tool_runtime,
                args=parsed.args,
                tool_name=parsed.tool,
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
    return format_json_fence(payload)


async def execute_file_attach(
    *,
    conversation: TgenieToolConversation,
    tool_runtime: ToolRuntime,
    args: dict[str, Any],
    tool_name: str,
) -> tuple[ToolResult, str]:
    pdf_only = tool_name == "pdf.attach"
    try:
        attachment = (
            tool_runtime.prepare_pdf_attachment(args)
            if pdf_only
            else tool_runtime.prepare_file_attachment(args)
        )
        await conversation.attach_file(attachment.path)
    except Exception as error:
        timed_out = is_attach_timeout(error)
        return (
            ToolResult(
                ok=False,
                status="timeout" if timed_out else "error",
                error=format_attach_error(error, pdf_only=pdf_only),
            ),
            format_attach_status_event(pdf_only=pdf_only, timed_out=timed_out),
        )

    return (
        ToolResult(ok=True, status="uploaded", data={"path": attachment.relative_path}),
        "pdf-uploaded" if pdf_only else "attachment-uploaded",
    )


def format_attach_status_event(*, pdf_only: bool, timed_out: bool) -> str:
    if pdf_only:
        return "pdf-upload-timeout" if timed_out else "pdf-upload-failed"
    return "attachment-upload-timeout" if timed_out else "attachment-upload-failed"


def format_attach_error(error: Exception, *, pdf_only: bool) -> str:
    if isinstance(error, ToolRuntimeError):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return "PDF file not found." if pdf_only else "Attachment file not found."
    if isinstance(error, IsADirectoryError):
        if pdf_only:
            return "Path is a directory, not a PDF file."
        return "Path is a directory, not an attachable file."
    if isinstance(error, KeyError):
        if pdf_only:
            return "pdf.attach requires a path argument."
        return "file.attach requires a path argument."
    return f"{'PDF attach' if pdf_only else 'Attachment'} failed: {error}"


def is_attach_timeout(error: Exception) -> bool:
    return isinstance(error, TimeoutError) or "timed out" in str(error).lower()
