from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.shell_policy import classify_shell_command
from atlas.workspace_paths import (
    WorkspacePathError,
    is_within_workspace,
    resolve_workspace_path,
    workspace_relative_path,
)


ALLOWED_ATTACHMENT_SUFFIXES = frozenset({".pdf", ".jpg", ".jpeg", ".png"})
ALLOWED_ATTACHMENT_SUFFIXES_TEXT = ".pdf, .jpg, .jpeg, or .png"
DEFAULT_MAX_READ_BYTES = 1_000_000
DEFAULT_MAX_SEARCH_FILE_BYTES = 1_000_000
DEFAULT_MAX_SEARCH_MATCHES = 200
DEFAULT_SHELL_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "data": self.data,
            "error": self.error,
        }


@dataclass(frozen=True)
class FileAttachment:
    path: Path
    relative_path: str


PdfAttachment = FileAttachment


class ToolRuntime:
    def __init__(
        self,
        workspace: Path,
        *,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_search_file_bytes: int = DEFAULT_MAX_SEARCH_FILE_BYTES,
        max_search_matches: int = DEFAULT_MAX_SEARCH_MATCHES,
        shell_timeout_seconds: float = DEFAULT_SHELL_TIMEOUT_SECONDS,
    ) -> None:
        self.workspace = workspace.resolve()
        self.max_read_bytes = max_read_bytes
        self.max_search_file_bytes = max_search_file_bytes
        self.max_search_matches = max_search_matches
        self.shell_timeout_seconds = shell_timeout_seconds

    def run(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        try:
            if tool_name == "file.write":
                return self._write_file(args)
            if tool_name == "file.read":
                return self._read_file(args)
            if tool_name == "file.list":
                return self._list_files(args)
            if tool_name == "file.search":
                return self._search_files(args)
            if tool_name == "shell.run":
                return self._run_shell(args)
            return ToolResult(
                ok=False,
                status="error",
                error=f"Unknown tool: {tool_name}",
            )
        except ToolRuntimeError as error:
            return ToolResult(ok=False, status="error", error=str(error))
        except FileNotFoundError:
            return ToolResult(ok=False, status="error", error="File not found.")
        except IsADirectoryError:
            return ToolResult(ok=False, status="error", error="Path is a directory, not a text file.")
        except UnicodeDecodeError:
            return ToolResult(ok=False, status="error", error="File is not readable as UTF-8 text.")
        except KeyError as error:
            return ToolResult(ok=False, status="error", error=f"Missing tool argument: {error.args[0]}.")
        except subprocess.TimeoutExpired as error:
            return ToolResult(
                ok=False,
                status="timeout",
                data={"command": str(error.cmd)},
                error="Shell command timed out.",
            )
        except OSError as error:
            return ToolResult(ok=False, status="error", error=f"File operation failed: {error}")

    def _resolve_workspace_path(self, raw_path: str) -> Path:
        try:
            return resolve_workspace_path(self.workspace, raw_path)
        except WorkspacePathError as exc:
            raise ToolRuntimeError(str(exc)) from exc

    def _relative_path(self, path: Path) -> str:
        return workspace_relative_path(self.workspace, path)

    def prepare_file_attachment(self, args: dict[str, Any]) -> FileAttachment:
        path = self._resolve_workspace_path(str(args["path"]))
        if path.suffix.lower() not in ALLOWED_ATTACHMENT_SUFFIXES:
            raise ToolRuntimeError(f"Attachment only accepts {ALLOWED_ATTACHMENT_SUFFIXES_TEXT} files.")
        if not path.exists():
            raise FileNotFoundError
        if path.is_dir():
            raise IsADirectoryError
        return FileAttachment(path=path, relative_path=self._relative_path(path))

    def prepare_pdf_attachment(self, args: dict[str, Any]) -> PdfAttachment:
        path = self._resolve_workspace_path(str(args["path"]))
        if path.suffix.lower() != ".pdf":
            raise ToolRuntimeError("PDF attach only accepts .pdf files.")
        if not path.exists():
            raise FileNotFoundError
        if path.is_dir():
            raise IsADirectoryError
        return PdfAttachment(path=path, relative_path=self._relative_path(path))

    def _write_file(self, args: dict[str, Any]) -> ToolResult:
        path = self._resolve_workspace_path(str(args["path"]))
        content = str(args["content"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(
            ok=True,
            status="ok",
            data={"path": self._relative_path(path), "bytes": len(content.encode("utf-8"))},
        )

    def _read_file(self, args: dict[str, Any]) -> ToolResult:
        path = self._resolve_workspace_path(str(args["path"]))
        if path.stat().st_size > self.max_read_bytes:
            raise ToolRuntimeError(f"File is too large to read. Maximum size is {self.max_read_bytes} bytes.")
        return ToolResult(
            ok=True,
            status="ok",
            data={"path": self._relative_path(path), "content": path.read_text(encoding="utf-8")},
        )

    def _list_files(self, args: dict[str, Any]) -> ToolResult:
        path = self._resolve_workspace_path(str(args.get("path", ".")))
        entries = []
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            entries.append(
                {
                    "path": self._relative_path(child),
                    "type": "directory" if child.is_dir() else "file",
                }
            )
        return ToolResult(ok=True, status="ok", data={"path": self._relative_path(path), "entries": entries})

    def _search_files(self, args: dict[str, Any]) -> ToolResult:
        query = str(args["query"])
        root = self._resolve_workspace_path(str(args.get("path", ".")))
        matches = []
        truncated = False
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if not is_within_workspace(self.workspace, path):
                continue
            if query in path.name:
                matches.append(
                    {
                        "path": self._relative_path(path),
                        "line": None,
                        "text": "",
                    }
                )
                if len(matches) >= self.max_search_matches:
                    truncated = True
                    break
                continue
            if path.stat().st_size > self.max_search_file_bytes:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for index, line in enumerate(lines, start=1):
                if query in line:
                    matches.append(
                        {
                            "path": self._relative_path(path),
                            "line": index,
                            "text": line,
                        }
                    )
                    if len(matches) >= self.max_search_matches:
                        truncated = True
                        break
            if truncated:
                break
        return ToolResult(ok=True, status="ok", data={"query": query, "matches": matches, "truncated": truncated})

    def _run_shell(self, args: dict[str, Any]) -> ToolResult:
        command = str(args["command"])
        decision = classify_shell_command(command)
        if decision == "confirm":
            return ToolResult(
                ok=False,
                status="confirmation-required",
                data={"command": command},
                error="Shell command requires user confirmation.",
            )
        if decision == "reject":
            return ToolResult(
                ok=False,
                status="rejected",
                data={"command": command},
                error="Shell command rejected by safety policy.",
            )
        completed = subprocess.run(
            command,
            cwd=self.workspace,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=self.shell_timeout_seconds,
        )
        return ToolResult(
            ok=True,
            status="ok",
            data={
                "command": command,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "exit_code": completed.returncode,
            },
        )
class ToolRuntimeError(Exception):
    pass
