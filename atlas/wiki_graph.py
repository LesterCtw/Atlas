from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyvis.network import Network

from atlas.wiki_models import WikiGraphResult, WikiPage


def render_wiki_graph_html(workspace: Path, pages: Sequence[WikiPage]) -> WikiGraphResult:
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
