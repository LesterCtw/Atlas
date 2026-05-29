from __future__ import annotations

from pathlib import Path

from atlas.wiki_graph import render_wiki_graph_html
from atlas.wiki_html import render_wiki_html_mirror
from atlas.wiki_models import (
    WikiGraphResult,
    WikiInitResult,
    WikiLintIssue,
    WikiLintReport,
    WikiPage,
    WikiRenderResult,
)
from atlas.wiki_markup import (
    extract_wikilinks,
    parse_frontmatter,
    title_from_path,
)


WIKI_DIRECTORIES = (
    "raw-sources",
    "schema",
    "pages",
    "pages/concepts",
    "pages/sources",
    "pages/contradictions",
    "output/html",
    "output/graph",
)

WIKI_FILES = {
    "index.md": "# LLM Wiki Index\n\nThis index is maintained by Atlas.\n",
    "log.md": "# LLM Wiki Log\n\nChronological wiki maintenance log.\n",
    "schema/page.md": (
        "# Wiki Page Schema\n\n"
        "Required frontmatter fields: title, type, tags, confidence, contradiction.\n"
    ),
}


def initialize_wiki(workspace: Path) -> WikiInitResult:
    root = workspace / "wiki"
    created_paths: list[Path] = []

    for directory in WIKI_DIRECTORIES:
        path = root / directory
        if not path.exists():
            created_paths.append(path)
        path.mkdir(parents=True, exist_ok=True)

    for relative_path, content in WIKI_FILES.items():
        path = root / relative_path
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created_paths.append(path)

    return WikiInitResult(root=root, created_paths=created_paths)


def load_wiki_pages(workspace: Path) -> list[WikiPage]:
    pages_root = workspace / "wiki" / "pages"
    if not pages_root.is_dir():
        return []

    pages: list[WikiPage] = []
    for path in sorted(pages_root.rglob("*.md")):
        metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = str(metadata.get("title") or title_from_path(path))
        page_type = str(metadata.get("type") or path.parent.name)
        tags = metadata.get("tags")
        pages.append(
            WikiPage(
                path=path,
                title=title,
                page_type=page_type,
                tags=tags if isinstance(tags, list) else [],
                confidence=str(metadata.get("confidence") or ""),
                contradiction=bool(metadata.get("contradiction")),
                metadata=metadata,
                body=body,
                wikilinks=extract_wikilinks(body),
            )
        )
    return pages


def lint_wiki(workspace: Path) -> WikiLintReport:
    pages = load_wiki_pages(workspace)
    issues: list[WikiLintIssue] = []
    titles = {page.title for page in pages}
    incoming_targets = {target for page in pages for target, _label in page.wikilinks if target in titles}

    for page in pages:
        relative_page = page.path.name
        if not page.metadata:
            issues.append(
                WikiLintIssue(
                    code="missing-frontmatter",
                    page=relative_page,
                    message="Wiki page is missing YAML frontmatter.",
                )
            )
        for key in ("title", "type", "tags", "confidence", "contradiction"):
            if key not in page.metadata:
                issues.append(
                    WikiLintIssue(
                        code="missing-metadata",
                        page=relative_page,
                        target=key,
                        message=f"Wiki page is missing metadata field: {key}.",
                    )
                )
        for target, _label in page.wikilinks:
            if target not in titles:
                issues.append(
                    WikiLintIssue(
                        code="broken-wikilink",
                        page=relative_page,
                        target=target,
                        message=f"Wiki page links to missing page: {target}.",
                    )
                )
        if not page.wikilinks and page.title not in incoming_targets:
            issues.append(
                WikiLintIssue(
                    code="orphan-page",
                    page=relative_page,
                    message="Wiki page has no incoming or outgoing wikilinks.",
                )
            )
    return WikiLintReport(issues=issues)


def render_html_mirror(workspace: Path) -> WikiRenderResult:
    pages = load_wiki_pages(workspace)
    return render_wiki_html_mirror(workspace, pages)


def render_graph_html(workspace: Path) -> WikiGraphResult:
    pages = load_wiki_pages(workspace)
    return render_wiki_graph_html(workspace, pages)
