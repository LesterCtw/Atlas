from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from atlas.commands import handle_slash_command


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

    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self.workspace = workspace

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
            result = handle_slash_command(prompt)
            messages.write(result.message)
            if result.action == "exit":
                self.exit()
            return

        messages.write(f"> {prompt}")
