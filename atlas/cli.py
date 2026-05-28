from __future__ import annotations

import argparse
from pathlib import Path

from atlas.tgenie_setup import AtlasConfigStore, TgenieBrowserLauncher, default_atlas_config_dir


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


def build_app(workspace: Path, config_dir: Path | None = None):
    from atlas.tui import AtlasApp

    store = AtlasConfigStore(config_dir=config_dir or default_atlas_config_dir())
    return AtlasApp(
        workspace=workspace,
        tgenie_config_store=store,
        tgenie_browser_launcher=TgenieBrowserLauncher(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = resolve_workspace(args.workspace)

    build_app(workspace=workspace).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
