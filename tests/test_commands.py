from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.commands import handle_slash_command
from atlas.skills import SkillLoader


class SlashCommandTests(unittest.TestCase):
    def test_help_command_lists_available_commands(self) -> None:
        result = handle_slash_command("/help")

        self.assertEqual(result.action, "message")
        self.assertIn("/help", result.message)
        self.assertIn("/exit", result.message)

    def test_help_with_skill_loader_lists_skill_commands(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            skill_dir = workspace / ".atlas" / "skills" / "repair-notes"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "# Repair Notes\n\nSummarize repair notes.",
                encoding="utf-8",
            )
            loader = SkillLoader(workspace=workspace)

            result = handle_slash_command("/help", skill_loader=loader)

        self.assertEqual(result.action, "message")
        self.assertIn("/help", result.message)
        self.assertIn("/exit", result.message)
        self.assertIn("/llm-wiki", result.message)
        self.assertIn("/skill-creator", result.message)
        self.assertIn("/repair-notes", result.message)

    def test_exit_command_requests_clean_exit(self) -> None:
        result = handle_slash_command("/exit")

        self.assertEqual(result.action, "exit")
        self.assertIn("結束", result.message)

    def test_unknown_slash_command_returns_clear_error(self) -> None:
        result = handle_slash_command("/missing")

        self.assertEqual(result.action, "message")
        self.assertIn("未知命令", result.message)
        self.assertIn("/missing", result.message)

    def test_builtin_skill_command_returns_injected_instructions(self) -> None:
        with TemporaryDirectory() as directory:
            loader = SkillLoader(workspace=Path(directory))

            result = handle_slash_command("/llm-wiki", skill_loader=loader)

        self.assertEqual(result.action, "inject-skill")
        self.assertIn("已載入 skill：llm-wiki", result.message)
        self.assertIsNotNone(result.injected_message)
        self.assertIn('<atlas.skill_instructions name="llm-wiki">', result.injected_message)
        self.assertIn("LLM Wiki", result.injected_message)

    def test_llm_wiki_command_initializes_wiki_structure_and_injects_instructions(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            loader = SkillLoader(workspace=workspace)

            result = handle_slash_command("/llm-wiki", skill_loader=loader)

            self.assertTrue((workspace / "wiki" / "index.md").is_file())
            self.assertTrue((workspace / "wiki" / "raw-sources").is_dir())

        self.assertEqual(result.action, "inject-skill")
        self.assertIn("已初始化 LLM Wiki", result.message)
        self.assertIsNotNone(result.injected_message)

    def test_workspace_skill_command_returns_injected_instructions(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            skill_dir = workspace / ".atlas" / "skills" / "repair-notes"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "# Repair Notes\n\nSummarize repair notes.",
                encoding="utf-8",
            )
            loader = SkillLoader(workspace=workspace)

            result = handle_slash_command("/repair-notes", skill_loader=loader)

        self.assertEqual(result.action, "inject-skill")
        self.assertIn("已載入 skill：repair-notes", result.message)
        self.assertIsNotNone(result.injected_message)
        self.assertIn('<atlas.skill_instructions name="repair-notes">', result.injected_message)
        self.assertIn("Summarize repair notes.", result.injected_message)

    def test_unknown_skill_command_returns_clear_error_without_injection(self) -> None:
        with TemporaryDirectory() as directory:
            loader = SkillLoader(workspace=Path(directory))

            result = handle_slash_command("/missing", skill_loader=loader)

        self.assertEqual(result.action, "message")
        self.assertIn("未知 skill", result.message)
        self.assertIn("missing", result.message)
        self.assertIsNone(result.injected_message)

    def test_skill_command_does_not_treat_path_segments_as_skill_names(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / ".atlas" / "skills").mkdir(parents=True)
            secret_dir = workspace / "secret"
            secret_dir.mkdir()
            (secret_dir / "SKILL.md").write_text(
                "# Secret\n\nThis must not load as a skill.",
                encoding="utf-8",
            )
            loader = SkillLoader(workspace=workspace)

            result = handle_slash_command("/../../secret", skill_loader=loader)

        self.assertEqual(result.action, "message")
        self.assertIn("未知 skill", result.message)
        self.assertIsNone(result.injected_message)


if __name__ == "__main__":
    unittest.main()
