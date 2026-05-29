from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from atlas.commands import handle_slash_command
from atlas.fa_stem import FaStemBriefError, run_fa_stem_brief
from atlas.fake_loop import FakeTgenieAdapter, run_fake_tool_loop
from atlas.llm_wiki_ingest import LlmWikiIngestError, run_llm_wiki_ingest
from atlas.prompt_history import PromptHistory
from atlas.skills import SkillLoader
from atlas.tgenie_adapter import (
    TgenieConversationAdapter,
    TgenieConversationClient,
    TgenieConversationError,
)
from atlas.tgenie_setup import AtlasConfigStore, TgenieBrowserLaunchError, TgenieBrowserLauncher
from atlas.tgenie_tool_loop import run_tgenie_tool_loop
from atlas.tool_runtime import ToolRuntime
from atlas.workspace_paths import WorkspacePathError, resolve_workspace_path, workspace_relative_path


STATUS_MESSAGES = {
    "validating-ingest-path": "Working: Validating ingestion path",
    "starting-ingest-batch": "Working: Starting ingestion batch",
    "ingest-batch-completed": "Working: Ingestion batch completed",
    "ingest-batch-failed": "Working: Ingestion batch failed",
    "rendering-html": "Working: Rendering HTML mirror",
    "rendering-graph": "Working: Rendering graph",
    "selecting-fa-stem-image": "Working: Selecting STEM images",
    "parsing-fa-stem-response": "Working: Parsing FA STEM response",
    "writing-fa-stem-report": "Working: Writing FA STEM report",
    "waiting-for-model": "Working: Waiting for model",
    "parsing-tool-call": "Working: Parsing tool call",
    "executing-tool": "Working: Executing tool",
    "sending-tool-result": "Working: Sending tool result",
    "uploading-attachment": "Working: Uploading attachment",
    "attachment-uploaded": "Working: Attachment uploaded",
    "attachment-upload-failed": "Working: Attachment upload failed",
    "attachment-upload-timeout": "Working: Attachment upload timed out",
    "uploading-pdf": "Working: Uploading PDF",
    "pdf-uploaded": "Working: PDF uploaded",
    "pdf-upload-failed": "Working: PDF upload failed",
    "pdf-upload-timeout": "Working: PDF upload timed out",
    "final-response": "Working: Final response",
    "tool-call-error": "Working: Tool call error",
    "sending-tool-error": "Working: Sending tool error",
    "error": "Working: Tool call error",
}
BASE_SLASH_OPTIONS = ["/help", "/exit"]


class PromptInput(Input):
    @property
    def _cursor_offset(self) -> int:
        # Keep terminal IME preedit text at the insertion point, not after Textual's soft cursor cell.
        return self._position_to_cell(self.cursor_position)


class AtlasApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #090909;
        color: #ffffff;
    }

    #header {
        height: 3;
        padding: 1 3;
        background: #141414;
        color: #ffffff;
    }

    #messages {
        height: 1fr;
        padding: 1 3;
        border: none;
        background: #090909;
        color: #ffffff;
    }

    #messages:focus {
        background-tint: transparent;
    }

    #slash-suggestions {
        height: auto;
        padding: 1 3;
        background: #141414;
        color: #999999;
    }

    .hidden {
        display: none;
    }

    #prompt {
        height: 3;
        padding: 1 3;
        border: none;
        background: #141414;
        color: #ffffff;
    }

    #prompt:focus {
        border: none;
        background-tint: transparent;
    }

    #prompt > .input--cursor {
        background: transparent;
        color: #ffffff;
        text-style: underline;
    }
    """

    def __init__(
        self,
        workspace: Path,
        fake_adapter: FakeTgenieAdapter | None = None,
        tgenie_adapter: TgenieConversationClient | None = None,
        tgenie_config_store: AtlasConfigStore | None = None,
        tgenie_browser_launcher: TgenieBrowserLauncher | None = None,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.fake_adapter = fake_adapter
        self.tgenie_adapter = tgenie_adapter
        self.tgenie_config_store = tgenie_config_store
        self.tgenie_browser_launcher = tgenie_browser_launcher
        self._tgenie_login_session: object | None = None
        self._awaiting_tgenie_url = False
        self._awaiting_tgenie_login = False
        self._pending_fa_stem_folder: Path | None = None
        self.slash_options: list[str] = []
        self.selected_slash_index = 0
        self._transcript_group: str | None = None
        self._prompt_history = PromptHistory()

    def compose(self) -> ComposeResult:
        yield Static(f"Atlas  |  Workspace: {self.workspace}", id="header")
        messages = RichLog(id="messages", wrap=True)
        messages.can_focus = False
        yield messages
        yield Static("", id="slash-suggestions", classes="hidden")
        yield PromptInput(
            placeholder="",
            id="prompt",
            select_on_focus=False,
        )

    def _write_transcript(self, renderable: object, group: str | None = None) -> None:
        messages = self.query_one("#messages", RichLog)
        if group is not None and group != self._transcript_group:
            rule_width = self._transcript_rule_width()
            rule = Text("─" * rule_width, style="#262626")
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
            ("› ", "bold #0099ff"),
            ("You", "bold #0099ff"),
            ("  ", "#999999"),
            (prompt, "bold #ffffff"),
        )

    def _resolve_workspace_folder(self, raw_path: str) -> Path:
        try:
            resolved = resolve_workspace_path(self.workspace, raw_path)
        except WorkspacePathError as error:
            raise ValueError(str(error)) from error
        if not resolved.exists():
            raise ValueError("Folder not found.")
        if not resolved.is_dir():
            raise ValueError("Path is not a folder.")
        return resolved

    async def on_mount(self) -> None:
        self._write_agent_output("Atlas: Ready.")
        await self._start_tgenie_setup_if_needed()
        self.query_one("#prompt", Input).focus()

    async def _start_tgenie_setup_if_needed(self) -> None:
        if self.tgenie_config_store is None:
            return
        config = self.tgenie_config_store.load()
        if config.tgenie_url is None:
            self._awaiting_tgenie_url = True
            self._write_agent_output("Atlas: tGenie URL is not configured. Paste the tGenie URL to continue.")
            return
        self._write_agent_output("Atlas: Using saved tGenie URL.")
        await self._open_tgenie_login(config.tgenie_url)

    async def _open_tgenie_login(self, url: str) -> None:
        if self.tgenie_config_store is None or self.tgenie_browser_launcher is None:
            return
        self._write_agent_output("Atlas: Opening tGenie in system Chrome.")
        try:
            self._tgenie_login_session = await self.tgenie_browser_launcher.open_login_browser(
                url=url,
                profile_dir=self.tgenie_config_store.chrome_profile_dir,
            )
        except TgenieBrowserLaunchError as error:
            self._write_agent_output(f"Error: {error}")
            return
        self._awaiting_tgenie_login = True
        self._write_agent_output("Atlas: Complete login in Chrome, then type /login-done.")

    def _prepare_tgenie_adapter(self) -> None:
        if self.tgenie_adapter is not None or self._tgenie_login_session is None:
            return
        page = getattr(self._tgenie_login_session, "page", None)
        if page is not None:
            self.tgenie_adapter = TgenieConversationAdapter(page=page)

    def _available_slash_options(self, value: str = "/") -> list[str]:
        skill_options = [f"/{name}" for name in SkillLoader(self.workspace).list_names()]
        options = [*BASE_SLASH_OPTIONS, *skill_options, "/fa-stem brief"]
        if self._awaiting_tgenie_login:
            options.append("/login-done")
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
                lines.append("› ", style="bold #0099ff on #1c1c1c")
                lines.append(option, style="bold #ffffff on #1c1c1c")
            else:
                lines.append("  ")
                lines.append(option, style="#999999")
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

    def _remember_prompt(self, prompt: str) -> None:
        self._prompt_history.remember(prompt)

    def _restore_prompt_history(self, direction: int) -> None:
        prompt = self.query_one("#prompt", Input)
        value = self._prompt_history.move(direction)
        if value is not None:
            self._set_prompt_value(prompt, value)

    def _set_prompt_value(self, prompt: Input, value: str) -> None:
        if prompt.value != value:
            self._prompt_history.record_programmatic_change()
            prompt.value = value
        prompt.cursor_position = len(value)

    def on_key(self, event: events.Key) -> None:
        prompt = self.query_one("#prompt", Input)
        if self.focused is prompt and self.slash_options and event.key in {"up", "down"}:
            direction = -1 if event.key == "up" else 1
            self.selected_slash_index = (self.selected_slash_index + direction) % len(self.slash_options)
            self._render_slash_suggestions()
            event.prevent_default()
            event.stop()
            return

        if self.focused is prompt and event.key == "shift+enter":
            prompt.insert_text_at_cursor("\n")
            self._prompt_history.reset_browse()
            event.prevent_default()
            event.stop()
            return

        if (
            self.focused is prompt
            and event.key in {"up", "down"}
            and self._prompt_history.should_restore(prompt.value)
        ):
            direction = -1 if event.key == "up" else 1
            self._restore_prompt_history(direction)
            event.prevent_default()
            event.stop()
            return

        if self.focused is prompt or event.character is None or not event.is_printable:
            return

        self.set_focus(prompt)
        self._prompt_history.reset_browse()
        prompt.insert_text_at_cursor(event.character)
        event.prevent_default()
        event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._prompt_history.handle_input_changed()
        self._update_slash_suggestions(event.value.strip())

    async def on_input_submitted(self, event: Input.Submitted) -> None:
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

        self._remember_prompt(prompt)

        if self._awaiting_tgenie_login and prompt == "/login-done":
            self._awaiting_tgenie_login = False
            self._prepare_tgenie_adapter()
            self._write_agent_output("Atlas: tGenie login confirmed. You can continue in Atlas.")
            return

        if self._awaiting_tgenie_login:
            self._write_agent_output("Atlas: Complete login in Chrome, then type /login-done before sending prompts.")
            return

        if self._pending_fa_stem_folder is not None:
            case_folder = self._pending_fa_stem_folder
            self._pending_fa_stem_folder = None
            self._write_transcript(self._format_user_prompt(prompt), group="user")
            if self.tgenie_adapter is None:
                self._write_agent_output("Error: /fa-stem brief requires tGenie login.")
                return
            try:
                brief_result = await run_fa_stem_brief(
                    workspace=self.workspace,
                    case_folder=case_folder,
                    case_background=prompt,
                    conversation=self.tgenie_adapter,
                )
            except FaStemBriefError as error:
                self._write_agent_output(f"Error: {error}")
                return
            for status_event in brief_result.status_events:
                status_message = STATUS_MESSAGES.get(status_event, f"Status: {status_event}")
                self._write_transcript(status_message)
            report_path = workspace_relative_path(self.workspace, brief_result.report_path)
            self._write_agent_output(f"Atlas: FA STEM brief report written: {report_path}")
            return

        if prompt.startswith("/"):
            result = handle_slash_command(prompt, skill_loader=SkillLoader(self.workspace))
            self._write_agent_output(f"Atlas: {result.message}")
            if result.action == "fa-stem-brief":
                if self.tgenie_adapter is None:
                    self._write_agent_output("Error: /fa-stem brief requires tGenie login.")
                    return
                try:
                    self._pending_fa_stem_folder = self._resolve_workspace_folder(result.argument or "")
                except ValueError as error:
                    self._write_agent_output(f"Error: {error}")
                    return
                self._write_agent_output("Atlas: Paste the FA STEM case background to start analysis.")
                return
            if result.action == "llm-wiki-ingest":
                if self.tgenie_adapter is None:
                    self._write_agent_output("Error: /llm-wiki ingest requires tGenie login.")
                    return
                try:
                    ingest_result = await run_llm_wiki_ingest(
                        workspace=self.workspace,
                        requested_path=result.argument or "",
                        conversation=self.tgenie_adapter,
                    )
                except LlmWikiIngestError as error:
                    self._write_agent_output(f"Error: {error}")
                    return
                for status_event in ingest_result.status_events:
                    status_message = STATUS_MESSAGES.get(status_event, f"Status: {status_event}")
                    self._write_transcript(status_message)
                if ingest_result.error is not None:
                    self._write_agent_output(f"Error: {ingest_result.error}")
                if ingest_result.final_response is not None:
                    self._write_agent_output(f"Atlas: {ingest_result.final_response}")
                return
            if result.action == "inject-skill" and result.injected_message is not None:
                if self.fake_adapter is not None:
                    self.fake_adapter.inject(result.injected_message)
            if result.action == "exit":
                self.exit()
            return

        if self._awaiting_tgenie_url:
            try:
                self.tgenie_config_store.save_tgenie_url(prompt)
            except ValueError as error:
                self._write_agent_output(f"Error: {error}")
                return
            self._awaiting_tgenie_url = False
            self._write_agent_output("Atlas: tGenie URL saved.")
            await self._open_tgenie_login(prompt)
            return

        self._write_transcript(self._format_user_prompt(prompt), group="user")
        if self.tgenie_adapter is not None:
            try:
                result = await run_tgenie_tool_loop(
                    initial_prompt=prompt,
                    conversation=self.tgenie_adapter,
                    tool_runtime=ToolRuntime(self.workspace),
                )
            except TgenieConversationError as error:
                self._write_agent_output(f"Error: {error}")
                return
            for status_event in result.status_events:
                status_message = STATUS_MESSAGES.get(status_event, f"Status: {status_event}")
                self._write_transcript(status_message)
            if result.error is not None:
                self._write_agent_output(f"Error: {result.error.message}")
            if result.final_response is not None:
                self._write_agent_output(f"Atlas: {result.final_response}")
            return

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
