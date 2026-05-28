from __future__ import annotations

import html
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.fake_loop import FakeTgenieAdapter
from atlas.tgenie_setup import AtlasConfigStore, TgenieBrowserLaunchError
from atlas.tui import AtlasApp
from rich.cells import cell_len
from textual.widgets import Input, RichLog, Static


class RecordingLoginBrowserLauncher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    def open_login_browser(self, url: str, profile_dir: Path) -> object:
        self.calls.append((url, profile_dir))
        return object()


class FailingLoginBrowserLauncher:
    def open_login_browser(self, url: str, profile_dir: Path) -> object:
        raise TgenieBrowserLaunchError("Could not open system Chrome. Install Google Chrome.")


def rich_log_text(log: RichLog) -> str:
    return "\n".join("".join(segment.text for segment in line) for line in log.lines)


def screenshot_text(svg: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", svg)).replace("\xa0", " ")


def is_horizontal_rule(line: str) -> bool:
    return bool(line) and set(line) == {"─"}


def rich_color_tuple(segment: object) -> tuple[int, int, int]:
    color = segment.style.color.triplet
    return (color.red, color.green, color.blue)


class AtlasTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_run_tgenie_url_is_saved_from_prompt(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                app = AtlasApp(workspace=Path(workspace_directory).resolve(), tgenie_config_store=store)

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: tGenie URL is not configured.", messages)

                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = " https://tgenie.example.test "
                    await prompt.action_submit()
                    await pilot.pause()

                self.assertEqual(store.load().tgenie_url, "https://tgenie.example.test")

    async def test_first_run_tgenie_url_opens_chrome_after_it_is_saved(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                launcher = RecordingLoginBrowserLauncher()
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=launcher,
                )

                async with app.run_test() as pilot:
                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = "https://tgenie.example.test"
                    await prompt.action_submit()
                    await pilot.pause()

                self.assertEqual(launcher.calls, [("https://tgenie.example.test", store.chrome_profile_dir)])

    async def test_slash_command_during_first_run_url_prompt_is_not_saved_as_url(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                app = AtlasApp(workspace=Path(workspace_directory).resolve(), tgenie_config_store=store)

                async with app.run_test() as pilot:
                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = "/help"
                    await prompt.action_submit()
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: Available commands", messages)

                self.assertIsNone(store.load().tgenie_url)

    async def test_saved_tgenie_url_is_reused_without_prompting_again(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(workspace=Path(workspace_directory).resolve(), tgenie_config_store=store)

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: Using saved tGenie URL.", messages)
                    self.assertNotIn("tGenie URL is not configured", messages)

    async def test_saved_tgenie_url_opens_chrome_and_waits_for_manual_login(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                launcher = RecordingLoginBrowserLauncher()
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=launcher,
                )

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: Complete login in Chrome, then type /login-done.", messages)

                self.assertEqual(launcher.calls, [("https://tgenie.example.test", store.chrome_profile_dir)])

    async def test_tgenie_browser_launch_error_is_shown_in_tui(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=FailingLoginBrowserLauncher(),
                )

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Error: Could not open system Chrome.", messages)

    async def test_login_done_confirms_manual_tgenie_login(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=RecordingLoginBrowserLauncher(),
                )

                async with app.run_test() as pilot:
                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = "/login-done"
                    await prompt.action_submit()
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: tGenie login confirmed. You can continue in Atlas.", messages)

    async def test_login_done_is_suggested_while_waiting_for_manual_login(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=RecordingLoginBrowserLauncher(),
                )

                async with app.run_test() as pilot:
                    await pilot.press("/")
                    await pilot.pause()

                    suggestions = pilot.app.query_one("#slash-suggestions", Static)
                    self.assertIn("/login-done", str(suggestions.render()))

    async def test_app_shows_header_messages_and_prompt_input(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            app = AtlasApp(workspace=workspace)

            async with app.run_test() as pilot:
                await pilot.pause()

                header = pilot.app.query_one("#header", Static)
                self.assertIn("Atlas", str(header.render()))
                self.assertIn(str(workspace), str(header.render()))
                pilot.app.query_one("#messages")
                pilot.app.query_one("#prompt")

    async def test_app_has_no_footer_status_bar(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                self.assertEqual(len(pilot.app.query("#status")), 0)

    async def test_header_has_breathing_room(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                header = pilot.app.query_one("#header", Static)
                self.assertEqual(header.region.height, 3)
                self.assertGreaterEqual(header.styles.padding.left, 3)
                self.assertEqual(header.styles.padding.top, 1)
                self.assertEqual(header.styles.padding.bottom, 1)

    async def test_layout_uses_color_blocks_without_borders(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertEqual(messages.styles.border.top[0], "")
                self.assertEqual(prompt.styles.border.top[0], "")

    async def test_prompt_box_stays_compact(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                self.assertEqual(prompt.region.height, 3)
                self.assertEqual(prompt.styles.padding.top, 1)
                self.assertEqual(prompt.styles.padding.bottom, 1)

    async def test_prompt_cursor_does_not_use_block_background(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                cursor_style = prompt.get_component_rich_style("input--cursor")
                self.assertIsNotNone(cursor_style.bgcolor)
                cursor_color = cursor_style.bgcolor.triplet
                self.assertEqual(
                    (cursor_color.red, cursor_color.green, cursor_color.blue),
                    (20, 20, 20),
                )
                self.assertTrue(cursor_style.underline)

    async def test_prompt_cursor_offset_stays_at_text_end_for_cjk_ime(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "中文輸入，"
                prompt.cursor_position = len(prompt.value)
                await pilot.pause()

                self.assertEqual(
                    prompt.cursor_screen_offset.x,
                    prompt.content_region.x + cell_len(prompt.value),
                )

    async def test_mouse_focus_does_not_create_box_highlight(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertFalse(messages.can_focus)
                self.assertEqual(prompt.styles.border.top[0], "")
                self.assertEqual(prompt.styles.background_tint.a, 0)

    async def test_app_focuses_prompt_on_startup(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                self.assertIs(pilot.app.focused, prompt)

    async def test_typing_while_transcript_is_focused_returns_to_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                pilot.app.set_focus(messages)

                await pilot.press("h", "i")
                await pilot.pause()

                self.assertEqual(prompt.value, "hi")
                self.assertIs(pilot.app.focused, prompt)

    async def test_app_keeps_prompt_focused_after_prompt_submission(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")
                self.assertIs(pilot.app.focused, prompt)

    async def test_transcript_labels_startup_and_user_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: Ready.", messages)
                self.assertIn("› You  say hello", messages)
                lines = messages.splitlines()
                message_log = pilot.app.query_one("#messages", RichLog)
                self.assertEqual(len(lines[0]), message_log.scrollable_content_region.width)
                self.assertEqual(set(lines[0]), {"─"})
                self.assertEqual(lines[1], "Atlas: Ready.")
                self.assertEqual(set(lines[2]), {"─"})
                self.assertEqual(lines[3], "› You  say hello")

    async def test_user_prompt_highlight_does_not_use_background_color(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                user_line = messages.lines[3]
                self.assertEqual("".join(segment.text for segment in user_line), "› You  say hello")
                for segment in user_line:
                    self.assertIsNone(segment.style.bgcolor)
                user_segments = list(user_line)
                self.assertEqual(rich_color_tuple(user_segments[0]), (0, 153, 255))
                self.assertEqual(rich_color_tuple(user_segments[2]), (153, 153, 153))
                self.assertEqual(rich_color_tuple(user_segments[3]), (255, 255, 255))

    async def test_prompt_text_is_visible_while_typing(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(100, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a", "b", "c")
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                screenshot = pilot.app.export_screenshot()
                self.assertEqual(prompt.value, "abc")
                self.assertIn("abc", screenshot)

    async def test_cjk_prompt_text_is_visible_before_and_after_submission(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(100, 24)) as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "你好啊"
                await pilot.pause()

                self.assertIn("你好啊", pilot.app.export_screenshot())

                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")
                self.assertIn("你好啊", pilot.app.export_screenshot())

    async def test_shift_enter_inserts_newline_without_submitting_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("h", "i", "shift+enter", "t", "h", "e", "r", "e")
                await pilot.pause()

                self.assertEqual(prompt.value, "hi\nthere")
                screenshot = screenshot_text(pilot.app.export_screenshot())
                self.assertIn("hi", screenshot)
                self.assertIn("there", screenshot)
                self.assertNotIn("› You  hi", rich_log_text(pilot.app.query_one("#messages", RichLog)))

                await pilot.press("enter")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "")
                self.assertIn("› You  hi", messages)
                self.assertIn("there", messages)

    async def test_empty_prompt_can_browse_submitted_prompt_history(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "first prompt"
                await prompt.action_submit()
                prompt.value = "second prompt"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(prompt.value, "second prompt")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(prompt.value, "first prompt")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(prompt.value, "second prompt")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(prompt.value, "")

                prompt.value = "draft"
                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(prompt.value, "draft")

    async def test_app_keeps_prompt_focused_after_slash_command(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "/help"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")
                self.assertIs(pilot.app.focused, prompt)

    async def test_transcript_labels_slash_command_output_as_atlas_output(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/help"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: Available commands", messages)

    async def test_consecutive_atlas_outputs_share_one_transcript_block(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/help"
                await prompt.action_submit()
                prompt.value = "/missing"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                lines = messages.splitlines()
                help_index = next(
                    index
                    for index, line in enumerate(lines)
                    if line.startswith("Atlas: Available commands")
                )
                missing_index = next(
                    index
                    for index, line in enumerate(lines)
                    if line.startswith("Atlas: Unknown skill")
                )

                self.assertFalse(any(is_horizontal_rule(line) for line in lines[help_index + 1 : missing_index]))

    async def test_focused_empty_prompt_does_not_render_placeholder_text(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()
                prompt = pilot.app.query_one("#prompt", Input)

                self.assertEqual(prompt.placeholder, "")
                self.assertNotIn(
                    "Enter a prompt",
                    screenshot_text(pilot.app.export_screenshot()),
                )

    async def test_slash_suggestions_show_when_prompt_starts_with_slash(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.press("/")
                await pilot.pause()

                suggestions = pilot.app.query_one("#slash-suggestions", Static)
                suggestion_text = str(suggestions.render())
                self.assertFalse(suggestions.has_class("hidden"))
                self.assertIn("/help", suggestion_text)
                self.assertIn("/llm-wiki", suggestion_text)
                self.assertIn("/skill-creator", suggestion_text)
                selected_marker_style = suggestions.render().spans[0].style
                self.assertEqual(selected_marker_style.foreground.rgb, (0, 153, 255))
                self.assertEqual(selected_marker_style.background.rgb, (28, 28, 28))

    async def test_slash_suggestions_support_keyboard_selection(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("/")
                await pilot.press("down")
                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "")
                self.assertIn("loaded skill: llm-wiki", messages)
                self.assertTrue(pilot.app.query_one("#slash-suggestions", Static).has_class("hidden"))

    async def test_app_shows_fake_tool_loop_status_updates(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Waiting for model", messages)
                self.assertIn("Working: Parsing tool call", messages)
                self.assertIn("Working: Executing tool", messages)
                self.assertIn("Working: Final response", messages)
                self.assertIn("Final answer: hello", messages)

    async def test_fake_tool_loop_does_not_render_footer_status(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(len(pilot.app.query("#status")), 0)
                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Final response", messages)

    async def test_transcript_labels_final_response_as_atlas_output(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: Final answer: hello", messages)

    async def test_transcript_labels_tool_call_errors(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call",
```""",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "run bad tool call"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Error: Tool call JSON is invalid", messages)

    async def test_skill_command_injects_instructions_into_fake_adapter(self) -> None:
        adapter = FakeTgenieAdapter(responses=[])

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/llm-wiki"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("loaded skill: llm-wiki", messages)

        self.assertEqual(len(adapter.sent_messages), 1)
        self.assertIn('<atlas.skill_instructions name="llm-wiki">', adapter.sent_messages[0])
        self.assertIn("LLM Wiki", adapter.sent_messages[0])

    async def test_skill_creator_command_injects_builtin_instructions(self) -> None:
        adapter = FakeTgenieAdapter(responses=[])

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/skill-creator"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Loaded skill: skill-creator", messages)

        self.assertEqual(len(adapter.sent_messages), 1)
        self.assertIn('<atlas.skill_instructions name="skill-creator">', adapter.sent_messages[0])
        self.assertIn("Skill Creator", adapter.sent_messages[0])


if __name__ == "__main__":
    unittest.main()
