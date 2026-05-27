from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from atlas.commands import handle_slash_command
from atlas.fake_loop import FakeTgenieAdapter, run_fake_tool_loop
from atlas.skills import SkillLoader


STATUS_MESSAGES = {
    "waiting-for-model": "Status: Waiting for model",
    "parsing-tool-call": "Status: Parsing tool call",
    "executing-tool": "Status: Executing tool",
    "final-response": "Status: Final response",
    "error": "Status: Tool call error",
}
STATUS_HINTS = "Enter Submit  |  /help Help  |  /exit Exit"


class AtlasApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #0b0f14;
        color: #d6deeb;
    }

    #header {
        height: 2;
        padding: 1 3 0 3;
        background: #111820;
        color: #d6deeb;
    }

    #messages {
        height: 1fr;
        padding: 2 3;
        border: solid #243244;
        background: #0b0f14;
        color: #d6deeb;
    }

    #messages:focus {
        background-tint: transparent;
    }

    #prompt {
        height: 5;
        padding: 1 3;
        border: tall #26364a;
        background: #0f151d;
        color: #e6edf3;
    }

    #prompt:focus {
        border: tall #26364a;
        background-tint: transparent;
    }

    #status {
        height: 2;
        padding: 0 3 1 3;
        background: #111820;
        color: #8fa3b8;
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
        yield Static(f"Atlas  |  Workspace: {self.workspace}", id="header")
        messages = RichLog(id="messages", wrap=True)
        messages.can_focus = False
        yield messages
        yield Input(
            placeholder="",
            id="prompt",
            select_on_focus=False,
        )
        yield Static(self._format_status("Status: Idle"), id="status")

    def _format_status(self, message: str) -> str:
        return f"{message}  |  {STATUS_HINTS}"

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(self._format_status(message))

    def _write_transcript(self, renderable: object) -> None:
        messages = self.query_one("#messages", RichLog)
        messages.write(renderable)
        messages.write("")

    def _format_user_prompt(self, prompt: str) -> Text:
        return Text.assemble(
            ("› ", "bold #7dd3fc"),
            ("You", "bold #020617 on #7dd3fc"),
            ("  ", "on #1e293b"),
            (prompt, "bold #f8fafc on #1e293b"),
        )

    def on_mount(self) -> None:
        self._write_transcript("Atlas: Ready.")
        self.query_one("#prompt", Input).focus()

    def on_key(self, event: events.Key) -> None:
        prompt = self.query_one("#prompt", Input)
        if self.focused is prompt or event.character is None or not event.is_printable:
            return

        self.set_focus(prompt)
        prompt.insert_text_at_cursor(event.character)
        event.prevent_default()
        event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.clear()
        if not prompt:
            return

        if prompt.startswith("/"):
            result = handle_slash_command(prompt, skill_loader=SkillLoader(self.workspace))
            self._write_transcript(f"Atlas: {result.message}")
            if result.action == "inject-skill" and result.injected_message is not None:
                if self.fake_adapter is not None:
                    self.fake_adapter.inject(result.injected_message)
            if result.action == "exit":
                self.exit()
            return

        self._write_transcript(self._format_user_prompt(prompt))
        if self.fake_adapter is None:
            return

        messages = self.query_one("#messages", RichLog)
        result = run_fake_tool_loop(
            initial_prompt=prompt,
            adapter=self.fake_adapter,
            tools={"echo": lambda args: {"text": args.get("text", "")}},
        )
        for status_event in result.status_events:
            status_message = STATUS_MESSAGES.get(status_event, f"Status: {status_event}")
            messages.write(status_message)
            messages.write("")
            self._set_status(status_message)
        if result.error is not None:
            self._set_status(STATUS_MESSAGES["error"])
            self._write_transcript(f"Error: {result.error.message}")
        if result.final_response is not None:
            self._write_transcript(f"Atlas: {result.final_response}")
