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
        self.assertIn("啟動後會自動聚焦輸入框", readme)
        self.assertIn("不用點選輸入框", readme)
        self.assertIn("單欄深色 TUI", readme)
        self.assertIn("header", readme)
        self.assertIn("不保留 footer status bar", readme)
        self.assertIn("tool loop 執行時會直接在 transcript 顯示 `Working:` 狀態", readme)
        self.assertIn("TUI 畫面文案使用英文", readme)
        self.assertIn("輸入框刻意不放 placeholder", readme)
        self.assertIn("中文 IME", readme)
        self.assertIn("輸入框游標使用 underline", readme)
        self.assertIn("不使用白色 block cursor", readme)
        self.assertIn("輸入框維持 3 行高度", readme)
        self.assertIn("header 使用上下對稱 padding", readme)
        self.assertIn("鍵盤優先操作", readme)
        self.assertIn("不會改變框線 highlight", readme)
        self.assertIn("輸入 `/` 時會顯示 slash command 選單", readme)
        self.assertIn("上下方向鍵選擇", readme)

    def test_readme_explains_tui_transcript_labels(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("transcript", readme)
        self.assertIn("`› You  prompt`", readme)
        self.assertIn("`Atlas:`", readme)
        self.assertIn("`Working:`", readme)
        self.assertIn("`Error:`", readme)
        self.assertIn("Atlas 發言和使用者發言都留在同一個 transcript 色塊裡", readme)
        self.assertIn("不再用訊息背景色塊分開", readme)
        self.assertIn("不使用背景色塊", readme)
        self.assertIn("不使用邊框", readme)
        self.assertIn("延伸到訊息區可用寬度的水平線分隔對話項目", readme)

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
