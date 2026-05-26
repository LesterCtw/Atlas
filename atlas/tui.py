from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from atlas.commands import handle_slash_command
from atlas.fake_loop import FakeTgenieAdapter, run_fake_tool_loop
from atlas.skills import SkillLoader


STATUS_MESSAGES = {
    "waiting-for-model": "狀態：等待模型回覆",
    "parsing-tool-call": "狀態：解析 tool call",
    "executing-tool": "狀態：執行 tool",
    "final-response": "狀態：收到最終回覆",
    "error": "狀態：tool call 錯誤",
}


class AtlasApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #workspace {
        padding: 0 1;
        background: $surface;
    }

    #messages {
        height: 1fr;
        border: solid $primary;
    }

    #prompt {
        dock: bottom;
    }
    """

    def __init__(
        self,
        workspace: Path,
        fake_adapter: FakeTgenieAdapter | None = None,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.fake_adapter = fake_adapter

    def compose(self) -> ComposeResult:
        yield Static(f"Workspace: {self.workspace}", id="workspace")
        yield RichLog(id="messages", wrap=True)
        yield Input(placeholder="Prompt or slash command", id="prompt")

    def on_mount(self) -> None:
        messages = self.query_one("#messages", RichLog)
        messages.write("Atlas 已啟動。")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.clear()
        if not prompt:
            return

        messages = self.query_one("#messages", RichLog)
        if prompt.startswith("/"):
            result = handle_slash_command(prompt, skill_loader=SkillLoader(self.workspace))
            messages.write(result.message)
            if result.action == "inject-skill" and result.injected_message is not None:
                if self.fake_adapter is not None:
                    self.fake_adapter.inject(result.injected_message)
            if result.action == "exit":
                self.exit()
            return

        messages.write(f"> {prompt}")
        if self.fake_adapter is None:
            return

        result = run_fake_tool_loop(
            initial_prompt=prompt,
            adapter=self.fake_adapter,
            tools={"echo": lambda args: {"text": args.get("text", "")}},
        )
        for status_event in result.status_events:
            messages.write(STATUS_MESSAGES.get(status_event, f"狀態：{status_event}"))
        if result.error is not None:
            messages.write(result.error.message)
        if result.final_response is not None:
            messages.write(result.final_response)
