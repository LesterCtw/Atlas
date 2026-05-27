from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.fake_loop import FakeTgenieAdapter
from atlas.tui import AtlasApp
from textual.widgets import Input, RichLog, Static


def rich_log_text(log: RichLog) -> str:
    return "\n".join(str(line) for line in log.lines)


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
                self.assertIn("狀態", status)
                self.assertIn("Enter", status)
                self.assertIn("/help", status)
                self.assertIn("/exit", status)

    async def test_app_focuses_prompt_on_startup(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
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
                self.assertIn("Atlas：已啟動。", messages)
                self.assertIn("User：say hello", messages)

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
                self.assertIn("Atlas：可用命令", messages)

    async def test_prompt_placeholder_mentions_prompt_and_slash_commands(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)

                self.assertIn("prompt", prompt.placeholder.lower())
                self.assertIn("slash command", prompt.placeholder.lower())
                self.assertIn("/help", prompt.placeholder)

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
                self.assertIn("等待模型回覆", messages)
                self.assertIn("解析 tool call", messages)
                self.assertIn("執行 tool", messages)
                self.assertIn("收到最終回覆", messages)
                self.assertIn("Final answer: hello", messages)

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
                self.assertIn("Atlas：Final answer: hello", messages)

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
                self.assertIn("Error：Tool call JSON 格式錯誤", messages)

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
                self.assertIn("已載入 skill：llm-wiki", messages)

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
                self.assertIn("已載入 skill：skill-creator", messages)

        self.assertEqual(len(adapter.sent_messages), 1)
        self.assertIn('<atlas.skill_instructions name="skill-creator">', adapter.sent_messages[0])
        self.assertIn("Skill Creator", adapter.sent_messages[0])


if __name__ == "__main__":
    unittest.main()
