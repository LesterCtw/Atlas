from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from atlas.tgenie_adapter import (
    ATTACH_SELECTOR,
    NEW_CONVERSATION_SELECTOR,
    REPLY_SELECTOR,
    SEND_SELECTOR,
    SIDEBAR_TOGGLE_SELECTOR,
    STOP_GENERATING_SELECTOR,
    TEXTAREA_SELECTOR,
    TgenieConversationAdapter,
    build_atlas_bootstrap_prompt,
)


class FakeLocator:
    def __init__(
        self,
        selector: str,
        *,
        visible: bool = True,
        on_click: Any | None = None,
        count_fn: Any | None = None,
        text_fn: Any | None = None,
    ) -> None:
        self.selector = selector
        self.visible = visible
        self.on_click = on_click
        self.count_fn = count_fn
        self.text_fn = text_fn
        self.clicks = 0
        self.filled_values: list[str] = []
        self.waits: list[tuple[str, int]] = []
        self.first_count = 0
        self.last_count = 0

    @property
    def first(self) -> "FakeLocator":
        self.first_count += 1
        return self

    @property
    def last(self) -> "FakeLocator":
        self.last_count += 1
        return self

    async def wait_for(self, *, state: str, timeout: int) -> None:
        self.waits.append((state, timeout))
        if state == "visible" and not self.visible:
            raise TimeoutError(f"{self.selector} is not visible")
        if state == "hidden":
            self.visible = False

    async def is_visible(self, *, timeout: int) -> bool:
        return self.visible

    async def fill(self, value: str) -> None:
        self.filled_values.append(value)

    async def click(self) -> None:
        self.clicks += 1
        if self.on_click is not None:
            self.on_click()

    async def count(self) -> int:
        if self.count_fn is None:
            return 1 if self.visible else 0
        return int(self.count_fn())

    async def inner_text(self) -> str:
        if self.text_fn is None:
            return ""
        return str(self.text_fn())


class FakeFileChooser:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    async def set_files(self, file_path: str) -> None:
        self.page.attached_file_names.append(Path(file_path).name)


class FakeFileChooserContext:
    def __init__(self, page: "FakePage") -> None:
        self._file_chooser = FakeFileChooser(page)
        self.value = self._value()

    async def _value(self) -> FakeFileChooser:
        return self._file_chooser

    async def __aenter__(self) -> "FakeFileChooserContext":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakePage:
    def __init__(self, *, new_conversation_visible: bool = True, stop_visible: bool = False) -> None:
        self.replies: list[str] = []
        self.attached_file_names: list[str] = []
        self.locators: dict[str, FakeLocator] = {}
        self.locators[TEXTAREA_SELECTOR] = FakeLocator(TEXTAREA_SELECTOR)
        self.locators[NEW_CONVERSATION_SELECTOR] = FakeLocator(
            NEW_CONVERSATION_SELECTOR,
            visible=new_conversation_visible,
        )
        self.locators[SIDEBAR_TOGGLE_SELECTOR] = FakeLocator(
            SIDEBAR_TOGGLE_SELECTOR,
            on_click=lambda: self._set_visible(NEW_CONVERSATION_SELECTOR, True),
        )
        self.locators[ATTACH_SELECTOR] = FakeLocator(ATTACH_SELECTOR)
        self.locators[SEND_SELECTOR] = FakeLocator(SEND_SELECTOR, on_click=lambda: self.replies.append("atlas-ok"))
        self.locators[STOP_GENERATING_SELECTOR] = FakeLocator(STOP_GENERATING_SELECTOR, visible=stop_visible)
        self.locators[REPLY_SELECTOR] = FakeLocator(
            REPLY_SELECTOR,
            count_fn=lambda: len(self.replies),
            text_fn=lambda: self.replies[-1],
        )

    def _set_visible(self, selector: str, visible: bool) -> None:
        self.locators[selector].visible = visible

    def locator(self, selector: str) -> FakeLocator:
        return self.locators[selector]

    def get_by_text(self, text: str, *, exact: bool) -> FakeLocator:
        return FakeLocator(
            f"text={text}",
            visible=any(text in file_name for file_name in self.attached_file_names),
        )

    def expect_file_chooser(self) -> FakeFileChooserContext:
        return FakeFileChooserContext(self)


class TgenieAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_bootstrap_prompt_explains_atlas_tool_protocol(self) -> None:
        prompt = build_atlas_bootstrap_prompt("Summarize README.md")

        self.assertIn("Atlas agent harness", prompt)
        self.assertIn("cannot directly read, write, or execute files", prompt)
        self.assertIn('"type": "atlas.tool_call"', prompt)
        self.assertIn('"tool": "tool.name"', prompt)
        self.assertIn('"args": {}', prompt)
        self.assertIn("Request only one tool call at a time", prompt)
        self.assertIn("atlas.tool_result", prompt)
        self.assertIn("Summarize README.md", prompt)

    async def test_adapter_sends_prompt_in_current_conversation_by_default(self) -> None:
        page = FakePage(new_conversation_visible=False, stop_visible=False)
        adapter = TgenieConversationAdapter(page, stop_start_timeout_ms=1, poll_interval_seconds=0)

        reply = await adapter.send_single_turn("Atlas smoke test.")

        self.assertEqual(reply, "atlas-ok")
        self.assertEqual(page.locators[SIDEBAR_TOGGLE_SELECTOR].clicks, 0)
        self.assertEqual(page.locators[NEW_CONVERSATION_SELECTOR].clicks, 0)
        self.assertEqual(page.locators[SEND_SELECTOR].clicks, 1)
        self.assertGreater(page.locators[TEXTAREA_SELECTOR].first_count, 0)
        self.assertGreater(page.locators[SEND_SELECTOR].first_count, 0)
        self.assertGreater(page.locators[REPLY_SELECTOR].last_count, 0)
        sent_prompt = page.locators[TEXTAREA_SELECTOR].filled_values[0]
        self.assertIn("Atlas agent harness", sent_prompt)
        self.assertIn("Atlas smoke test.", sent_prompt)

    async def test_adapter_can_start_new_conversation_when_requested(self) -> None:
        page = FakePage(new_conversation_visible=False, stop_visible=False)
        adapter = TgenieConversationAdapter(page, stop_start_timeout_ms=1, poll_interval_seconds=0)

        reply = await adapter.send_single_turn_with_attachments(
            user_prompt="Start clean.",
            attachments=(),
            start_new_conversation=True,
        )

        self.assertEqual(reply, "atlas-ok")
        self.assertEqual(page.locators[SIDEBAR_TOGGLE_SELECTOR].clicks, 1)
        self.assertEqual(page.locators[NEW_CONVERSATION_SELECTOR].clicks, 1)

    async def test_adapter_waits_for_stop_icon_to_disappear_when_generation_is_visible(self) -> None:
        page = FakePage(stop_visible=True)
        adapter = TgenieConversationAdapter(page, stop_start_timeout_ms=1, poll_interval_seconds=0)

        await adapter.send_single_turn("Wait for completion.")

        self.assertIn(("visible", 1), page.locators[STOP_GENERATING_SELECTOR].waits)
        self.assertIn(("hidden", 180_000), page.locators[STOP_GENERATING_SELECTOR].waits)

    async def test_adapter_attaches_files_and_waits_for_file_name(self) -> None:
        page = FakePage()
        adapter = TgenieConversationAdapter(page, stop_start_timeout_ms=1, poll_interval_seconds=0)

        reply = await adapter.send_single_turn_with_attachments(
            user_prompt="Read this file.",
            attachments=(Path("/tmp/report.pdf"),),
        )

        self.assertEqual(reply, "atlas-ok")
        self.assertEqual(page.attached_file_names, ["report.pdf"])
        self.assertEqual(page.locators[ATTACH_SELECTOR].clicks, 1)


if __name__ == "__main__":
    unittest.main()
