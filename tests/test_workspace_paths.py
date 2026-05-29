from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.workspace_paths import (
    WORKSPACE_ESCAPE_ERROR,
    WorkspacePathError,
    is_within_workspace,
    resolve_workspace_path,
    workspace_relative_path,
)


class WorkspacePathsTests(unittest.TestCase):
    def test_resolves_relative_path_inside_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)

            resolved = resolve_workspace_path(workspace, "notes/report.md")

        self.assertEqual(resolved, (workspace / "notes" / "report.md").resolve())

    def test_rejects_absolute_path(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            outside = Path(directory) / "outside.txt"

            with self.assertRaisesRegex(WorkspacePathError, WORKSPACE_ESCAPE_ERROR):
                resolve_workspace_path(workspace, outside)

    def test_rejects_symlink_escape(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            (workspace / "linked.txt").symlink_to(outside)

            with self.assertRaisesRegex(WorkspacePathError, WORKSPACE_ESCAPE_ERROR):
                resolve_workspace_path(workspace, "linked.txt")

    def test_reports_workspace_relative_path(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            path = workspace / "notes" / "report.md"

            relative_path = workspace_relative_path(workspace, path)

        self.assertEqual(relative_path, "notes/report.md")

    def test_workspace_relative_path_preserves_symlink_name_inside_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            target = workspace / "target.txt"
            target.write_text("ok", encoding="utf-8")
            link = workspace / "link.txt"
            link.symlink_to(target)

            relative_path = workspace_relative_path(workspace, link)

        self.assertEqual(relative_path, "link.txt")

    def test_detects_paths_outside_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")

            self.assertTrue(is_within_workspace(workspace, workspace / "inside.txt"))
            self.assertFalse(is_within_workspace(workspace, outside))


if __name__ == "__main__":
    unittest.main()
