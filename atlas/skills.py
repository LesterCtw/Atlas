from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    instructions: str


BUILTIN_SKILLS = {
    "llm-wiki": """# LLM Wiki

You are helping maintain an LLM Wiki for the current Atlas workspace.
Keep raw sources immutable, write Markdown-first wiki pages, maintain an
index and chronological log, and make claims traceable to source documents.
""".strip(),
    "skill-creator": """# Skill Creator

You are helping create an Atlas skill for the current workspace.
Clarify the workflow, write focused instructions, keep the skill small,
and document how users invoke it with a slash command.
""".strip(),
}

_VALID_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SkillLoader:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def load(self, name: str) -> Skill:
        if _VALID_SKILL_NAME.fullmatch(name) is None:
            raise SkillNotFound(name)

        local_skill = self.workspace / ".atlas" / "skills" / name / "SKILL.md"
        if local_skill.is_file():
            return Skill(name=name, instructions=local_skill.read_text(encoding="utf-8").strip())

        try:
            instructions = BUILTIN_SKILLS[name]
        except KeyError as exc:
            raise SkillNotFound(name) from exc
        return Skill(name=name, instructions=instructions)

    def list_names(self) -> list[str]:
        names = set(BUILTIN_SKILLS)
        skills_dir = self.workspace / ".atlas" / "skills"
        if skills_dir.is_dir():
            for child in skills_dir.iterdir():
                if (
                    child.is_dir()
                    and _VALID_SKILL_NAME.fullmatch(child.name) is not None
                    and (child / "SKILL.md").is_file()
                ):
                    names.add(child.name)
        return sorted(names)


class SkillNotFound(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name
