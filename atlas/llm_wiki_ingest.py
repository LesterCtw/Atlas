from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atlas.commands import format_skill_instructions
from atlas.skills import SkillLoader
from atlas.tgenie_tool_loop import TgenieToolConversation, run_tgenie_tool_loop
from atlas.tool_runtime import PdfAttachment, ToolRuntime, ToolRuntimeError
from atlas.workspace_paths import WorkspacePathError, resolve_workspace_path
from atlas.wiki import initialize_wiki, render_graph_html, render_html_mirror


@dataclass(frozen=True)
class LlmWikiIngestResult:
    final_response: str | None
    status_events: list[str]
    ingested_paths: list[str]
    failed_paths: list[str]
    error: str | None = None


class LlmWikiIngestError(Exception):
    pass


async def run_llm_wiki_ingest(
    *,
    workspace: Path,
    requested_path: str,
    conversation: TgenieToolConversation,
) -> LlmWikiIngestResult:
    runtime = ToolRuntime(workspace)
    attachments = collect_ingest_pdfs(runtime, requested_path)
    initialize_wiki(runtime.workspace)

    status_events: list[str] = ["validating-ingest-path"]
    final_response: str | None = None
    ingested_paths: list[str] = []
    failed_paths: list[str] = []
    error_message: str | None = None
    for attachment in attachments:
        status_events.append("starting-ingest-batch")
        prompt = build_llm_wiki_ingest_prompt(
            workspace=runtime.workspace,
            source_paths=[attachment.relative_path],
            batch_size=1,
        )
        try:
            tool_loop_result = await run_tgenie_tool_loop(
                initial_prompt=prompt,
                conversation=conversation,
                tool_runtime=runtime,
            )
        except Exception as error:
            failed_paths.append(attachment.relative_path)
            error_message = f"{attachment.relative_path}: {error}"
            status_events.append("ingest-batch-failed")
            break
        status_events.extend(tool_loop_result.status_events)
        status_events.append("ingest-batch-completed")
        ingested_paths.append(attachment.relative_path)
        final_response = tool_loop_result.final_response

    status_events.append("rendering-html")
    render_html_mirror(runtime.workspace)
    status_events.append("rendering-graph")
    render_graph_html(runtime.workspace)

    return LlmWikiIngestResult(
        final_response=final_response,
        status_events=status_events,
        ingested_paths=ingested_paths,
        failed_paths=failed_paths,
        error=error_message,
    )


def build_llm_wiki_ingest_prompt(*, workspace: Path, source_paths: list[str], batch_size: int) -> str:
    skill = SkillLoader(workspace).load("llm-wiki")
    source_list = "\n".join(f"- {path}" for path in source_paths)
    return (
        f"{format_skill_instructions(skill)}\n\n"
        "Atlas task: /llm-wiki ingest "
        f"{' '.join(source_paths)}\n\n"
        f"Conservative batch metadata: batch-size: {batch_size}\n\n"
        "Ingest the following workspace-local PDF source into the LLM Wiki:\n"
        f"{source_list}\n\n"
        "Required behavior:\n"
        "- Request `pdf.attach` for the source PDF before reading or summarizing it.\n"
        "- Update wiki pages under `wiki/pages/`, plus `wiki/index.md` and `wiki/log.md`.\n"
        "- Preserve source traceability in generated Markdown so readers can identify the originating PDF.\n"
        "- Use Atlas file tools to write every wiki change.\n"
        "- Finish with a concise summary of what changed.\n"
    )


def collect_ingest_pdfs(runtime: ToolRuntime, requested_path: str) -> list[PdfAttachment]:
    candidate = resolve_workspace_input(runtime, requested_path)
    if candidate.is_dir():
        attachments = [
            runtime.prepare_pdf_attachment({"path": path.relative_to(runtime.workspace).as_posix()})
            for path in sorted(candidate.iterdir(), key=lambda item: item.name)
            if path.is_file() and path.suffix.lower() == ".pdf"
        ]
        if not attachments:
            raise LlmWikiIngestError("PDF directory contains no .pdf files.")
        return attachments
    return [prepare_ingest_pdf(runtime, requested_path)]


def resolve_workspace_input(runtime: ToolRuntime, requested_path: str) -> Path:
    try:
        resolved = resolve_workspace_path(runtime.workspace, requested_path)
    except WorkspacePathError as error:
        raise LlmWikiIngestError(str(error)) from error
    if not resolved.exists():
        raise LlmWikiIngestError("PDF path not found.")
    return resolved


def prepare_ingest_pdf(runtime: ToolRuntime, requested_path: str) -> PdfAttachment:
    try:
        return runtime.prepare_pdf_attachment({"path": requested_path})
    except ToolRuntimeError as error:
        raise LlmWikiIngestError(str(error)) from error
    except FileNotFoundError as error:
        raise LlmWikiIngestError("PDF file not found.") from error
    except IsADirectoryError as error:
        raise LlmWikiIngestError("Path is a directory, not a PDF file.") from error
    except KeyError as error:
        raise LlmWikiIngestError("PDF path is required.") from error
