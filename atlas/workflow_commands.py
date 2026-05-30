from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowCommand:
    prefix: str
    action: str
    label: str
    usage: str
    description: str


WORKFLOW_COMMANDS = (
    WorkflowCommand(
        prefix="/fa-stem brief",
        action="fa-stem-brief",
        label="FA STEM brief",
        usage="/fa-stem brief <workspace-relative-folder>",
        description="FA STEM brief folder-level first-pass triage",
    ),
    WorkflowCommand(
        prefix="/llm-wiki ingest",
        action="llm-wiki-ingest",
        label="LLM Wiki ingestion",
        usage="/llm-wiki ingest <workspace-pdf-or-directory>",
        description="LLM Wiki ingestion",
    ),
)


def workflow_slash_options() -> list[str]:
    return [command.prefix for command in WORKFLOW_COMMANDS]


def workflow_command_help() -> str:
    return ", ".join(f"{command.usage} for {command.description}" for command in WORKFLOW_COMMANDS)


def find_workflow_command(command: str) -> WorkflowCommand | None:
    for workflow_command in WORKFLOW_COMMANDS:
        if command == workflow_command.prefix or command.startswith(workflow_command.prefix + " "):
            return workflow_command
    return None
