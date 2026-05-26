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

    def test_readme_explains_tool_call_protocol_and_fake_adapter_testing(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("atlas.tool_call", readme)
        self.assertIn("atlas.tool_result", readme)
        self.assertIn("一次只能有一個 tool call", readme)
        self.assertIn("malformed JSON", readme)
        self.assertIn("fake adapter", readme)

    def test_readme_explains_workspace_tool_runtime(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("workspace tool runtime", readme)
        self.assertIn("file.list", readme)
        self.assertIn("file.read", readme)
        self.assertIn("file.search", readme)
        self.assertIn("file.write", readme)
        self.assertIn("shell.run", readme)
        self.assertIn("confirmation-required", readme)

    def test_readme_explains_skill_loader_usage(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("skill loader", readme)
        self.assertIn("/llm-wiki", readme)
        self.assertIn("/skill-creator", readme)
        self.assertIn(".atlas/skills/<skill-name>/SKILL.md", readme)
        self.assertIn("atlas.skill_instructions", readme)

    def test_readme_explains_llm_wiki_outputs(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("LLM Wiki 初始化", readme)
        self.assertIn("wiki/raw-sources", readme)
        self.assertIn("wiki/pages/concepts", readme)
        self.assertIn("lint_wiki", readme)
        self.assertIn("render_html_mirror", readme)
        self.assertIn("render_graph_html", readme)


if __name__ == "__main__":
    unittest.main()
