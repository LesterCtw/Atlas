from __future__ import annotations

from dataclasses import dataclass

from atlas.skills import Skill, SkillLoader, SkillNotFound


@dataclass(frozen=True)
class SlashCommandResult:
    action: str
    message: str
    injected_message: str | None = None


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
                skill_commands = " Skills：" + "、".join(f"/{name}" for name in names) + "。"
        return SlashCommandResult(
            action="message",
            message="可用命令：/help 顯示說明、/exit 結束 Atlas。" + skill_commands,
        )
    if command == "/exit":
        return SlashCommandResult(action="exit", message="正在結束 Atlas。")
    if skill_loader is not None and command.startswith("/"):
        skill_name = command.removeprefix("/")
        try:
            skill = skill_loader.load(skill_name)
        except SkillNotFound:
            return SlashCommandResult(
                action="message",
                message=f"未知 skill：{skill_name}。輸入 /help 查看可用命令。",
            )
        return SlashCommandResult(
            action="inject-skill",
            message=f"已載入 skill：{skill.name}",
            injected_message=format_skill_instructions(skill),
        )
    return SlashCommandResult(
        action="message",
        message=f"未知命令：{command}。輸入 /help 查看可用命令。",
    )


def format_skill_instructions(skill: Skill) -> str:
    return (
        f'<atlas.skill_instructions name="{skill.name}">\n'
        f"{skill.instructions}\n"
        "</atlas.skill_instructions>"
    )
