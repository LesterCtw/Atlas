from __future__ import annotations

from dataclasses import dataclass
import html
import json
from pathlib import Path
import re
from typing import Any

from pyvis.network import Network


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

_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


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


def extract_wikilinks(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in _WIKILINK_PATTERN.finditer(markdown):
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()
        links.append((target, label))
    return links


def load_wiki_pages(workspace: Path) -> list[WikiPage]:
    pages_root = workspace / "wiki" / "pages"
    if not pages_root.is_dir():
        return []

    pages: list[WikiPage] = []
    for path in sorted(pages_root.rglob("*.md")):
        metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = str(metadata.get("title") or _title_from_path(path))
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
    slug_by_title = {page.title: _slug(page.title) for page in pages}
    written_files: list[Path] = []

    for page in pages:
        output_path = output_dir / f"{_slug(page.title)}.html"
        output_path.write_text(_render_page_html(page, slug_by_title), encoding="utf-8")
        written_files.append(output_path)

    index_path = output_dir / "index.html"
    links = "\n".join(
        f'<li><a href="{_slug(page.title)}.html">{html.escape(page.title)}</a></li>' for page in pages
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
        rendered_lines.append(f"<p>{_render_inline_markdown(line, slug_by_title)}</p>")

    body = "\n".join(rendered_lines)
    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(page.title)}</title></head>"
        f"<body>{body}</body></html>\n"
    )


def _render_inline_markdown(markdown: str, slug_by_title: dict[str, str]) -> str:
    parts: list[str] = []
    last_end = 0
    for match in _WIKILINK_PATTERN.finditer(markdown):
        parts.append(html.escape(markdown[last_end : match.start()]))
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()
        href = f"{slug_by_title.get(target, _slug(target))}.html"
        parts.append(f'<a href="{html.escape(href)}">{html.escape(label)}</a>')
        last_end = match.end()
    parts.append(html.escape(markdown[last_end:]))
    return "".join(parts)


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "page"


def parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    if not markdown.startswith("---\n"):
        return {}, markdown

    end_marker = markdown.find("\n---\n", 4)
    if end_marker == -1:
        return {}, markdown

    raw_frontmatter = markdown[4:end_marker]
    body = markdown[end_marker + len("\n---\n") :]
    metadata: dict[str, Any] = {}
    for raw_line in raw_frontmatter.splitlines():
        if ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        metadata[key.strip()] = _parse_frontmatter_value(raw_value.strip())
    return metadata, body


def _parse_frontmatter_value(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        items = value[1:-1].strip()
        if not items:
            return []
        return [item.strip().strip('"').strip("'") for item in items.split(",")]
    return value.strip('"').strip("'")


def _title_from_path(path: Path) -> str:
    return path.stem.replace("-", " ").title()
