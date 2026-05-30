from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    attach: bool = False


TOOL_DEFINITIONS = (
    ToolDefinition("file.list", "List workspace files."),
    ToolDefinition("file.read", "Read a UTF-8 workspace text file."),
    ToolDefinition("file.search", "Search workspace file names and UTF-8 text."),
    ToolDefinition("file.write", "Write a UTF-8 workspace text file."),
    ToolDefinition("shell.run", "Run a shell command through Atlas safety policy."),
    ToolDefinition("file.attach", "Attach a workspace-local PDF or image.", attach=True),
    ToolDefinition("pdf.attach", "Legacy PDF-only attachment tool.", attach=True),
)

SUPPORTED_TOOL_NAMES = frozenset(tool.name for tool in TOOL_DEFINITIONS)
ATTACH_TOOL_NAMES = frozenset(tool.name for tool in TOOL_DEFINITIONS if tool.attach)


def format_tool_names() -> str:
    return ", ".join(f"`{tool.name}`" for tool in TOOL_DEFINITIONS)
