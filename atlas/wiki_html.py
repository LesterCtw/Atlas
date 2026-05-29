from __future__ import annotations

import html
from collections.abc import Sequence
from pathlib import Path

from atlas.wiki_markup import render_inline_markdown, slug
from atlas.wiki_models import WikiPage, WikiRenderResult


def render_wiki_html_mirror(workspace: Path, pages: Sequence[WikiPage]) -> WikiRenderResult:
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
