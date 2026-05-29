from __future__ import annotations

from dataclasses import dataclass

from atlas.skills import Skill, SkillLoader, SkillNotFound
from atlas.wiki import initialize_wiki


BUILTIN_COMMANDS_MESSAGE = (
    "Available commands: /help for help, /exit to quit Atlas, "
    "/fa-stem brief <workspace-relative-folder> for single-image FA STEM reports."
)


@dataclass(frozen=True)
class SlashCommandResult:
    action: str
    message: str
    injected_message: str | None = None
    argument: str | None = None


def handle_slash_command(
    raw_command: str,
    skill_loader: SkillLoader | None = None,
) -> SlashCommandResult:
    command = raw_command.strip()
    if command == "/help":
        skill_commands = ""
        if skill_loader is not None:
            names = skill_loader.list_names()
            if names:
                skill_commands = " Skills: " + ", ".join(f"/{name}" for name in names) + "."
        return SlashCommandResult(
            action="message",
            message=BUILTIN_COMMANDS_MESSAGE + skill_commands,
        )
    if command == "/exit":
        return SlashCommandResult(action="exit", message="Exiting Atlas.")
    if command == "/fa-stem brief":
        return SlashCommandResult(
            action="message",
            message="Usage: /fa-stem brief <workspace-relative-folder>",
        )
    if command.startswith("/fa-stem brief "):
        argument = command.removeprefix("/fa-stem brief ").strip()
        if not argument:
            return SlashCommandResult(
                action="message",
                message="Usage: /fa-stem brief <workspace-relative-folder>",
            )
        return SlashCommandResult(
            action="fa-stem-brief",
            message=f"Starting FA STEM brief: {argument}",
            argument=argument,
        )
    if command.startswith("/llm-wiki ingest "):
        argument = command.removeprefix("/llm-wiki ingest ").strip()
        if not argument:
            return SlashCommandResult(
                action="message",
                message="Usage: /llm-wiki ingest <workspace-pdf-or-directory>",
            )
        return SlashCommandResult(
            action="llm-wiki-ingest",
            message=f"Starting LLM Wiki ingestion: {argument}",
            argument=argument,
        )
    if skill_loader is not None and command.startswith("/"):
        skill_name = command.removeprefix("/")
        try:
            skill = skill_loader.load(skill_name)
        except SkillNotFound:
            return SlashCommandResult(
                action="message",
                message=f"Unknown skill: {skill_name}. Type /help to see available commands.",
            )
        message = f"Loaded skill: {skill.name}"
        if skill.name == "llm-wiki":
            initialize_wiki(skill_loader.workspace)
            message = f"Initialized LLM Wiki; loaded skill: {skill.name}"
        return SlashCommandResult(
            action="inject-skill",
            message=message,
            injected_message=format_skill_instructions(skill),
        )
    return SlashCommandResult(
        action="message",
        message=f"Unknown command: {command}. Type /help to see available commands.",
    )


def format_skill_instructions(skill: Skill) -> str:
    return (
        f'<atlas.skill_instructions name="{skill.name}">\n'
        f"{skill.instructions}\n"
        "</atlas.skill_instructions>"
    )
