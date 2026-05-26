from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.fake_loop import FakeTgenieAdapter
from atlas.tui import AtlasApp
from textual.widgets import RichLog


def rich_log_text(log: RichLog) -> str:
    return "\n".join(str(line) for line in log.lines)


class AtlasTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_app_shows_workspace_messages_and_prompt_input(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            app = AtlasApp(workspace=workspace)

            async with app.run_test() as pilot:
                await pilot.pause()

                self.assertIn(str(workspace), str(pilot.app.query_one("#workspace").render()))
                pilot.app.query_one("#messages")
                pilot.app.query_one("#prompt")

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


if __name__ == "__main__":
    unittest.main()
