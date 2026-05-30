from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.geometry import Offset, Size
from textual.strip import Strip
from textual.widgets import Input, RichLog, Static

from atlas.commands import handle_slash_command
from atlas.fa_stem import FaStemBriefError, run_fa_stem_brief
from atlas.fake_loop import FakeTgenieAdapter, run_fake_tool_loop
from atlas.llm_wiki_ingest import LlmWikiIngestError, run_llm_wiki_ingest
from atlas.prompt_history import PromptHistory
from atlas.skills import SkillLoader
from atlas.slash_suggestions import SlashSuggestionState
from atlas.tgenie_adapter import (
    TgenieConversationAdapter,
    TgenieConversationClient,
    TgenieConversationError,
    check_tgenie_chat_readiness,
    format_tgenie_readiness_issue,
)
from atlas.tgenie_setup import AtlasConfigStore, TgenieBrowserLaunchError, TgenieBrowserLauncher
from atlas.tgenie_tool_loop import run_tgenie_tool_loop
from atlas.tool_runtime import ToolRuntime
from atlas.workspace_paths import WorkspacePathError, resolve_workspace_path, workspace_relative_path
from atlas.workflow_commands import workflow_slash_options


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
    "tool-loop-limit": "Working: Tool loop limit reached",
    "error": "Working: Tool call error",
}
BASE_SLASH_OPTIONS = ["/help", "/exit"]
PROMPT_MAX_CONTENT_HEIGHT = 5
SLASH_SUGGESTION_MAX_VISIBLE = 6


class PromptInput(Input):
    BINDINGS = (
        *Input.BINDINGS,
        Binding("shift+enter", "insert_newline", show=False, priority=True),
    )

    @property
    def _cursor_offset(self) -> int:
        # Keep terminal IME preedit text at the insertion point, not after Textual's soft cursor cell.
        return self._position_to_cell(self.cursor_position)

    def action_insert_newline(self) -> None:
        self.insert_text_at_cursor("\n")

    def _watch_value(self, value: str) -> None:
        super()._watch_value(value)
        self.refresh(layout=True)

    @property
    def cursor_screen_offset(self) -> Offset:
        if not self._should_wrap_prompt():
            return super().cursor_screen_offset

        x, y, _width, _height = self.content_region
        width = self._prompt_content_width()
        cursor_line, cursor_column = self._cursor_line_and_column(width)
        visible_start = self._visible_prompt_start(width, cursor_line)
        return Offset(x + cursor_column, y + max(0, cursor_line - visible_start))

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        content_width = max(1, width)
        return min(PROMPT_MAX_CONTENT_HEIGHT, len(self._wrapped_prompt_lines(content_width)))

    def render_line(self, y: int) -> Strip:
        if not self._should_wrap_prompt():
            return super().render_line(y)

        width = self._prompt_content_width()
        cursor_line, cursor_column = self._cursor_line_and_column(width)
        visible_start = self._visible_prompt_start(width, cursor_line)
        visible_lines = self._wrapped_prompt_lines(width)[
            visible_start : visible_start + PROMPT_MAX_CONTENT_HEIGHT
        ]
        line_index = visible_start + y
        line = visible_lines[y] if y < len(visible_lines) else ""
        text = Text(line, end="")

        if self.has_focus and self._cursor_visible and line_index == cursor_line:
            cursor_style = self.get_component_rich_style("input--cursor")
            cursor_index = self._character_index_for_cell_offset(line, cursor_column)
            if cursor_index >= len(text):
                text.pad_right(1)
                cursor_index = len(text) - 1
            text.stylize(cursor_style, cursor_index, cursor_index + 1)

        segments = list(self.app.console.render(text, self.app.console_options.update_width(width + 1)))
        strip = Strip(segments)
        return strip.crop(0, width + 1).extend_cell_length(width + 1).apply_style(self.rich_style)

    def _should_wrap_prompt(self) -> bool:
        return "\n" in self.value or cell_len(self.value) > self._prompt_content_width()

    def _prompt_content_width(self) -> int:
        return max(1, self.scrollable_content_region.width or self.content_region.width or self.size.width)

    def _wrapped_prompt_lines(self, width: int, value: str | None = None) -> list[str]:
        return [line for line, _start_index in self._wrapped_prompt_line_segments(width, value)]

    def _cursor_line_and_column(self, width: int) -> tuple[int, int]:
        cursor_prefix = self.value[: self.cursor_position]
        cursor_lines = self._wrapped_prompt_lines(width, cursor_prefix)
        return len(cursor_lines) - 1, cell_len(cursor_lines[-1])

    def move_cursor_vertically(self, direction: int) -> bool:
        width = self._prompt_content_width()
        segments = self._wrapped_prompt_line_segments(width)
        if len(segments) <= 1:
            return False

        cursor_line, cursor_column = self._cursor_line_and_column(width)
        target_line = cursor_line + direction
        if target_line < 0 or target_line >= len(segments):
            return False

        target_text, target_start = segments[target_line]
        target_offset = self._character_index_for_cell_offset(target_text, cursor_column)
        self.cursor_position = min(len(self.value), target_start + target_offset)
        return True

    def _wrapped_prompt_line_segments(
        self,
        width: int,
        value: str | None = None,
    ) -> list[tuple[str, int]]:
        prompt_value = self.value if value is None else value
        if not prompt_value:
            return [("", 0)]

        lines: list[tuple[str, int]] = []
        current = ""
        current_width = 0
        current_start = 0
        for index, character in enumerate(prompt_value):
            if character == "\n":
                lines.append((current, current_start))
                current = ""
                current_width = 0
                current_start = index + 1
                continue

            character_width = cell_len(character)
            if current and current_width + character_width > width:
                lines.append((current, current_start))
                current = character
                current_width = character_width
                current_start = index
            else:
                current += character
                current_width += character_width

        lines.append((current, current_start))
        return lines

    def _visible_prompt_start(self, width: int, cursor_line: int) -> int:
        line_count = len(self._wrapped_prompt_lines(width))
        if line_count <= PROMPT_MAX_CONTENT_HEIGHT:
            return 0
        return max(0, min(cursor_line - PROMPT_MAX_CONTENT_HEIGHT + 1, line_count - PROMPT_MAX_CONTENT_HEIGHT))

    def _character_index_for_cell_offset(self, text: str, cell_offset: int) -> int:
        width = 0
        for index, character in enumerate(text):
            if width >= cell_offset:
                return index
            width += cell_len(character)
        return len(text)


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
        padding: 0 3;
        border: none;
        background: #090909;
        color: #ffffff;
    }

    #messages:focus {
        background-tint: transparent;
    }

    #slash-suggestions {
        height: auto;
        padding: 0 3;
        background: #141414;
        color: #999999;
    }

    .hidden {
        display: none;
    }

    #prompt {
        height: auto;
        min-height: 3;
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
        self._last_tgenie_readiness_issue: str | None = None
        self._pending_fa_stem_folder: Path | None = None
        self._slash_suggestions = SlashSuggestionState()
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

    def _write_status_events(self, status_events: Iterable[str]) -> None:
        for status_event in status_events:
            status_message = STATUS_MESSAGES.get(status_event, f"Status: {status_event}")
            self._write_agent_output(status_message)

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
        self.call_after_refresh(self._sync_prompt_cursor_position)

    def _sync_prompt_cursor_position(self) -> None:
        prompt = self.query_one("#prompt", Input)
        if self.focused is prompt:
            self.cursor_position = prompt.cursor_screen_offset

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
        if await self._complete_tgenie_login_if_ready():
            return
        self._awaiting_tgenie_login = True
        self._write_agent_output("Atlas: Complete login in Chrome, then type /login-done.")

    def _prepare_tgenie_adapter(self) -> None:
        if self.tgenie_adapter is not None or self._tgenie_login_session is None:
            return
        page = getattr(self._tgenie_login_session, "page", None)
        if page is not None:
            self.tgenie_adapter = TgenieConversationAdapter(page=page)

    async def _complete_tgenie_login_if_ready(self) -> bool:
        if self._tgenie_login_session is None:
            return False
        page = getattr(self._tgenie_login_session, "page", None)
        if page is None:
            return False
        readiness = await check_tgenie_chat_readiness(page)
        if not readiness.ready:
            self._last_tgenie_readiness_issue = format_tgenie_readiness_issue(readiness)
            return False
        self._last_tgenie_readiness_issue = None
        self._awaiting_tgenie_login = False
        self._prepare_tgenie_adapter()
        self._write_agent_output("Atlas: tGenie is ready. You can continue in Atlas.")
        return True

    def _available_slash_options(self, value: str = "/") -> list[str]:
        skill_options = [f"/{name}" for name in SkillLoader(self.workspace).list_names()]
        options = [*BASE_SLASH_OPTIONS, *skill_options, *workflow_slash_options()]
        if self._awaiting_tgenie_login:
            options = ["/login-done", *options]
        if value == "/":
            return options
        filtered_options = [option for option in options if option.startswith(value)]
        return filtered_options

    def _render_slash_suggestions(self) -> None:
        suggestions = self.query_one("#slash-suggestions", Static)
        if not self._slash_suggestions.has_options:
            suggestions.add_class("hidden")
            suggestions.update("")
            return

        suggestions.remove_class("hidden")
        lines = Text()
        options = self._visible_slash_options()
        for index, (option_index, option) in enumerate(options):
            if index:
                lines.append("\n")
            if option_index == self._slash_suggestions.selected_index:
                lines.append("› ", style="bold #0099ff on #1c1c1c")
                lines.append(option, style="bold #ffffff on #1c1c1c")
            else:
                lines.append("  ")
                lines.append(option, style="#999999")
        suggestions.update(lines)

    def _visible_slash_options(self) -> list[tuple[int, str]]:
        options = self._slash_suggestions.options
        visible_limit = self._slash_suggestion_visible_limit()
        if len(options) <= visible_limit:
            return list(enumerate(options))

        selected_index = self._slash_suggestions.selected_index
        start = max(0, min(selected_index - visible_limit // 2, len(options) - visible_limit))
        return list(enumerate(options[start : start + visible_limit], start=start))

    def _slash_suggestion_visible_limit(self) -> int:
        header = self.query_one("#header", Static)
        prompt = self.query_one("#prompt", Input)
        reserved_height = header.region.height + max(3, prompt.region.height) + 1
        available_height = self.size.height - reserved_height
        return max(1, min(SLASH_SUGGESTION_MAX_VISIBLE, available_height))

    def _update_slash_suggestions(self, value: str) -> None:
        if not value.startswith("/"):
            self._slash_suggestions.clear()
            self._render_slash_suggestions()
            return

        options = self._available_slash_options(value)
        if len(options) == 1 and options[0] == value:
            self._slash_suggestions.clear()
            self._render_slash_suggestions()
            return

        self._slash_suggestions.update(options)
        self._render_slash_suggestions()

    def _selected_slash_option(self) -> str | None:
        return self._slash_suggestions.selected()

    def _single_slash_completion(self, value: str) -> str | None:
        prompt = value.strip()
        selected_command = self._selected_slash_option()
        if (
            prompt.startswith("/")
            and selected_command is not None
            and len(self._slash_suggestions.options) == 1
            and prompt != selected_command
        ):
            return f"{selected_command} "
        return None

    def _complete_slash_prompt(self, prompt: Input, completion: str) -> None:
        self._set_prompt_value(prompt, completion)
        self._slash_suggestions.clear()
        self._render_slash_suggestions()

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
        if self.focused is prompt and self._slash_suggestions.has_options and event.key in {"up", "down"}:
            direction = -1 if event.key == "up" else 1
            self._slash_suggestions.move_selection(direction)
            self._render_slash_suggestions()
            event.prevent_default()
            event.stop()
            return

        if self.focused is prompt and event.key == "tab":
            completion = self._single_slash_completion(prompt.value)
            if completion is not None:
                self._complete_slash_prompt(prompt, completion)
                event.prevent_default()
                event.stop()
                return

        if (
            self.focused is prompt
            and event.key in {"up", "down"}
            and isinstance(prompt, PromptInput)
            and prompt.move_cursor_vertically(-1 if event.key == "up" else 1)
        ):
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

    async def _run_model_prompt(self, transcript_prompt: str, *, model_prompt: str | None = None) -> None:
        self._write_transcript(self._format_user_prompt(transcript_prompt), group="user")
        prompt_for_model = model_prompt or transcript_prompt
        if self.tgenie_adapter is not None:
            try:
                result = await run_tgenie_tool_loop(
                    initial_prompt=prompt_for_model,
                    conversation=self.tgenie_adapter,
                    tool_runtime=ToolRuntime(self.workspace),
                )
            except TgenieConversationError as error:
                self._write_agent_output(f"Error: {error}")
                return
            self._write_status_events(result.status_events)
            if result.error is not None:
                self._write_agent_output(f"Error: {result.error.message}")
            if result.final_response is not None:
                self._write_agent_output(f"Atlas: {result.final_response}")
            return

        if self.fake_adapter is None:
            return

        result = run_fake_tool_loop(
            initial_prompt=prompt_for_model,
            adapter=self.fake_adapter,
            tools={"echo": lambda args: {"text": args.get("text", "")}},
        )
        self._write_status_events(result.status_events)
        if result.error is not None:
            self._write_agent_output(f"Error: {result.error.message}")
        if result.final_response is not None:
            self._write_agent_output(f"Atlas: {result.final_response}")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        completion = self._single_slash_completion(event.value)
        if completion is not None:
            self._complete_slash_prompt(event.input, completion)
            return

        prompt = event.value.strip()
        selected_command = self._selected_slash_option()
        if prompt.startswith("/") and selected_command is not None:
            prompt = selected_command
        self._slash_suggestions.clear()
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
            if not await self._complete_tgenie_login_if_ready():
                self._write_agent_output("Atlas: Complete login in Chrome, then type /login-done before sending prompts.")
                if self._last_tgenie_readiness_issue is not None:
                    self._write_agent_output(f"Atlas: {self._last_tgenie_readiness_issue}")
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
            self._write_status_events(brief_result.status_events)
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
                self._write_status_events(ingest_result.status_events)
                if ingest_result.error is not None:
                    self._write_agent_output(f"Error: {ingest_result.error}")
                if ingest_result.final_response is not None:
                    self._write_agent_output(f"Atlas: {ingest_result.final_response}")
                return
            if result.action == "inject-skill" and result.injected_message is not None:
                if result.argument:
                    await self._run_model_prompt(
                        result.argument,
                        model_prompt=f"{result.injected_message}\n\nUser task:\n{result.argument}",
                    )
                    return
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

        await self._run_model_prompt(prompt)
