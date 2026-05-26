from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.wiki import (
    extract_wikilinks,
    initialize_wiki,
    lint_wiki,
    load_wiki_pages,
    render_graph_html,
    render_html_mirror,
)


class WikiInitializationTests(unittest.TestCase):
    def test_initializes_hermes_style_wiki_structure(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)

            result = initialize_wiki(workspace)

            self.assertEqual(result.root, workspace / "wiki")
            for path in [
                "wiki/raw-sources",
                "wiki/schema",
                "wiki/pages",
                "wiki/pages/concepts",
                "wiki/pages/sources",
                "wiki/pages/contradictions",
                "wiki/output/html",
                "wiki/output/graph",
            ]:
                self.assertTrue((workspace / path).is_dir(), path)
            for path in [
                "wiki/index.md",
                "wiki/log.md",
                "wiki/schema/page.md",
            ]:
                self.assertTrue((workspace / path).is_file(), path)


class WikiParsingTests(unittest.TestCase):
    def test_extracts_wikilinks_with_aliases(self) -> None:
        links = extract_wikilinks(
            "This page links to [[Pump Failure]] and [[Motor Current|current signature]]."
        )

        self.assertEqual(
            links,
            [
                ("Pump Failure", "Pump Failure"),
                ("Motor Current", "current signature"),
            ],
        )

    def test_loads_page_frontmatter_body_and_wikilinks(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            initialize_wiki(workspace)
            page_path = workspace / "wiki" / "pages" / "concepts" / "pump-failure.md"
            page_path.write_text(
                """---
title: Pump Failure
type: concept
tags: [failure, pump]
confidence: high
contradiction: false
---
# Pump Failure

Related to [[Motor Current|current signature]].
""",
                encoding="utf-8",
            )

            pages = load_wiki_pages(workspace)

        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page.title, "Pump Failure")
        self.assertEqual(page.page_type, "concept")
        self.assertEqual(page.tags, ["failure", "pump"])
        self.assertEqual(page.confidence, "high")
        self.assertFalse(page.contradiction)
        self.assertEqual(page.wikilinks, [("Motor Current", "current signature")])


class WikiLintTests(unittest.TestCase):
    def test_reports_missing_frontmatter_broken_links_orphans_and_metadata_issues(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            initialize_wiki(workspace)
            concepts = workspace / "wiki" / "pages" / "concepts"
            (concepts / "pump-failure.md").write_text(
                """---
title: Pump Failure
type: concept
tags: [failure]
confidence: high
contradiction: false
---
# Pump Failure

Related to [[Motor Current]].
""",
                encoding="utf-8",
            )
            (concepts / "orphan-page.md").write_text(
                """---
title: Orphan Page
type: concept
tags: []
confidence: medium
contradiction: false
---
# Orphan Page
""",
                encoding="utf-8",
            )
            (concepts / "missing-frontmatter.md").write_text(
                "# Missing Frontmatter\n",
                encoding="utf-8",
            )
            (concepts / "missing-confidence.md").write_text(
                """---
title: Missing Confidence
type: concept
tags: [metadata]
contradiction: false
---
# Missing Confidence
""",
                encoding="utf-8",
            )

            report = lint_wiki(workspace)

        codes = {(issue.code, issue.page, issue.target) for issue in report.issues}
        self.assertIn(("missing-frontmatter", "missing-frontmatter.md", None), codes)
        self.assertIn(("broken-wikilink", "pump-failure.md", "Motor Current"), codes)
        self.assertIn(("orphan-page", "orphan-page.md", None), codes)
        self.assertIn(("missing-metadata", "missing-confidence.md", "confidence"), codes)


class WikiRenderTests(unittest.TestCase):
    def test_renders_html_mirror_with_clickable_wikilinks_without_touching_raw_sources(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            initialize_wiki(workspace)
            raw_source = workspace / "wiki" / "raw-sources" / "source.txt"
            raw_source.write_text("immutable source", encoding="utf-8")
            concepts = workspace / "wiki" / "pages" / "concepts"
            (concepts / "pump-failure.md").write_text(
                """---
title: Pump Failure
type: concept
tags: [failure]
confidence: high
contradiction: false
---
# Pump Failure

Related to [[Motor Current|current signature]].
""",
                encoding="utf-8",
            )
            (concepts / "motor-current.md").write_text(
                """---
title: Motor Current
type: concept
tags: [signal]
confidence: medium
contradiction: false
---
# Motor Current
""",
                encoding="utf-8",
            )

            lint_wiki(workspace)
            result = render_html_mirror(workspace)
            render_graph_html(workspace)

            pump_html = workspace / "wiki" / "output" / "html" / "pump-failure.html"
            self.assertIn(pump_html, result.written_files)
            self.assertTrue(pump_html.is_file())
            html = pump_html.read_text(encoding="utf-8")
            raw_content = raw_source.read_text(encoding="utf-8")

        self.assertIn("<h1>Pump Failure</h1>", html)
        self.assertIn('<a href="motor-current.html">current signature</a>', html)
        self.assertEqual(raw_content, "immutable source")

    def test_renders_graph_html_with_nodes_edges_and_obsidian_like_style(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            initialize_wiki(workspace)
            concepts = workspace / "wiki" / "pages" / "concepts"
            (concepts / "pump-failure.md").write_text(
                """---
title: Pump Failure
type: concept
tags: [failure]
confidence: high
contradiction: false
---
# Pump Failure

Related to [[Motor Current]].
""",
                encoding="utf-8",
            )
            (concepts / "motor-current.md").write_text(
                """---
title: Motor Current
type: source
tags: [signal]
confidence: medium
contradiction: false
---
# Motor Current
""",
                encoding="utf-8",
            )

            result = render_graph_html(workspace)

            self.assertTrue(result.output_path.is_file())
            graph_html = result.output_path.read_text(encoding="utf-8")

        self.assertIn('"label": "Pump Failure"', graph_html)
        self.assertIn('"label": "Motor Current"', graph_html)
        self.assertIn('"from": "Pump Failure"', graph_html)
        self.assertIn('"to": "Motor Current"', graph_html)
        self.assertIn("#0d1117", graph_html)
        self.assertIn("source", graph_html)


if __name__ == "__main__":
    unittest.main()
