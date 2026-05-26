from __future__ import annotations

import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.cli import resolve_workspace


ROOT = Path(__file__).resolve().parents[1]


class AtlasCliTests(unittest.TestCase):
    def test_cli_help_describes_the_atlas_command(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "atlas.cli", "--help"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("atlas", result.stdout)
        self.assertIn("workspace", result.stdout)

    def test_default_workspace_uses_current_directory(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = resolve_workspace(".", cwd=Path(directory))

        self.assertEqual(workspace, Path(directory).resolve())

    def test_relative_workspace_is_resolved_from_current_directory(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = resolve_workspace("project-a", cwd=Path(directory))

        self.assertEqual(workspace, (Path(directory) / "project-a").resolve())

    def test_project_declares_atlas_console_script(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(project["project"]["scripts"]["atlas"], "atlas.cli:main")


if __name__ == "__main__":
    unittest.main()
