from __future__ import annotations

from pathlib import Path


WORKSPACE_ESCAPE_ERROR = "Path must stay inside the workspace."


class WorkspacePathError(ValueError):
    pass


def resolve_workspace_path(workspace: Path, raw_path: str | Path) -> Path:
    root = workspace.resolve()
    path = Path(raw_path)
    if path.is_absolute():
        raise WorkspacePathError(WORKSPACE_ESCAPE_ERROR)

    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise WorkspacePathError(WORKSPACE_ESCAPE_ERROR) from error
    return resolved


def workspace_relative_path(workspace: Path, path: Path) -> str:
    root = workspace.resolve()
    path.resolve().relative_to(root)
    for base in (workspace, root):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.resolve().relative_to(root).as_posix()


def is_within_workspace(workspace: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
    except ValueError:
        return False
    return True
