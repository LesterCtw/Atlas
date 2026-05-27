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
    "waiting-for-model": "Working: Waiting for model",
    "parsing-tool-call": "Working: Parsing tool call",
    "executing-tool": "Working: Executing tool",
    "final-response": "Working: Final response",
    "error": "Working: Tool call error",
}
BASE_SLASH_OPTIONS = ["/help", "/exit"]


class AtlasApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #0b0f14;
        color: #d6deeb;
    }

    #header {
        height: 3;
        padding: 1 3;
        background: #111820;
        color: #d6deeb;
    }

    #messages {
        height: 1fr;
        padding: 1 3;
        border: none;
        background: #090d13;
        color: #d6deeb;
    }

    #messages:focus {
        background-tint: transparent;
    }

    #slash-suggestions {
        height: auto;
        padding: 1 3;
        background: #101923;
        color: #8fa3b8;
    }

    .hidden {
        display: none;
    }

    #prompt {
        height: 3;
        padding: 1 3;
        border: none;
        background: #0f151d;
        color: #e6edf3;
    }

    #prompt:focus {
        border: none;
        background-tint: transparent;
    }

    #prompt > .input--cursor {
        background: transparent;
        color: #e6edf3;
        text-style: underline;
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
        self.slash_options: list[str] = []
        self.selected_slash_index = 0
        self._transcript_group: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(f"Atlas  |  Workspace: {self.workspace}", id="header")
        messages = RichLog(id="messages", wrap=True)
        messages.can_focus = False
        yield messages
        yield Static("", id="slash-suggestions", classes="hidden")
        yield Input(
            placeholder="",
            id="prompt",
            select_on_focus=False,
        )

    def _write_transcript(self, renderable: object, group: str | None = None) -> None:
        messages = self.query_one("#messages", RichLog)
        if group is not None and group != self._transcript_group:
            rule_width = self._transcript_rule_width()
            rule = Text("─" * rule_width, style="#243244")
            messages.write(rule, width=rule_width)
            self._transcript_group = group
        messages.write(renderable)

    def _transcript_rule_width(self) -> int:
        messages = self.query_one("#messages", RichLog)
        padding = messages.styles.padding
        fallback_width = self.size.width - padding.left - padding.right - 2
        return max(1, messages.scrollable_content_region.width or fallback_width)

    def _write_agent_output(self, renderable: object) -> None:
        self._write_transcript(renderable, group="atlas")

    def _format_user_prompt(self, prompt: str) -> Text:
        return Text.assemble(
            ("› ", "bold #7dd3fc"),
            ("You", "bold #7dd3fc"),
            ("  ", "#8fa3b8"),
            (prompt, "bold #f8fafc"),
        )

    def on_mount(self) -> None:
        self._write_agent_output("Atlas: Ready.")
        self.query_one("#prompt", Input).focus()

    def _available_slash_options(self, value: str = "/") -> list[str]:
        skill_options = [f"/{name}" for name in SkillLoader(self.workspace).list_names()]
        options = [*BASE_SLASH_OPTIONS, *skill_options]
        if value == "/":
            return options
        filtered_options = [option for option in options if option.startswith(value)]
        return filtered_options

    def _render_slash_suggestions(self) -> None:
        suggestions = self.query_one("#slash-suggestions", Static)
        if not self.slash_options:
            suggestions.add_class("hidden")
            suggestions.update("")
            return

        suggestions.remove_class("hidden")
        lines = Text()
        for index, option in enumerate(self.slash_options):
            if index:
                lines.append("\n")
            if index == self.selected_slash_index:
                lines.append("› ", style="bold #7dd3fc")
                lines.append(option, style="bold #020617 on #7dd3fc")
            else:
                lines.append("  ")
                lines.append(option, style="#8fa3b8")
        suggestions.update(lines)

    def _update_slash_suggestions(self, value: str) -> None:
        if not value.startswith("/"):
            self.slash_options = []
            self.selected_slash_index = 0
            self._render_slash_suggestions()
            return

        self.slash_options = self._available_slash_options(value)
        self.selected_slash_index = min(self.selected_slash_index, len(self.slash_options) - 1)
        self._render_slash_suggestions()

    def _selected_slash_option(self) -> str | None:
        if not self.slash_options:
            return None
        return self.slash_options[self.selected_slash_index]

    def on_key(self, event: events.Key) -> None:
        prompt = self.query_one("#prompt", Input)
        if self.focused is prompt and self.slash_options and event.key in {"up", "down"}:
            direction = -1 if event.key == "up" else 1
            self.selected_slash_index = (self.selected_slash_index + direction) % len(self.slash_options)
            self._render_slash_suggestions()
            event.prevent_default()
            event.stop()
            return

        if self.focused is prompt or event.character is None or not event.is_printable:
            return

        self.set_focus(prompt)
        prompt.insert_text_at_cursor(event.character)
        event.prevent_default()
        event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_slash_suggestions(event.value.strip())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        selected_command = self._selected_slash_option()
        if prompt.startswith("/") and selected_command is not None:
            prompt = selected_command
        self.slash_options = []
        self.selected_slash_index = 0
        self._render_slash_suggestions()
        event.input.clear()
        if not prompt:
            return

        if prompt.startswith("/"):
            result = handle_slash_command(prompt, skill_loader=SkillLoader(self.workspace))
            self._write_agent_output(f"Atlas: {result.message}")
            if result.action == "inject-skill" and result.injected_message is not None:
                if self.fake_adapter is not None:
                    self.fake_adapter.inject(result.injected_message)
            if result.action == "exit":
                self.exit()
            return

        self._write_transcript(self._format_user_prompt(prompt), group="user")
        if self.fake_adapter is None:
            return

        result = run_fake_tool_loop(
            initial_prompt=prompt,
            adapter=self.fake_adapter,
            tools={"echo": lambda args: {"text": args.get("text", "")}},
        )
        for status_event in result.status_events:
            status_message = STATUS_MESSAGES.get(status_event, f"Status: {status_event}")
            self._write_transcript(status_message)
        if result.error is not None:
            self._write_agent_output(f"Error: {result.error.message}")
        if result.final_response is not None:
            self._write_agent_output(f"Atlas: {result.final_response}")
