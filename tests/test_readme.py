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
        self.assertIn("`Shift+Enter` 可以插入換行", readme)
        self.assertIn("上下方向鍵瀏覽過去送出的文字", readme)
        self.assertIn("單欄深色 TUI", readme)
        self.assertIn("header", readme)
        self.assertIn("不保留 footer status bar", readme)
        self.assertIn("tool loop 執行時會直接在 transcript 顯示 `Working:` 狀態", readme)
        self.assertIn("TUI 畫面文案使用英文", readme)
        self.assertIn("配色參考 [`DESIGN.md`](DESIGN.md)", readme)
        self.assertIn("單一藍色 `#0099ff`", readme)
        self.assertIn("輸入框刻意不放 placeholder", readme)
        self.assertIn("中文 IME", readme)
        self.assertIn("輸入框游標使用 underline", readme)
        self.assertIn("不使用白色 block cursor", readme)
        self.assertIn("terminal cursor 對齊文字插入點", readme)
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
        self.assertIn("延伸到訊息區可用寬度的水平線分隔不同發言者區塊", readme)
        self.assertIn("連續 Atlas 訊息之間不會再插入水平線", readme)

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

    def test_readme_explains_first_run_tgenie_setup(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("首次 tGenie 設定", readme)
        self.assertIn("tGenie URL", readme)
        self.assertIn("後續啟動會重用已儲存的 URL", readme)
        self.assertIn("Chrome profile", readme)
        self.assertIn("不放在 workspace", readme)
        self.assertIn("/login-done", readme)
        self.assertIn("Atlas 不會要求、儲存或處理密碼", readme)

    def test_readme_explains_issue_5_probe_checklist(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("notes", readme)
        self.assertIn("texts", readme)
        self.assertIn("inspect <元素編號>", readme)
        self.assertIn("Stable selector candidates", readme)
        self.assertIn("set_text latest_response", readme)
        self.assertIn("smoke <prompt_input 編號> <send_button 編號>", readme)
        self.assertIn("Gemini-3.0-flash Preview (All around help)", readme)
        self.assertIn("Gemini-3.1-Pro Preview", readme)
        self.assertIn("stop_generating_hover_label", readme)
        self.assertIn("latest_response_text", readme)
        self.assertIn("smoke_result", readme)

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
