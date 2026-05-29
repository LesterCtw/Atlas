from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.llm_wiki_ingest import LlmWikiIngestError, run_llm_wiki_ingest


class FakeIngestConversation:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.sent_messages: list[str] = []
        self.attached_pdfs: list[Path] = []

    async def send_single_turn(self, user_prompt: str) -> str:
        self.sent_messages.append(user_prompt)
        return self.responses.pop(0)

    async def send_followup(self, message: str) -> str:
        self.sent_messages.append(message)
        return self.responses.pop(0)

    async def attach_pdf(self, path: Path) -> None:
        self.attached_pdfs.append(path)


class FailingSecondBatchConversation(FakeIngestConversation):
    async def send_single_turn(self, user_prompt: str) -> str:
        if len([message for message in self.sent_messages if "/llm-wiki ingest" in message]) == 1:
            self.sent_messages.append(user_prompt)
            raise RuntimeError("tGenie stopped during batch")
        return await super().send_single_turn(user_prompt)


class LlmWikiIngestTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_pdf_ingestion_attaches_pdf_writes_wiki_and_renders_outputs(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            pdf_path = workspace / "docs" / "case.pdf"
            pdf_path.parent.mkdir()
            pdf_path.write_bytes(b"%PDF-1.4\n")
            conversation = FakeIngestConversation(
                responses=[
                    """```json
{"type": "atlas.tool_call", "tool": "pdf.attach", "args": {"path": "docs/case.pdf"}}
```""",
                    """```json
{"type": "atlas.tool_call", "tool": "file.write", "args": {"path": "wiki/pages/sources/case-report.md", "content": "---\\ntitle: Case Report\\ntype: source\\ntags: [pdf]\\nconfidence: high\\ncontradiction: false\\nsource: docs/case.pdf\\n---\\n# Case Report\\n\\nSource PDF: docs/case.pdf\\n"}}
```""",
                    """```json
{"type": "atlas.tool_call", "tool": "file.write", "args": {"path": "wiki/index.md", "content": "# LLM Wiki Index\\n\\n- [[Case Report]] - source: docs/case.pdf\\n"}}
```""",
                    """```json
{"type": "atlas.tool_call", "tool": "file.write", "args": {"path": "wiki/log.md", "content": "# LLM Wiki Log\\n\\n- Ingested docs/case.pdf into [[Case Report]].\\n"}}
```""",
                    "Ingested docs/case.pdf into the LLM Wiki.",
                ]
            )

            result = await run_llm_wiki_ingest(
                workspace=workspace,
                requested_path="docs/case.pdf",
                conversation=conversation,
            )

            source_page = workspace / "wiki" / "pages" / "sources" / "case-report.md"
            html_index = workspace / "wiki" / "output" / "html" / "index.html"
            graph_html = workspace / "wiki" / "output" / "graph" / "index.html"

            self.assertEqual(result.final_response, "Ingested docs/case.pdf into the LLM Wiki.")
            self.assertEqual(result.ingested_paths, ["docs/case.pdf"])
            self.assertIn("rendering-html", result.status_events)
            self.assertIn("rendering-graph", result.status_events)
            self.assertEqual(conversation.attached_pdfs, [pdf_path.resolve()])
            self.assertTrue(source_page.is_file())
            self.assertIn("source: docs/case.pdf", source_page.read_text(encoding="utf-8"))
            self.assertIn("# LLM Wiki Index", (workspace / "wiki" / "index.md").read_text(encoding="utf-8"))
            self.assertIn("Ingested docs/case.pdf", (workspace / "wiki" / "log.md").read_text(encoding="utf-8"))
            self.assertTrue(html_index.is_file())
            self.assertTrue(graph_html.is_file())
            self.assertIn('<atlas.skill_instructions name="llm-wiki">', conversation.sent_messages[0])
            self.assertIn("/llm-wiki ingest docs/case.pdf", conversation.sent_messages[0])
            self.assertIn("source traceability", conversation.sent_messages[0])

    async def test_single_pdf_ingestion_rejects_invalid_paths_before_tgenie_runs(self) -> None:
        cases = {
            "non-pdf": ("docs/case.txt", "only accepts .pdf"),
            "missing-pdf": ("docs/missing.pdf", "not found"),
            "workspace-escape": ("../outside.pdf", "workspace"),
        }

        for case_name, (requested_path, expected_message) in cases.items():
            with self.subTest(case_name=case_name):
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    workspace = root / "workspace"
                    workspace.mkdir()
                    (workspace / "docs").mkdir()
                    (workspace / "docs" / "case.txt").write_text("not a pdf", encoding="utf-8")
                    (root / "outside.pdf").write_bytes(b"%PDF-1.4\n")
                    conversation = FakeIngestConversation(responses=[])

                    with self.assertRaises(LlmWikiIngestError) as caught:
                        await run_llm_wiki_ingest(
                            workspace=workspace,
                            requested_path=requested_path,
                            conversation=conversation,
                        )

                self.assertIn(expected_message, str(caught.exception))
                self.assertEqual(conversation.sent_messages, [])
                self.assertEqual(conversation.attached_pdfs, [])

    async def test_directory_ingestion_processes_workspace_pdfs_one_at_a_time(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            docs = workspace / "docs"
            docs.mkdir()
            (docs / "b.pdf").write_bytes(b"%PDF-1.4\nb")
            (docs / "a.pdf").write_bytes(b"%PDF-1.4\na")
            (docs / "notes.txt").write_text("ignore me", encoding="utf-8")
            conversation = FakeIngestConversation(
                responses=[
                    """```json
{"type": "atlas.tool_call", "tool": "pdf.attach", "args": {"path": "docs/a.pdf"}}
```""",
                    """```json
{"type": "atlas.tool_call", "tool": "file.write", "args": {"path": "wiki/pages/sources/a.md", "content": "---\\ntitle: A Source\\ntype: source\\ntags: [pdf]\\nconfidence: high\\ncontradiction: false\\nsource: docs/a.pdf\\n---\\n# A Source\\n\\nSource PDF: docs/a.pdf\\n"}}
```""",
                    "Finished docs/a.pdf.",
                    """```json
{"type": "atlas.tool_call", "tool": "pdf.attach", "args": {"path": "docs/b.pdf"}}
```""",
                    """```json
{"type": "atlas.tool_call", "tool": "file.write", "args": {"path": "wiki/pages/sources/b.md", "content": "---\\ntitle: B Source\\ntype: source\\ntags: [pdf]\\nconfidence: high\\ncontradiction: false\\nsource: docs/b.pdf\\n---\\n# B Source\\n\\nSource PDF: docs/b.pdf\\n"}}
```""",
                    "Finished docs/b.pdf.",
                ]
            )

            result = await run_llm_wiki_ingest(
                workspace=workspace,
                requested_path="docs",
                conversation=conversation,
            )

            self.assertEqual(result.ingested_paths, ["docs/a.pdf", "docs/b.pdf"])
            self.assertEqual(conversation.attached_pdfs, [(docs / "a.pdf").resolve(), (docs / "b.pdf").resolve()])
            self.assertTrue((workspace / "wiki" / "pages" / "sources" / "a.md").is_file())
            self.assertTrue((workspace / "wiki" / "pages" / "sources" / "b.md").is_file())
            self.assertEqual(conversation.sent_messages[0].count("/llm-wiki ingest docs/a.pdf"), 1)
            self.assertEqual(conversation.sent_messages[3].count("/llm-wiki ingest docs/b.pdf"), 1)
            self.assertIn("batch-size: 1", conversation.sent_messages[0])
            self.assertIn("batch-size: 1", conversation.sent_messages[3])

    async def test_directory_ingestion_keeps_completed_outputs_when_a_later_batch_fails(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            docs = workspace / "docs"
            docs.mkdir()
            (docs / "a.pdf").write_bytes(b"%PDF-1.4\na")
            (docs / "b.pdf").write_bytes(b"%PDF-1.4\nb")
            conversation = FailingSecondBatchConversation(
                responses=[
                    """```json
{"type": "atlas.tool_call", "tool": "pdf.attach", "args": {"path": "docs/a.pdf"}}
```""",
                    """```json
{"type": "atlas.tool_call", "tool": "file.write", "args": {"path": "wiki/pages/sources/a.md", "content": "---\\ntitle: A Source\\ntype: source\\ntags: [pdf]\\nconfidence: high\\ncontradiction: false\\nsource: docs/a.pdf\\n---\\n# A Source\\n\\nSource PDF: docs/a.pdf\\n"}}
```""",
                    "Finished docs/a.pdf.",
                ]
            )

            result = await run_llm_wiki_ingest(
                workspace=workspace,
                requested_path="docs",
                conversation=conversation,
            )

            self.assertEqual(result.ingested_paths, ["docs/a.pdf"])
            self.assertEqual(result.failed_paths, ["docs/b.pdf"])
            self.assertIn("tGenie stopped during batch", result.error or "")
            self.assertIn("ingest-batch-failed", result.status_events)
            self.assertTrue((workspace / "wiki" / "pages" / "sources" / "a.md").is_file())
            self.assertTrue((workspace / "wiki" / "output" / "html" / "index.html").is_file())
            self.assertTrue((workspace / "wiki" / "output" / "graph" / "index.html").is_file())
            self.assertFalse((workspace / "wiki" / "pages" / "sources" / "b.md").exists())


if __name__ == "__main__":
    unittest.main()
