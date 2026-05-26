from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommandResult:
    action: str
    message: str


def handle_slash_command(raw_command: str) -> SlashCommandResult:
    command = raw_command.strip()
    if command == "/help":
        return SlashCommandResult(
            action="message",
            message="可用命令：/help 顯示說明、/exit 結束 Atlas。",
        )
    if command == "/exit":
        return SlashCommandResult(action="exit", message="正在結束 Atlas。")
    return SlashCommandResult(
        action="message",
        message=f"未知命令：{command}。輸入 /help 查看可用命令。",
    )
