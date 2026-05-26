from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.skills import SkillLoader


class SkillLoaderTests(unittest.TestCase):
    def test_loads_builtin_llm_wiki_skill(self) -> None:
        with TemporaryDirectory() as directory:
            loader = SkillLoader(workspace=Path(directory))

            skill = loader.load("llm-wiki")

        self.assertEqual(skill.name, "llm-wiki")
        self.assertIn("LLM Wiki", skill.instructions)

    def test_loads_builtin_skill_creator_skill(self) -> None:
        with TemporaryDirectory() as directory:
            loader = SkillLoader(workspace=Path(directory))

            skill = loader.load("skill-creator")

        self.assertEqual(skill.name, "skill-creator")
        self.assertIn("skill", skill.instructions.lower())

    def test_loads_workspace_local_skill(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            skill_dir = workspace / ".atlas" / "skills" / "repair-notes"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "# Repair Notes\n\nSummarize repair notes from source PDFs.",
                encoding="utf-8",
            )
            loader = SkillLoader(workspace=workspace)

            skill = loader.load("repair-notes")

        self.assertEqual(skill.name, "repair-notes")
        self.assertIn("Summarize repair notes", skill.instructions)


if __name__ == "__main__":
    unittest.main()
