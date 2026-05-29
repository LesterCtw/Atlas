from __future__ import annotations

import html
from pathlib import Path
import re
from typing import Any


_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def extract_wikilinks(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in _WIKILINK_PATTERN.finditer(markdown):
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()
        links.append((target, label))
    return links


def render_inline_markdown(markdown: str, slug_by_title: dict[str, str]) -> str:
    parts: list[str] = []
    last_end = 0
    for match in _WIKILINK_PATTERN.finditer(markdown):
        parts.append(html.escape(markdown[last_end : match.start()]))
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()
        href = f"{slug_by_title.get(target, slug(target))}.html"
        parts.append(f'<a href="{html.escape(href)}">{html.escape(label)}</a>')
        last_end = match.end()
    parts.append(html.escape(markdown[last_end:]))
    return "".join(parts)


def slug(title: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return value or "page"


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


def title_from_path(path: Path) -> str:
    return path.stem.replace("-", " ").title()


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
