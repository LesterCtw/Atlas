from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from atlas.tool_catalog import format_tool_names


TEXTAREA_SELECTOR = 'textarea[name="chat-input-textarea"]'
NEW_CONVERSATION_SELECTOR = 'button:has-text("New Conversation")'
SIDEBAR_TOGGLE_SELECTOR = "svg.tabler-icon-layout-sidebar"
ATTACH_SELECTOR = 'button[data-tooltip-id="attach-button-tooltip"]'
SEND_SELECTOR = "button:has(svg.tabler-icon-circle-arrow-up-filled)"
STOP_GENERATING_SELECTOR = 'img[alt="stop icon"]'
REPLY_SELECTOR = "div.prose"


@dataclass(frozen=True)
class TgenieReadinessResult:
    ready: bool
    missing_selector: str | None = None


async def check_tgenie_chat_readiness(page: Any, *, timeout_ms: int = 1_500) -> TgenieReadinessResult:
    for selector in (TEXTAREA_SELECTOR, SEND_SELECTOR):
        try:
            await page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            return TgenieReadinessResult(ready=False, missing_selector=selector)
    return TgenieReadinessResult(ready=True)


async def is_tgenie_chat_ready(page: Any, *, timeout_ms: int = 1_500) -> bool:
    return (await check_tgenie_chat_readiness(page, timeout_ms=timeout_ms)).ready


def format_tgenie_readiness_issue(result: TgenieReadinessResult) -> str:
    if result.ready:
        return "tGenie chat UI is ready."
    return f"tGenie chat UI is not ready; missing selector: {result.missing_selector}"


class TgenieConversationClient(Protocol):
    async def send_single_turn(self, user_prompt: str) -> str:
        pass

    async def send_followup(self, message: str) -> str:
        pass

    async def attach_file(self, path: Path) -> None:
        pass


class TgenieConversationError(RuntimeError):
    pass


def build_atlas_bootstrap_prompt(user_prompt: str) -> str:
    cleaned_prompt = user_prompt.strip()
    if not cleaned_prompt:
        raise ValueError("User prompt is required.")

    return f"""You are tGenie running inside the Atlas agent harness.

Atlas is the local controller. You are operating through a browser UI and cannot directly read, write, or execute files on the user's machine.

When you need local workspace access or a local command, ask Atlas for either one single tool call or one read-only tool batch.

Use one fenced JSON block with this shape for a single tool call:

```json
{{
  "type": "atlas.tool_call",
  "tool": "tool.name",
  "args": {{}}
}}
```

Use one fenced JSON block with this shape for an independent read-only batch:

```json
{{
  "type": "atlas.tool_batch",
  "calls": [
    {{
      "id": "read-readme",
      "tool": "file.read",
      "args": {{"path": "README.md"}}
    }}
  ]
}}
```

Rules:
- The JSON `type` must be `atlas.tool_call` or `atlas.tool_batch`.
- A single tool call must include `tool` and `args`.
- `args` must be a JSON object.
- Request only one single tool call, or one `atlas.tool_batch`, per model response.
- `atlas.tool_batch` is only for independent read-only calls: `file.list`, `file.read`, and `file.search`.
- `atlas.tool_batch` can include at most 5 calls. Each call must include a unique string `id`.
- The batch limit is not an inspection limit. If a task requires more than 5 files, searches, or directories, continue with another useful batch or single tool call after Atlas returns the previous result.
- Do not put `file.write`, `shell.run`, or `file.attach` in a batch. Request those as a single `atlas.tool_call`.
- Do not claim that you have inspected, read, or understood local files unless Atlas provides file content, an attachment, or saved evidence in the conversation.
- Preserve useful observations from attachments as structured evidence, including source identity, observation, inference, uncertainty, confidence, and coordinates when available.
- Available tools include {format_tool_names()}.
- Use `file.attach` for workspace-local attachment paths ending in `.pdf`, `.jpg`, `.jpeg`, or `.png`, for example `{{"path": "docs/report.pdf"}}` or `{{"path": "photos/panel.png"}}`.

Completion discipline:
- Treat the user task as work to complete, not just a question to answer, when Atlas tools can safely move it forward.
- Before giving a final answer, keep requesting one useful single tool call or one useful read-only batch at a time until the task is complete, the next step requires a user decision, Atlas returns a blocking tool error, or no relevant safe check remains.
- For codebase tasks, inspect relevant files with `file.list`, `file.search`, and `file.read`; make the smallest needed `file.write` changes; then run targeted checks with `shell.run` when tests, lint, type checks, or build commands are discoverable.
- If a check fails and the fix is in scope, inspect the failure, update the files, and rerun the targeted check before the final answer.
- Do not ask the user for clarification before doing low-risk inspection that could clarify the task.
- Do not stop after the first file, first search result, or first tool result when an obvious next check remains. Use read-only batch when several independent reads or searches are useful.
- When the user asks you to inspect all relevant files or complete a codebase task, do not stop after one 5-call batch if more relevant files or checks remain. Continue until the relevant scope is covered, a blocking error occurs, or the next step needs a user decision.
- In the final answer, report what you changed or verified, which checks ran, and any concrete blocker or unverified part.

Atlas will send tool output back to you as an `atlas.tool_result` or `atlas.tool_batch_result` fenced JSON block in a later turn. Continue from that result when it arrives.

User task:
{cleaned_prompt}"""


class TgenieConversationAdapter:
    def __init__(
        self,
        page: Any,
        *,
        timeout_ms: int = 30_000,
        generation_timeout_ms: int = 180_000,
        stop_start_timeout_ms: int = 2_000,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self.page = page
        self.timeout_ms = timeout_ms
        self.generation_timeout_ms = generation_timeout_ms
        self.stop_start_timeout_ms = stop_start_timeout_ms
        self.poll_interval_seconds = poll_interval_seconds

    async def send_single_turn(self, user_prompt: str) -> str:
        return await self.send_single_turn_with_attachments(user_prompt=user_prompt, attachments=())

    async def send_followup(self, message: str) -> str:
        return await self._send_message(message)

    async def attach_file(self, path: Path) -> None:
        await self._attach_files((path,))

    async def send_single_turn_with_attachments(
        self,
        user_prompt: str,
        attachments: Sequence[Path],
        *,
        start_new_conversation: bool = False,
    ) -> str:
        prompt = build_atlas_bootstrap_prompt(user_prompt)
        textarea = self._textarea()

        await self._wait_visible(textarea, "prompt textarea", TEXTAREA_SELECTOR)
        if start_new_conversation:
            await self._open_new_conversation()
            await self._wait_visible(textarea, "prompt textarea", TEXTAREA_SELECTOR)

        if attachments:
            await self._attach_files(attachments)

        return await self._send_message(prompt)

    async def _send_message(self, message: str) -> str:
        textarea = self._textarea()
        reply_locator = self.page.locator(REPLY_SELECTOR)
        previous_reply_count = await self._safe_count(reply_locator)
        previous_reply_text = await self._latest_reply_text(default="")

        await self._wait_visible(textarea, "prompt textarea", TEXTAREA_SELECTOR)
        await self._run_step("fill prompt textarea", textarea.fill(message))

        send_button = self._send_button()
        await self._wait_visible(send_button, "send button", SEND_SELECTOR)
        await self._run_step("click send button", send_button.click())

        await self._wait_for_generation_to_finish()
        await self._wait_for_reply_change(previous_reply_count, previous_reply_text)
        return await self._latest_reply_text()

    async def _open_new_conversation(self) -> None:
        new_conversation = self._new_conversation()
        if not await self._is_visible(new_conversation):
            sidebar_toggle = self._sidebar_toggle()
            await self._wait_visible(sidebar_toggle, "sidebar toggle", SIDEBAR_TOGGLE_SELECTOR)
            await self._run_step("open sidebar", sidebar_toggle.click())
            await self._wait_visible(new_conversation, "new conversation button", NEW_CONVERSATION_SELECTOR)

        await self._run_step("click new conversation button", new_conversation.click())

    async def _attach_files(self, attachments: Sequence[Path]) -> None:
        attach_button = self._attach_button()
        await self._wait_visible(attach_button, "attach button", ATTACH_SELECTOR)

        for attachment in attachments:
            file_path = Path(attachment)
            async with self.page.expect_file_chooser() as chooser_info:
                await self._run_step("click attach button", attach_button.click())
            file_chooser = await chooser_info.value
            await self._run_step("set attach file", file_chooser.set_files(str(file_path)))
            success_text = self.page.get_by_text(file_path.name, exact=False)
            await self._wait_visible(success_text, "attached file name", file_path.name)

    async def _wait_for_generation_to_finish(self) -> None:
        stop_icon = self._stop_generating()
        stop_seen = await self._wait_visible_or_false(
            stop_icon,
            timeout_ms=self.stop_start_timeout_ms,
        )
        if not stop_seen:
            return

        try:
            await stop_icon.wait_for(state="hidden", timeout=self.generation_timeout_ms)
        except Exception as error:
            raise TgenieConversationError(
                f"Timed out waiting for tGenie generation to finish via selector: {STOP_GENERATING_SELECTOR}"
            ) from error

    async def _wait_for_reply_change(self, previous_count: int, previous_text: str) -> None:
        deadline = asyncio.get_running_loop().time() + (self.generation_timeout_ms / 1000)
        reply_locator = self.page.locator(REPLY_SELECTOR)
        while asyncio.get_running_loop().time() < deadline:
            current_count = await self._safe_count(reply_locator)
            current_text = await self._latest_reply_text(default="")
            if current_text and (current_count > previous_count or current_text != previous_text):
                return
            await asyncio.sleep(self.poll_interval_seconds)

        raise TgenieConversationError(f"Timed out waiting for latest tGenie reply via selector: {REPLY_SELECTOR}")

    async def _latest_reply_text(self, default: str | None = None) -> str:
        reply = self.page.locator(REPLY_SELECTOR).last
        try:
            await reply.wait_for(state="visible", timeout=self.timeout_ms)
            text = await reply.inner_text()
        except Exception as error:
            if default is not None:
                return default
            raise TgenieConversationError(f"Could not read latest tGenie reply via selector: {REPLY_SELECTOR}") from error

        cleaned_text = text.strip()
        if not cleaned_text and default is None:
            raise TgenieConversationError(f"Latest tGenie reply was empty via selector: {REPLY_SELECTOR}")
        return cleaned_text

    async def _wait_visible(self, locator: Any, label: str, selector: str) -> None:
        try:
            await locator.wait_for(state="visible", timeout=self.timeout_ms)
        except Exception as error:
            raise TgenieConversationError(f"Could not find tGenie {label} with selector: {selector}") from error

    async def _wait_visible_or_false(self, locator: Any, *, timeout_ms: int) -> bool:
        try:
            await locator.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            return False
        return True

    async def _is_visible(self, locator: Any) -> bool:
        try:
            return bool(await locator.is_visible(timeout=1_000))
        except Exception:
            return False

    async def _safe_count(self, locator: Any) -> int:
        try:
            return int(await locator.count())
        except Exception:
            return 0

    async def _run_step(self, label: str, operation: Any) -> None:
        try:
            await operation
        except Exception as error:
            raise TgenieConversationError(f"tGenie adapter failed to {label}: {error}") from error

    def _textarea(self) -> Any:
        return self.page.locator(TEXTAREA_SELECTOR).first

    def _new_conversation(self) -> Any:
        return self.page.locator(NEW_CONVERSATION_SELECTOR).first

    def _sidebar_toggle(self) -> Any:
        return self.page.locator(SIDEBAR_TOGGLE_SELECTOR).first

    def _attach_button(self) -> Any:
        return self.page.locator(ATTACH_SELECTOR).first

    def _send_button(self) -> Any:
        return self.page.locator(SEND_SELECTOR).first

    def _stop_generating(self) -> Any:
        return self.page.locator(STOP_GENERATING_SELECTOR).first
