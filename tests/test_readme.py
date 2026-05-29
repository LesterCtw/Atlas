from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_readme_focuses_on_deployment_and_usage(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Windows 部署", readme)
        self.assertIn("第一次啟動", readme)
        self.assertIn("基本使用", readme)
        self.assertIn("Input to Output Workflow", readme)
        self.assertIn("Workspace 安全規則", readme)
        self.assertIn("常見問題", readme)
        self.assertIn("維護者驗證", readme)

    def test_readme_explains_windows_install_and_launch(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("py -3.12 -m venv .venv", readme)
        self.assertIn(".\\.venv\\Scripts\\python -m pip install -e .", readme)
        self.assertIn(".\\.venv\\Scripts\\atlas --help", readme)
        self.assertIn("atlas <workspace-path>", readme)
        self.assertIn("/login-done", readme)
        self.assertIn("%APPDATA%\\Atlas", readme)

    def test_readme_explains_input_to_output_workflows(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("一般對話", readme)
        self.assertIn("Workspace 檔案工作", readme)
        self.assertIn("PDF 摘要或分析", readme)
        self.assertIn("LLM Wiki 匯入", readme)
        self.assertIn("Skill 使用", readme)
        self.assertIn("atlas.tool_call", readme)
        self.assertIn("atlas.tool_result", readme)
        self.assertIn("file.list", readme)
        self.assertIn("file.read", readme)
        self.assertIn("file.search", readme)
        self.assertIn("file.write", readme)
        self.assertIn("file.attach", readme)
        self.assertIn("pdf.attach", readme)
        self.assertIn("shell.run", readme)

    def test_readme_explains_outputs_and_limits(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("wiki/index.md", readme)
        self.assertIn("wiki/log.md", readme)
        self.assertIn("wiki/pages/", readme)
        self.assertIn("wiki/output/html/index.html", readme)
        self.assertIn("wiki/output/graph/index.html", readme)
        self.assertIn("workspace 內 `.pdf`", readme)
        self.assertIn("`.jpg`", readme)
        self.assertIn("`.png`", readme)
        self.assertIn("confirmation-required", readme)
        self.assertIn("rejected", readme)

    def test_readme_explains_fa_stem_brief_tracer(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("/fa-stem brief <workspace-relative-folder>", readme)
        self.assertIn("atlas-fa-stem-brief.html", readme)
        self.assertIn("case background", readme)
        self.assertIn("3x3 Photo Bundle", readme)
        self.assertIn("recursive", readme)
        self.assertIn("candidate observations", readme)
        self.assertIn("second-pass original-image review", readme)
        self.assertIn("final ranking", readme)
        self.assertIn("primary suspect unclear", readme)
        self.assertIn("profile anomalies", readme)
        self.assertIn("不是 final conclusions", readme)
        self.assertIn("AI 建議的初篩標記", readme)
        self.assertIn("不是量測級標註", readme)

    def test_readme_explains_attachment_evidence_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Attachment evidence", readme)
        self.assertIn("observation", readme)
        self.assertIn("inference", readme)
        self.assertIn("uncertainty", readme)
        self.assertIn("confidence", readme)
        self.assertIn("coordinates", readme)
        self.assertIn("後續 workflow", readme)

    def test_docs_do_not_reference_removed_development_flows(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        html = (ROOT / "atlas-deployment-and-usage.html").read_text(encoding="utf-8").lower()

        removed_terms = (
            "pr" + "obe",
            "hi" + "tl",
            "scripts/" + "pr" + "obe_tgenie.py",
            "hi" + "tl_collect_windows.ps1",
        )
        for removed_term in removed_terms:
            self.assertNotIn(removed_term, readme)
            self.assertNotIn(removed_term, html)

    def test_html_manual_exists_and_covers_workflow(self) -> None:
        html = (ROOT / "atlas-deployment-and-usage.html").read_text(encoding="utf-8")

        self.assertIn("<title>Atlas 部署與使用說明書</title>", html)
        self.assertIn("Windows 部署步驟", html)
        self.assertIn("Input to Output Workflow", html)
        self.assertIn("/llm-wiki ingest", html)
        self.assertIn("wiki/output/html/index.html", html)
        self.assertIn("wiki/output/graph/index.html", html)


if __name__ == "__main__":
    unittest.main()
