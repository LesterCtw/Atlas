from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeTests(unittest.TestCase):
    def test_readme_explains_atlas_startup_and_workspace_behavior(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("uv run atlas", readme)
        self.assertIn("atlas <workspace-path>", readme)
        self.assertIn("預設 workspace 是目前資料夾", readme)


if __name__ == "__main__":
    unittest.main()
