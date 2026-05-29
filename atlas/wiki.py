from __future__ import annotations

from dataclasses import dataclass
import html
import json
from pathlib import Path
from typing import Any

from pyvis.network import Network

from atlas.wiki_markup import (
    extract_wikilinks,
    parse_frontmatter,
    render_inline_markdown,
    slug,
    title_from_path,
)


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
    output_dir = workspace / "wiki" / "output" / "html"
    output_dir.mkdir(parents=True, exist_ok=True)
    slug_by_title = {page.title: slug(page.title) for page in pages}
    written_files: list[Path] = []

    for page in pages:
        output_path = output_dir / f"{slug(page.title)}.html"
        output_path.write_text(_render_page_html(page, slug_by_title), encoding="utf-8")
        written_files.append(output_path)

    index_path = output_dir / "index.html"
    links = "\n".join(
        f'<li><a href="{slug(page.title)}.html">{html.escape(page.title)}</a></li>' for page in pages
    )
    index_path.write_text(
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>LLM Wiki</title></head>"
        f"<body><h1>LLM Wiki</h1><ul>{links}</ul></body></html>\n",
        encoding="utf-8",
    )
    written_files.append(index_path)
    return WikiRenderResult(written_files=written_files)


def render_graph_html(workspace: Path) -> WikiGraphResult:
    pages = load_wiki_pages(workspace)
    output_dir = workspace / "wiki" / "output" / "graph"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "index.html"
    title_to_page = {page.title: page for page in pages}
    degree_by_title = {page.title: 0 for page in pages}
    edges: list[dict[str, str]] = []

    for page in pages:
        for target, _label in page.wikilinks:
            if target not in title_to_page:
                continue
            edges.append({"from": page.title, "to": target})
            degree_by_title[page.title] += 1
            degree_by_title[target] += 1

    nodes = [
        {
            "id": page.title,
            "label": page.title,
            "type": page.page_type,
            "color": _graph_color(page.page_type),
            "size": 18 + degree_by_title[page.title] * 4,
        }
        for page in pages
    ]
    _write_pyvis_graph(output_path, nodes, edges)
    return WikiGraphResult(output_path=output_path, nodes=nodes, edges=edges)


def _write_pyvis_graph(output_path: Path, nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> None:
    network = Network(
        height="100vh",
        width="100%",
        bgcolor="#0d1117",
        font_color="#e6edf3",
        directed=False,
        cdn_resources="in_line",
    )
    for node in nodes:
        network.add_node(
            node["id"],
            label=node["label"],
            title=f"{node['label']} ({node['type']})",
            color=node["color"],
            size=node["size"],
        )
    for edge in edges:
        network.add_edge(edge["from"], edge["to"], color="#8b949e", width=1)
    network.barnes_hut()
    network.write_html(str(output_path), notebook=False, open_browser=False)
    with output_path.open("a", encoding="utf-8") as file:
        file.write(
            "\n<script id=\"atlas-graph-data\" type=\"application/json\">\n"
            + json.dumps(
                {
                    "nodes": nodes,
                    "edges": edges,
                    "graphStyle": {"background": "#0d1117", "edgeColor": "#8b949e"},
                    "renderer": "pyvis",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n</script>\n"
        )


def _graph_color(page_type: str) -> str:
    return {
        "concept": "#7c3aed",
        "source": "#2dd4bf",
        "contradiction": "#f97316",
    }.get(page_type, "#94a3b8")


def _render_page_html(page: WikiPage, slug_by_title: dict[str, str]) -> str:
    rendered_lines: list[str] = []
    for line in page.body.splitlines():
        if line.startswith("# "):
            rendered_lines.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
            continue
        if not line.strip():
            continue
        rendered_lines.append(f"<p>{render_inline_markdown(line, slug_by_title)}</p>")

    body = "\n".join(rendered_lines)
    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(page.title)}</title></head>"
        f"<body>{body}</body></html>\n"
    )
