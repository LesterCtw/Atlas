from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.tui import AtlasApp


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


if __name__ == "__main__":
    unittest.main()
