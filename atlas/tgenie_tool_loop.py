from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from atlas.fake_loop import format_tool_batch_result, format_tool_result
from atlas.json_fences import format_json_fence
from atlas.tool_protocol import ToolBatch, ToolCallError, parse_tool_call
from atlas.tool_catalog import ATTACH_TOOL_NAMES, READ_ONLY_BATCH_TOOL_NAMES, SUPPORTED_TOOL_NAMES
from atlas.tool_loop_events import ToolLoopEvent
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
    events: tuple[ToolLoopEvent, ...] = ()
    error: ToolCallError | None = None


async def run_tgenie_tool_loop(
    *,
    initial_prompt: str,
    conversation: TgenieToolConversation,
    tool_runtime: ToolRuntime,
    max_tool_calls: int = 20,
) -> TgenieToolLoopResult:
    status_events = ["waiting-for-model"]
    events: list[ToolLoopEvent] = [ToolLoopEvent(kind="user_prompt", message=initial_prompt)]
    model_response = await conversation.send_single_turn(initial_prompt)
    tool_call_count = 0

    while True:
        status_events.append("parsing-tool-call")
        try:
            parsed = parse_tool_call(
                model_response,
                available_tools=SUPPORTED_TOOL_NAMES,
                batch_tools=READ_ONLY_BATCH_TOOL_NAMES,
            )
        except ValueError:
            status_events.append("final-response")
            events.append(ToolLoopEvent(kind="assistant_final", message=model_response))
            return TgenieToolLoopResult(
                final_response=model_response,
                status_events=status_events,
                events=tuple(events),
            )

        if isinstance(parsed, ToolCallError):
            events.append(
                ToolLoopEvent(
                    kind="tool_call_error",
                    message=model_response,
                    error_code=parsed.code,
                    error_message=parsed.message,
                )
            )
            status_events.append("tool-call-error")
            status_events.append("sending-tool-error")
            status_events.append("waiting-for-model")
            model_response = await conversation.send_followup(format_tool_call_error(parsed))
            continue

        if isinstance(parsed, ToolBatch):
            events.append(
                ToolLoopEvent(
                    kind="assistant_tool_batch",
                    message=model_response,
                    tool="atlas.tool_batch",
                    args={"calls": [_batch_call_to_dict(call) for call in parsed.calls]},
                )
            )
            if tool_call_count + len(parsed.calls) > max_tool_calls:
                status_events.append("tool-loop-limit")
                return TgenieToolLoopResult(
                    final_response=None,
                    status_events=status_events,
                    events=tuple(events),
                    error=ToolCallError(
                        code="tool-loop-limit",
                        message="Atlas stopped because the model requested too many tool calls in one turn.",
                    ),
                )
            tool_call_count += len(parsed.calls)

            status_events.append("executing-tool-batch")
            batch_results = []
            for call in parsed.calls:
                tool_result = tool_runtime.run(call.tool, call.args).to_dict()
                batch_results.append({"id": call.id, "tool": call.tool, "result": tool_result})
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
            model_response = await conversation.send_followup(tool_result_message)
            continue

        events.append(
            ToolLoopEvent(
                kind="assistant_tool_call",
                message=model_response,
                tool=parsed.tool,
                args=dict(parsed.args),
            )
        )
        if tool_call_count >= max_tool_calls:
            status_events.append("tool-loop-limit")
            return TgenieToolLoopResult(
                final_response=None,
                status_events=status_events,
                events=tuple(events),
                error=ToolCallError(
                    code="tool-loop-limit",
                    message="Atlas stopped because the model requested too many tool calls in one turn.",
                ),
            )
        tool_call_count += 1

        if parsed.tool in ATTACH_TOOL_NAMES:
            status_events.append("uploading-attachment")
            tool_result, status_event = await execute_file_attach(
                conversation=conversation,
                tool_runtime=tool_runtime,
                args=parsed.args,
            )
            status_events.append(status_event)
        else:
            status_events.append("executing-tool")
            tool_result = tool_runtime.run(parsed.tool, parsed.args)
        status_events.append("sending-tool-result")
        tool_result_dict = tool_result.to_dict()
        tool_result_message = format_tool_result(parsed, tool_result_dict)
        events.append(
            ToolLoopEvent(
                kind="tool_result",
                message=tool_result_message,
                tool=parsed.tool,
                result=dict(tool_result_dict),
            )
        )
        status_events.append("waiting-for-model")
        model_response = await conversation.send_followup(tool_result_message)


def _batch_call_to_dict(call: Any) -> dict[str, Any]:
    return {"id": call.id, "tool": call.tool, "args": dict(call.args)}


def format_tool_call_error(error: ToolCallError) -> str:
    payload = {
        "type": "atlas.tool_call_error",
        "code": error.code,
        "message": error.message,
        "instruction": "Send one corrected atlas.tool_call or atlas.tool_batch fenced JSON block.",
    }
    return format_json_fence(payload)


async def execute_file_attach(
    *,
    conversation: TgenieToolConversation,
    tool_runtime: ToolRuntime,
    args: dict[str, Any],
) -> tuple[ToolResult, str]:
    try:
        attachment = tool_runtime.prepare_file_attachment(args)
        await conversation.attach_file(attachment.path)
    except Exception as error:
        timed_out = is_attach_timeout(error)
        return (
            ToolResult(
                ok=False,
                status="timeout" if timed_out else "error",
                error=format_attach_error(error),
            ),
            format_attach_status_event(timed_out=timed_out),
        )

    return (
        ToolResult(ok=True, status="uploaded", data={"path": attachment.relative_path}),
        "attachment-uploaded",
    )


def format_attach_status_event(*, timed_out: bool) -> str:
    return "attachment-upload-timeout" if timed_out else "attachment-upload-failed"


def format_attach_error(error: Exception) -> str:
    if isinstance(error, ToolRuntimeError):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return "Attachment file not found."
    if isinstance(error, IsADirectoryError):
        return "Path is a directory, not an attachable file."
    if isinstance(error, KeyError):
        return "file.attach requires a path argument."
    return f"Attachment failed: {error}"


def is_attach_timeout(error: Exception) -> bool:
    return isinstance(error, TimeoutError) or "timed out" in str(error).lower()
