from __future__ import annotations

import html
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.fake_loop import FakeTgenieAdapter
from atlas.tui import AtlasApp
from textual.widgets import Input, RichLog, Static


def rich_log_text(log: RichLog) -> str:
    return "\n".join("".join(segment.text for segment in line) for line in log.lines)


def screenshot_text(svg: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", svg)).replace("\xa0", " ")


class AtlasTuiTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_app_shows_footer_status_hints(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                status = str(pilot.app.query_one("#status", Static).render())
                self.assertIn("Status", status)
                self.assertIn("Enter", status)
                self.assertIn("/help", status)
                self.assertIn("/exit", status)

    async def test_header_and_status_have_breathing_room(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                header = pilot.app.query_one("#header", Static)
                status = pilot.app.query_one("#status", Static)
                self.assertEqual(header.region.height, 2)
                self.assertEqual(status.region.height, 2)
                self.assertGreaterEqual(header.styles.padding.left, 3)
                self.assertGreaterEqual(status.styles.padding.left, 3)
                self.assertEqual(header.styles.padding.top, 1)
                self.assertEqual(status.styles.padding.bottom, 1)

    async def test_mouse_focus_does_not_create_box_highlight(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertFalse(messages.can_focus)
                self.assertEqual(prompt.styles.border.top[1].hex6, "#26364A")
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
                self.assertIn("Atlas: Ready.\n\n› You  say hello", messages)

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
                self.assertIn("Waiting for model", messages)
                self.assertIn("Parsing tool call", messages)
                self.assertIn("Executing tool", messages)
                self.assertIn("Final response", messages)
                self.assertIn("Final answer: hello", messages)

    async def test_status_footer_reflects_latest_fake_tool_loop_status(self) -> None:
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

                status = str(pilot.app.query_one("#status", Static).render())
                self.assertIn("Final response", status)
                self.assertIn("Enter", status)
                self.assertIn("/help", status)
                self.assertIn("/exit", status)

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
