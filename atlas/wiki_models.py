from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WikiInitResult:
    root: Path
    created_paths: list[Path]


@dataclass(frozen=True)
class WikiPage:
    path: Path
    title: str
    page_type: str
    tags: list[str]
    confidence: str
    contradiction: bool
    metadata: dict[str, Any]
    body: str
    wikilinks: list[tuple[str, str]]


@dataclass(frozen=True)
class WikiLintIssue:
    code: str
    page: str
    message: str
    target: str | None = None


@dataclass(frozen=True)
class WikiLintReport:
    issues: list[WikiLintIssue]


@dataclass(frozen=True)
class WikiRenderResult:
    written_files: list[Path]


@dataclass(frozen=True)
class WikiGraphResult:
    output_path: Path
    nodes: list[dict[str, Any]]
    edges: list[dict[str, str]]
