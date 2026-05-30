from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ToolLoopEventKind = Literal[
    "user_prompt",
    "assistant_tool_call",
    "assistant_tool_batch",
    "tool_result",
    "tool_batch_result",
    "tool_call_error",
    "assistant_final",
]


@dataclass(frozen=True)
class ToolLoopEvent:
    kind: ToolLoopEventKind
    message: str
    tool: str | None = None
    args: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
