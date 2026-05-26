from __future__ import annotations

import argparse
from pathlib import Path


def resolve_workspace(workspace: str | Path, cwd: Path | None = None) -> Path:
    base = Path.cwd() if cwd is None else cwd
    path = Path(workspace).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Start the Atlas interactive terminal UI.",
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="Workspace path. Defaults to the current directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = resolve_workspace(args.workspace)

    from atlas.tui import AtlasApp

    AtlasApp(workspace=workspace).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
