from __future__ import annotations

import unittest
from pathlib import Path

from atlas.wiki_markup import (
    extract_wikilinks,
    parse_frontmatter,
    render_inline_markdown,
    slug,
    title_from_path,
)


class WikiMarkupTests(unittest.TestCase):
    def test_extracts_wikilinks_with_aliases(self) -> None:
        self.assertEqual(
            extract_wikilinks("See [[Pump Failure]] and [[Motor Current|current signature]]."),
            [
                ("Pump Failure", "Pump Failure"),
                ("Motor Current", "current signature"),
            ],
        )

    def test_parses_frontmatter_values_and_body(self) -> None:
        metadata, body = parse_frontmatter(
            """---
title: Pump Failure
tags: [failure, "pump"]
contradiction: false
---
# Pump Failure
"""
        )

        self.assertEqual(metadata["title"], "Pump Failure")
        self.assertEqual(metadata["tags"], ["failure", "pump"])
        self.assertFalse(metadata["contradiction"])
        self.assertEqual(body, "# Pump Failure\n")

    def test_returns_empty_metadata_when_frontmatter_is_missing_or_open(self) -> None:
        self.assertEqual(parse_frontmatter("# Title\n"), ({}, "# Title\n"))
        self.assertEqual(parse_frontmatter("---\ntitle: Open\n"), ({}, "---\ntitle: Open\n"))

    def test_renders_inline_markdown_with_wikilinks_and_html_escape(self) -> None:
        rendered = render_inline_markdown(
            "Use <safe> [[Motor Current|current signature]] and [[Missing Page]].",
            {"Motor Current": "motor-current"},
        )

        self.assertEqual(
            rendered,
            'Use &lt;safe&gt; <a href="motor-current.html">current signature</a> '
            'and <a href="missing-page.html">Missing Page</a>.',
        )

    def test_slug_and_title_from_path(self) -> None:
        self.assertEqual(slug("Pump Failure!"), "pump-failure")
        self.assertEqual(slug("!!!"), "page")
        self.assertEqual(title_from_path(Path("pump-failure.md")), "Pump Failure")


if __name__ == "__main__":
    unittest.main()
