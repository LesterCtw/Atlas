from __future__ import annotations

import html
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from atlas.fake_loop import FakeTgenieAdapter
from atlas.tgenie_adapter import TgenieConversationError
from atlas.tgenie_setup import AtlasConfigStore, TgenieBrowserLaunchError
from atlas.tui import AtlasApp
from rich.cells import cell_len
from textual.widgets import Input, RichLog, Static


class RecordingLoginBrowserLauncher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    async def open_login_browser(self, url: str, profile_dir: Path) -> object:
        self.calls.append((url, profile_dir))
        return object()


class ReadyLocator:
    def __init__(self, page: ReadyTgeniePage, selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> ReadyLocator:
        return self

    async def wait_for(self, *, state: str, timeout: int) -> None:
        self.page.waits.append((self.selector, state, timeout))
        if self.selector not in self.page.ready_selectors:
            raise TimeoutError(f"Missing selector: {self.selector}")


class ReadyTgeniePage:
    def __init__(self, ready_selectors: set[str]) -> None:
        self.ready_selectors = ready_selectors
        self.waits: list[tuple[str, str, int]] = []

    def locator(self, selector: str) -> ReadyLocator:
        return ReadyLocator(self, selector)


class ReadyLoginBrowserSession:
    def __init__(self, page: ReadyTgeniePage) -> None:
        self.page = page


class ReadyLoginBrowserLauncher:
    def __init__(self, page: ReadyTgeniePage) -> None:
        self.page = page
        self.calls: list[tuple[str, Path]] = []

    async def open_login_browser(self, url: str, profile_dir: Path) -> ReadyLoginBrowserSession:
        self.calls.append((url, profile_dir))
        return ReadyLoginBrowserSession(self.page)


class FailingLoginBrowserLauncher:
    async def open_login_browser(self, url: str, profile_dir: Path) -> object:
        raise TgenieBrowserLaunchError("Could not open system Chrome. Install Google Chrome.")


class RecordingTgenieAdapter:
    def __init__(self, response: str = "atlas-ok") -> None:
        self.response = response
        self.prompts: list[str] = []

    async def send_single_turn(self, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return self.response

    async def send_followup(self, message: str) -> str:
        self.prompts.append(message)
        return self.response


class FailingTgenieAdapter:
    async def send_single_turn(self, user_prompt: str) -> str:
        raise TgenieConversationError("Could not find tGenie send button with selector: button:has(svg)")


class ToolLoopTgenieAdapter:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_single_turn(self, user_prompt: str) -> str:
        self.messages.append(user_prompt)
        return """```json
{"type": "atlas.tool_call", "tool": "file.search", "args": {"query": "needle"}}
```"""

    async def send_followup(self, message: str) -> str:
        self.messages.append(message)
        return "The answer is needle here."


class PdfAttachTgenieAdapter:
    def __init__(
        self,
        requested_path: str = "case.pdf",
        tool_name: str = "pdf.attach",
        attach_error: Exception | None = None,
        followup_response: str = "The PDF is attached.",
    ) -> None:
        self.requested_path = requested_path
        self.tool_name = tool_name
        self.attach_error = attach_error
        self.followup_response = followup_response
        self.messages: list[str] = []
        self.attached_files: list[Path] = []
        self.attached_pdfs = self.attached_files

    async def send_single_turn(self, user_prompt: str) -> str:
        self.messages.append(user_prompt)
        return f"""```json
{{"type": "atlas.tool_call", "tool": "{self.tool_name}", "args": {{"path": "{self.requested_path}"}}}}
```"""

    async def send_followup(self, message: str) -> str:
        self.messages.append(message)
        return self.followup_response

    async def attach_file(self, path: Path) -> None:
        if self.attach_error is not None:
            raise self.attach_error
        self.attached_files.append(path)

    async def attach_pdf(self, path: Path) -> None:
        await self.attach_file(path)


class FaStemBriefTgenieAdapter:
    def __init__(self, response: str | list[str]) -> None:
        self.responses = [response] if isinstance(response, str) else list(response)
        self.prompts: list[str] = []
        self.attached_files: list[Path] = []

    async def send_single_turn(self, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return self.responses.pop(0)

    async def send_followup(self, message: str) -> str:
        self.prompts.append(message)
        return self.responses.pop(0)

    async def attach_file(self, path: Path) -> None:
        self.attached_files.append(path)

    async def attach_pdf(self, path: Path) -> None:
        await self.attach_file(path)


def rich_log_text(log: RichLog) -> str:
    return "\n".join("".join(segment.text for segment in line) for line in log.lines)


def screenshot_text(svg: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", svg)).replace("\xa0", " ")


def is_horizontal_rule(line: str) -> bool:
    return bool(line) and set(line) == {"─"}


def rich_color_tuple(segment: object) -> tuple[int, int, int]:
    color = segment.style.color.triplet
    return (color.red, color.green, color.blue)


class AtlasTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_run_tgenie_url_is_saved_from_prompt(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                app = AtlasApp(workspace=Path(workspace_directory).resolve(), tgenie_config_store=store)

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: tGenie URL is not configured.", messages)

                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = " https://tgenie.example.test "
                    await prompt.action_submit()
                    await pilot.pause()

                self.assertEqual(store.load().tgenie_url, "https://tgenie.example.test")

    async def test_first_run_tgenie_url_opens_chrome_after_it_is_saved(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                launcher = RecordingLoginBrowserLauncher()
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=launcher,
                )

                async with app.run_test() as pilot:
                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = "https://tgenie.example.test"
                    await prompt.action_submit()
                    await pilot.pause()

                self.assertEqual(launcher.calls, [("https://tgenie.example.test", store.chrome_profile_dir)])

    async def test_slash_command_during_first_run_url_prompt_is_not_saved_as_url(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                app = AtlasApp(workspace=Path(workspace_directory).resolve(), tgenie_config_store=store)

                async with app.run_test() as pilot:
                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = "/help"
                    await prompt.action_submit()
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: Available commands", messages)

                self.assertIsNone(store.load().tgenie_url)

    async def test_saved_tgenie_url_is_reused_without_prompting_again(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(workspace=Path(workspace_directory).resolve(), tgenie_config_store=store)

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: Using saved tGenie URL.", messages)
                    self.assertNotIn("tGenie URL is not configured", messages)

    async def test_saved_tgenie_url_opens_chrome_and_waits_for_manual_login(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                launcher = RecordingLoginBrowserLauncher()
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=launcher,
                )

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: Complete login in Chrome, then type /login-done.", messages)

                self.assertEqual(launcher.calls, [("https://tgenie.example.test", store.chrome_profile_dir)])

    async def test_saved_tgenie_url_auto_confirms_login_when_chat_ui_is_ready(self) -> None:
        from atlas.tgenie_adapter import SEND_SELECTOR, TEXTAREA_SELECTOR

        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                page = ReadyTgeniePage({TEXTAREA_SELECTOR, SEND_SELECTOR})
                launcher = ReadyLoginBrowserLauncher(page)
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=launcher,
                )

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: tGenie is ready. You can continue in Atlas.", messages)
                    self.assertNotIn("type /login-done", messages)
                    self.assertIsNotNone(pilot.app.tgenie_adapter)

                self.assertEqual(
                    [selector for selector, _state, _timeout in page.waits],
                    [TEXTAREA_SELECTOR, SEND_SELECTOR],
                )

    async def test_tgenie_browser_launch_error_is_shown_in_tui(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=FailingLoginBrowserLauncher(),
                )

                async with app.run_test() as pilot:
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Error: Could not open system Chrome.", messages)

    async def test_login_done_confirms_manual_tgenie_login(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=RecordingLoginBrowserLauncher(),
                )

                async with app.run_test() as pilot:
                    prompt = pilot.app.query_one("#prompt", Input)
                    prompt.value = "/login-done"
                    await prompt.action_submit()
                    await pilot.pause()

                    messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                    self.assertIn("Atlas: tGenie login confirmed. You can continue in Atlas.", messages)

    async def test_login_done_is_suggested_while_waiting_for_manual_login(self) -> None:
        with TemporaryDirectory() as workspace_directory:
            with TemporaryDirectory() as config_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))
                store.save_tgenie_url("https://tgenie.example.test")
                app = AtlasApp(
                    workspace=Path(workspace_directory).resolve(),
                    tgenie_config_store=store,
                    tgenie_browser_launcher=RecordingLoginBrowserLauncher(),
                )

                async with app.run_test() as pilot:
                    await pilot.press("/")
                    await pilot.pause()

                    suggestions = pilot.app.query_one("#slash-suggestions", Static)
                    self.assertIn("/login-done", str(suggestions.render()))

    async def test_prompt_is_sent_to_real_tgenie_adapter_when_available(self) -> None:
        adapter = RecordingTgenieAdapter(response="atlas-ok")

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "Atlas smoke test."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("› You  Atlas smoke test.", messages)
                self.assertIn("Working: Waiting for model", messages)
                self.assertIn("Atlas: atlas-ok", messages)

        self.assertEqual(adapter.prompts, ["Atlas smoke test."])

    async def test_prompt_runs_real_tgenie_tool_loop_when_adapter_requests_tool(self) -> None:
        adapter = ToolLoopTgenieAdapter()

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            (workspace / "notes.md").write_text("needle here\n", encoding="utf-8")
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "Find needle."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Waiting for model", messages)
                self.assertIn("Working: Parsing tool call", messages)
                self.assertIn("Working: Executing tool", messages)
                self.assertIn("Working: Sending tool result", messages)
                self.assertIn("Atlas: The answer is needle here.", messages)

        self.assertEqual(adapter.messages[0], "Find needle.")
        self.assertIn('"type": "atlas.tool_result"', adapter.messages[1])
        self.assertIn('"path": "notes.md"', adapter.messages[1])

    async def test_tui_shows_pdf_attach_upload_status(self) -> None:
        adapter = PdfAttachTgenieAdapter()

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            (workspace / "case.pdf").write_bytes(b"%PDF-1.4\n")
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "Attach case.pdf."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Uploading PDF", messages)
                self.assertIn("Working: PDF uploaded", messages)
                self.assertIn("Atlas: The PDF is attached.", messages)

        self.assertEqual(adapter.attached_pdfs, [(workspace / "case.pdf").resolve()])
        self.assertIn('"type": "atlas.tool_result"', adapter.messages[1])
        self.assertIn('"status": "uploaded"', adapter.messages[1])

    async def test_tui_shows_image_attach_upload_status(self) -> None:
        adapter = PdfAttachTgenieAdapter(
            requested_path="panel.png",
            tool_name="file.attach",
            followup_response="The image is attached.",
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            (workspace / "panel.png").write_bytes(b"\x89PNG\r\n")
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "Attach panel.png."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Uploading attachment", messages)
                self.assertIn("Working: Attachment uploaded", messages)
                self.assertIn("Atlas: The image is attached.", messages)

        self.assertEqual(adapter.attached_files, [(workspace / "panel.png").resolve()])
        self.assertIn('"type": "atlas.tool_result"', adapter.messages[1])
        self.assertIn('"tool": "file.attach"', adapter.messages[1])
        self.assertIn('"status": "uploaded"', adapter.messages[1])

    async def test_fa_stem_brief_command_waits_for_case_background(self) -> None:
        adapter = RecordingTgenieAdapter()

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            (workspace / "case-a").mkdir()
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/fa-stem brief case-a"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: Starting FA STEM brief: case-a", messages)
                self.assertIn("Atlas: Paste the FA STEM case background to start analysis.", messages)

        self.assertEqual(adapter.prompts, [])

    async def test_fa_stem_brief_command_rejects_invalid_folder_before_waiting(self) -> None:
        adapter = RecordingTgenieAdapter()

        cases = {
            "missing": ("/fa-stem brief missing", "Folder not found."),
            "escape": ("/fa-stem brief ../outside", "Path must stay inside the workspace."),
        }
        for case_name, (command, expected_error) in cases.items():
            with self.subTest(case_name=case_name):
                with TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    workspace = root / "workspace"
                    workspace.mkdir()
                    (root / "outside").mkdir()
                    app = AtlasApp(
                        workspace=workspace,
                        tgenie_adapter=adapter,
                    )

                    async with app.run_test() as pilot:
                        prompt = pilot.app.query_one("#prompt")
                        prompt.value = command
                        await prompt.action_submit()
                        await pilot.pause()

                        messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                        self.assertIn(f"Error: {expected_error}", messages)
                        self.assertNotIn("Paste the FA STEM case background", messages)

        self.assertEqual(adapter.prompts, [])

    async def test_fa_stem_brief_background_creates_demo_report(self) -> None:
        adapter = FaStemBriefTgenieAdapter(
            [
                """```json
{
  "candidate_observations": [
    {
      "tile_label": "A1",
      "observation": "Void-like contrast near the via edge.",
      "inference": "This may indicate missing material.",
      "uncertainty": "The contrast could also come from sample preparation.",
      "confidence": "medium",
      "coordinates": [{"center_x_percent": 25, "center_y_percent": 40, "radius_percent": 12}]
    }
  ]
}
```"""
                ,
                """```json
{
  "candidate_review": {
    "observation": "The original image confirms a void-like contrast near the via edge.",
    "reason": "This candidate overlaps the likely electrical path.",
    "uncertainty": "The contrast could also come from sample preparation.",
    "confidence": "high",
    "classification": "primary-suspect-relevant",
    "coordinates": [{"center_x_percent": 25, "center_y_percent": 40, "radius_percent": 12}]
  }
}
```""",
                """```json
{
  "primary_suspect": {
    "status": "selected",
    "source_id": "case-a/a-first.jpg",
    "reason": "The confirmed void-like contrast best matches the leakage background.",
    "uncertainty": "Human FA review is still required.",
    "confidence": "high",
    "coordinates": [{"center_x_percent": 25, "center_y_percent": 40, "radius_percent": 12}]
  },
  "profile_anomalies": []
}
```""",
            ]
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            selected_image = case_folder / "a-first.jpg"
            Image.new("RGB", (32, 24), color=(180, 20, 20)).save(selected_image)
            Image.new("RGB", (32, 24), color=(20, 20, 180)).save(case_folder / "z-later.jpeg")
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/fa-stem brief case-a"
                await prompt.action_submit()
                prompt.value = "Leakage fails at VDD after stress."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: FA STEM brief report written:", messages)

            report = case_folder / "atlas-fa-stem-brief.html"
            report_html = report.read_text(encoding="utf-8")
            metadata_exists = (case_folder / "atlas-fa-stem-report" / "metadata.json").exists()
            model_outputs_exists = (case_folder / "atlas-fa-stem-report" / "model-outputs.json").exists()

        self.assertEqual(len(adapter.attached_files), 2)
        self.assertEqual(adapter.attached_files[0].suffix, ".png")
        self.assertEqual(adapter.attached_files[1].name, "a-first.jpg")
        self.assertEqual(len(adapter.prompts), 3)
        self.assertIn("senior semiconductor process failure analysis engineer", adapter.prompts[0])
        self.assertIn("Leakage fails at VDD after stress.", adapter.prompts[0])
        self.assertIn("candidate_observations", adapter.prompts[0])
        self.assertIn("A1: case-a/a-first.jpg", adapter.prompts[0])
        self.assertIn("candidate_review", adapter.prompts[1])
        self.assertIn("Do not assume prior attachments are still visible", adapter.prompts[2])
        self.assertIn("a-first.jpg", report_html)
        self.assertIn("z-later.jpeg", report_html)
        self.assertIn("Leakage fails at VDD after stress.", report_html)
        self.assertIn("FA STEM Suspect Triage Report", report_html)
        self.assertIn("Scan Summary", report_html)
        self.assertIn("Primary Electrical Suspect", report_html)
        self.assertIn("overlay-circle primary-suspect", report_html)
        self.assertIn("The confirmed void-like contrast best matches the leakage background.", report_html)
        self.assertIn("Not-Flagged Images", report_html)
        self.assertIn("selected", report_html)
        self.assertTrue(metadata_exists)
        self.assertTrue(model_outputs_exists)

    async def test_fa_stem_brief_empty_folder_shows_clear_error(self) -> None:
        adapter = FaStemBriefTgenieAdapter("{}")

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/fa-stem brief case-a"
                await prompt.action_submit()
                prompt.value = "Leakage fails at VDD after stress."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Error: No .jpg or .jpeg image found", messages)

            self.assertFalse((case_folder / "atlas-fa-stem-brief.html").exists())

        self.assertEqual(adapter.attached_files, [])
        self.assertEqual(adapter.prompts, [])

    async def test_tui_shows_pdf_attach_failure_status(self) -> None:
        adapter = PdfAttachTgenieAdapter(
            requested_path="case.txt",
            followup_response="The PDF was rejected.",
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            (workspace / "case.txt").write_text("not a pdf", encoding="utf-8")
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "Attach case.txt."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Uploading PDF", messages)
                self.assertIn("Working: PDF upload failed", messages)
                self.assertIn("Atlas: The PDF was rejected.", messages)

        self.assertEqual(adapter.attached_pdfs, [])
        self.assertIn('"type": "atlas.tool_result"', adapter.messages[1])
        self.assertIn('"ok": false', adapter.messages[1])

    async def test_tui_shows_pdf_attach_timeout_status(self) -> None:
        adapter = PdfAttachTgenieAdapter(
            requested_path="case.pdf",
            attach_error=TimeoutError("Timed out waiting for attached file name."),
            followup_response="The PDF upload timed out.",
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            (workspace / "case.pdf").write_bytes(b"%PDF-1.4\n")
            app = AtlasApp(
                workspace=workspace,
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "Attach case.pdf."
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Uploading PDF", messages)
                self.assertIn("Working: PDF upload timed out", messages)
                self.assertIn("Atlas: The PDF upload timed out.", messages)

        self.assertEqual(adapter.attached_pdfs, [])
        self.assertIn('"type": "atlas.tool_result"', adapter.messages[1])
        self.assertIn('"status": "timeout"', adapter.messages[1])

    async def test_real_tgenie_adapter_errors_are_shown_in_tui(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                tgenie_adapter=FailingTgenieAdapter(),
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "send this"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Error: Could not find tGenie send button", messages)

    async def test_app_shows_header_messages_and_prompt_input(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            app = AtlasApp(workspace=workspace)

            async with app.run_test() as pilot:
                await pilot.pause()

                header = pilot.app.query_one("#header", Static)
                self.assertIn("Atlas", str(header.render()))
                self.assertIn(str(workspace), str(header.render()))
                pilot.app.query_one("#messages")
                pilot.app.query_one("#prompt")

    async def test_app_has_no_footer_status_bar(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                self.assertEqual(len(pilot.app.query("#status")), 0)

    async def test_header_has_breathing_room(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                header = pilot.app.query_one("#header", Static)
                self.assertEqual(header.region.height, 3)
                self.assertGreaterEqual(header.styles.padding.left, 3)
                self.assertEqual(header.styles.padding.top, 1)
                self.assertEqual(header.styles.padding.bottom, 1)

    async def test_layout_uses_color_blocks_without_borders(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertEqual(messages.styles.border.top[0], "")
                self.assertEqual(prompt.styles.border.top[0], "")

    async def test_prompt_box_stays_compact(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                self.assertEqual(prompt.region.height, 3)
                self.assertEqual(prompt.styles.padding.top, 1)
                self.assertEqual(prompt.styles.padding.bottom, 1)

    async def test_multiline_prompt_expands_inside_layout(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(42, 10)) as pilot:
                await pilot.press("h", "i", "shift+enter", "t", "h", "e", "r", "e")
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertEqual(prompt.content_region.height, 2)
                self.assertEqual(prompt.region.height, 4)
                self.assertLessEqual(messages.region.y + messages.region.height, prompt.region.y)
                self.assertLessEqual(prompt.region.y + prompt.region.height, pilot.app.size.height)

    async def test_long_prompt_wraps_without_overlapping_messages(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(30, 12)) as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "abcdefghijklmnopqrstuvwxyz0123456789"
                prompt.cursor_position = len(prompt.value)
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                self.assertGreater(prompt.content_region.height, 1)
                self.assertLessEqual(messages.region.y + messages.region.height, prompt.region.y)
                self.assertLessEqual(prompt.cursor_screen_offset.y, prompt.content_region.y + prompt.content_region.height - 1)

    async def test_left_and_right_arrows_move_prompt_cursor(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(40, 12)) as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("a", "b", "c", "left", "x", "right", "y")
                await pilot.pause()

                self.assertEqual(prompt.value, "abxcy")
                self.assertEqual(prompt.cursor_position, len(prompt.value))

    async def test_up_and_down_arrows_move_multiline_prompt_cursor(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(40, 12)) as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "abc\ndef"
                prompt.cursor_position = len(prompt.value)
                await pilot.pause()

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(prompt.cursor_position, 3)

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(prompt.cursor_position, len(prompt.value))

    async def test_up_and_down_arrows_move_wrapped_prompt_cursor(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(18, 12)) as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "abcdefghijklmnopqrst"
                prompt.cursor_position = len(prompt.value)
                await pilot.pause()

                await pilot.press("up")
                await pilot.pause()
                self.assertLess(prompt.cursor_position, len(prompt.value))

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(prompt.cursor_position, len(prompt.value))

    async def test_resize_keeps_multiline_prompt_inside_terminal(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(42, 10)) as pilot:
                await pilot.press("h", "i", "shift+enter", "t", "h", "e", "r", "e")
                await pilot.resize_terminal(28, 8)
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertGreaterEqual(messages.content_region.height, 1)
                self.assertEqual(prompt.content_region.height, 2)
                self.assertLessEqual(messages.region.y + messages.region.height, prompt.region.y)
                self.assertLessEqual(prompt.region.y + prompt.region.height, pilot.app.size.height)

    async def test_prompt_cursor_does_not_use_block_background(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                cursor_style = prompt.get_component_rich_style("input--cursor")
                self.assertIsNotNone(cursor_style.bgcolor)
                cursor_color = cursor_style.bgcolor.triplet
                self.assertEqual(
                    (cursor_color.red, cursor_color.green, cursor_color.blue),
                    (32, 32, 32),
                )
                self.assertTrue(cursor_style.underline)

    async def test_prompt_terminal_cursor_starts_at_input_origin_for_ime_preview(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)

                self.assertEqual(prompt.cursor_screen_offset.x, prompt.content_region.x)
                self.assertEqual(pilot.app.cursor_position, prompt.cursor_screen_offset)

    async def test_prompt_cursor_offset_stays_at_text_end_for_cjk_ime(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "中文輸入，"
                prompt.cursor_position = len(prompt.value)
                await pilot.pause()

                self.assertEqual(
                    prompt.cursor_screen_offset.x,
                    prompt.content_region.x + cell_len(prompt.value),
                )

    async def test_mouse_focus_does_not_create_box_highlight(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertFalse(messages.can_focus)
                self.assertEqual(prompt.styles.border.top[0], "")
                self.assertEqual(prompt.styles.background_tint.a, 0)

    async def test_app_focuses_prompt_on_startup(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                self.assertIs(pilot.app.focused, prompt)

    async def test_typing_while_transcript_is_focused_returns_to_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                messages = pilot.app.query_one("#messages", RichLog)
                prompt = pilot.app.query_one("#prompt", Input)
                pilot.app.set_focus(messages)

                await pilot.press("h", "i")
                await pilot.pause()

                self.assertEqual(prompt.value, "hi")
                self.assertIs(pilot.app.focused, prompt)

    async def test_app_keeps_prompt_focused_after_prompt_submission(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")
                self.assertIs(pilot.app.focused, prompt)

    async def test_transcript_labels_startup_and_user_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: Ready.", messages)
                self.assertIn("› You  say hello", messages)
                lines = messages.splitlines()
                message_log = pilot.app.query_one("#messages", RichLog)
                self.assertEqual(len(lines[0]), message_log.scrollable_content_region.width)
                self.assertEqual(set(lines[0]), {"─"})
                self.assertEqual(lines[1], "Atlas: Ready.")
                self.assertEqual(set(lines[2]), {"─"})
                self.assertEqual(lines[3], "› You  say hello")

    async def test_multiline_user_prompt_body_is_not_pushed_right_by_label(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "一\n二\n三"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                lines = messages.splitlines()
                user_index = lines.index("› You")

                self.assertEqual(lines[user_index + 1 : user_index + 4], ["一", "二", "三"])

    async def test_user_prompt_highlight_does_not_use_background_color(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = pilot.app.query_one("#messages", RichLog)
                user_line = messages.lines[3]
                self.assertEqual("".join(segment.text for segment in user_line), "› You  say hello")
                for segment in user_line:
                    self.assertIsNone(segment.style.bgcolor)
                user_segments = list(user_line)
                self.assertEqual(rich_color_tuple(user_segments[0]), (77, 182, 255))
                self.assertEqual(rich_color_tuple(user_segments[2]), (208, 208, 208))
                self.assertEqual(rich_color_tuple(user_segments[3]), (255, 255, 255))

    async def test_prompt_text_is_visible_while_typing(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(100, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a", "b", "c")
                await pilot.pause()

                prompt = pilot.app.query_one("#prompt", Input)
                screenshot = pilot.app.export_screenshot()
                self.assertEqual(prompt.value, "abc")
                self.assertIn("abc", screenshot)

    async def test_cjk_prompt_text_is_visible_before_and_after_submission(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test(size=(100, 24)) as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "你好啊"
                await pilot.pause()

                self.assertIn("你好啊", pilot.app.export_screenshot())

                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")
                self.assertIn("你好啊", pilot.app.export_screenshot())

    async def test_shift_enter_inserts_newline_without_submitting_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("h", "i", "shift+enter", "t", "h", "e", "r", "e")
                await pilot.pause()

                self.assertEqual(prompt.value, "hi\nthere")
                screenshot = screenshot_text(pilot.app.export_screenshot())
                self.assertIn("hi", screenshot)
                self.assertIn("there", screenshot)
                self.assertNotIn("› You  hi", rich_log_text(pilot.app.query_one("#messages", RichLog)))

                await pilot.press("enter")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "")
                lines = messages.splitlines()
                user_index = lines.index("› You")
                self.assertEqual(lines[user_index + 1 : user_index + 3], ["hi", "there"])

    async def test_empty_prompt_can_browse_submitted_prompt_history(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "first prompt"
                await prompt.action_submit()
                prompt.value = "second prompt"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(prompt.value, "second prompt")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(prompt.value, "first prompt")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(prompt.value, "second prompt")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(prompt.value, "")

                prompt.value = "draft"
                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(prompt.value, "draft")

    async def test_app_keeps_prompt_focused_after_slash_command(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                prompt.value = "/help"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(prompt.value, "")
                self.assertIs(pilot.app.focused, prompt)

    async def test_transcript_labels_slash_command_output_as_atlas_output(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/help"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: Available commands", messages)

    async def test_consecutive_atlas_outputs_share_one_transcript_block(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/help"
                await prompt.action_submit()
                prompt.value = "/missing"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                lines = messages.splitlines()
                help_index = next(
                    index
                    for index, line in enumerate(lines)
                    if line.startswith("Atlas: Available commands")
                )
                missing_index = next(
                    index
                    for index, line in enumerate(lines)
                    if line.startswith("Atlas: Unknown skill")
                )

                self.assertFalse(any(is_horizontal_rule(line) for line in lines[help_index + 1 : missing_index]))

    async def test_focused_empty_prompt_does_not_render_placeholder_text(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.pause()
                prompt = pilot.app.query_one("#prompt", Input)

                self.assertEqual(prompt.placeholder, "")
                self.assertNotIn(
                    "Enter a prompt",
                    screenshot_text(pilot.app.export_screenshot()),
                )

    async def test_slash_suggestions_show_when_prompt_starts_with_slash(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                await pilot.press("/")
                await pilot.pause()

                suggestions = pilot.app.query_one("#slash-suggestions", Static)
                suggestion_text = str(suggestions.render())
                self.assertFalse(suggestions.has_class("hidden"))
                self.assertIn("/help", suggestion_text)
                self.assertIn("/llm-wiki", suggestion_text)
                self.assertIn("/llm-wiki ingest", suggestion_text)
                self.assertIn("/skill-creator", suggestion_text)
                selected_marker_style = suggestions.render().spans[0].style
                self.assertEqual(selected_marker_style.foreground.rgb, (77, 182, 255))
                self.assertEqual(selected_marker_style.background.rgb, (48, 48, 48))

    async def test_slash_suggestions_are_capped_to_keep_prompt_visible(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            for index in range(12):
                skill_dir = workspace / ".atlas" / "skills" / f"skill-{index:02d}"
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("# Skill\n\nDo work.", encoding="utf-8")
            app = AtlasApp(workspace=workspace)

            async with app.run_test(size=(40, 12)) as pilot:
                await pilot.press("/")
                await pilot.pause()

                suggestions = pilot.app.query_one("#slash-suggestions", Static)
                prompt = pilot.app.query_one("#prompt", Input)
                self.assertLessEqual(suggestions.content_region.height, 6)
                self.assertLessEqual(suggestions.region.y + suggestions.region.height, prompt.region.y)
                self.assertLessEqual(prompt.region.y + prompt.region.height, pilot.app.size.height)

    async def test_slash_suggestions_support_keyboard_selection(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("/")
                await pilot.press("down")
                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "/llm-wiki ")
                self.assertNotIn("loaded skill: llm-wiki", messages)
                self.assertTrue(pilot.app.query_one("#slash-suggestions", Static).has_class("hidden"))

                await pilot.press("enter")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "")
                self.assertIn("loaded skill: llm-wiki", messages)

    async def test_slash_suggestions_keyboard_selection_tab_completes_without_submitting(self) -> None:
        with TemporaryDirectory() as directory:
            app = AtlasApp(workspace=Path(directory).resolve())

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("/")
                await pilot.press("down")
                await pilot.press("down")
                await pilot.press("tab")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "/llm-wiki ")
                self.assertNotIn("loaded skill: llm-wiki", messages)
                self.assertTrue(pilot.app.query_one("#slash-suggestions", Static).has_class("hidden"))

    async def test_single_slash_suggestion_enter_completes_without_submitting(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            skill_dir = workspace / ".atlas" / "skills" / "repair-notes"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# Repair Notes\n\nFix notes.", encoding="utf-8")
            app = AtlasApp(workspace=workspace)

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("/", "r", "e", "p", "enter")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "/repair-notes ")
                self.assertNotIn("Loaded skill: repair-notes", messages)
                self.assertTrue(pilot.app.query_one("#slash-suggestions", Static).has_class("hidden"))

                await pilot.press("enter")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "")
                self.assertIn("Loaded skill: repair-notes", messages)

    async def test_single_slash_suggestion_tab_completes_without_submitting(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            skill_dir = workspace / ".atlas" / "skills" / "repair-notes"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# Repair Notes\n\nFix notes.", encoding="utf-8")
            app = AtlasApp(workspace=workspace)

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt", Input)
                await pilot.press("/", "r", "e", "p", "tab")
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertEqual(prompt.value, "/repair-notes ")
                self.assertNotIn("Loaded skill: repair-notes", messages)
                self.assertTrue(pilot.app.query_one("#slash-suggestions", Static).has_class("hidden"))

    async def test_app_shows_fake_tool_loop_status_updates(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Waiting for model", messages)
                self.assertIn("Working: Parsing tool call", messages)
                self.assertIn("Working: Executing tool", messages)
                self.assertIn("Working: Final response", messages)
                self.assertIn("Final answer: hello", messages)

    async def test_tool_loop_status_renders_as_atlas_output_after_user_prompt(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                lines = messages.splitlines()
                user_index = next(index for index, line in enumerate(lines) if "› You  say hello" in line)
                working_index = next(
                    index for index, line in enumerate(lines) if line == "Working: Waiting for model"
                )

                self.assertTrue(
                    any(is_horizontal_rule(line) for line in lines[user_index + 1 : working_index])
                )

    async def test_fake_tool_loop_does_not_render_footer_status(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                self.assertEqual(len(pilot.app.query("#status")), 0)
                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Final response", messages)

    async def test_transcript_labels_final_response_as_atlas_output(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "say hello"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Atlas: Final answer: hello", messages)

    async def test_transcript_labels_tool_call_errors(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call",
```""",
            ]
        )

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "run bad tool call"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Error: Tool call JSON is invalid", messages)

    async def test_skill_command_injects_instructions_into_fake_adapter(self) -> None:
        adapter = FakeTgenieAdapter(responses=[])

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/llm-wiki"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("loaded skill: llm-wiki", messages)

        self.assertEqual(len(adapter.sent_messages), 1)
        self.assertIn('<atlas.skill_instructions name="llm-wiki">', adapter.sent_messages[0])
        self.assertIn("LLM Wiki", adapter.sent_messages[0])

    async def test_llm_wiki_ingest_command_runs_ingestion_with_real_tgenie_adapter(self) -> None:
        adapter = PdfAttachTgenieAdapter(
            requested_path="case.pdf",
            followup_response="Ingested case.pdf into the wiki.",
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "case.pdf").write_bytes(b"%PDF-1.4\n")
            app = AtlasApp(
                workspace=workspace.resolve(),
                tgenie_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/llm-wiki ingest case.pdf"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Working: Uploading PDF", messages)
                self.assertIn("Working: Rendering HTML mirror", messages)
                self.assertIn("Working: Rendering graph", messages)
                self.assertIn("Atlas: Ingested case.pdf into the wiki.", messages)

            self.assertEqual(adapter.attached_pdfs, [(workspace / "case.pdf").resolve()])
            self.assertTrue((workspace / "wiki" / "output" / "html" / "index.html").is_file())
            self.assertTrue((workspace / "wiki" / "output" / "graph" / "index.html").is_file())

    async def test_skill_creator_command_injects_builtin_instructions(self) -> None:
        adapter = FakeTgenieAdapter(responses=[])

        with TemporaryDirectory() as directory:
            app = AtlasApp(
                workspace=Path(directory).resolve(),
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/skill-creator"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Loaded skill: skill-creator", messages)

        self.assertEqual(len(adapter.sent_messages), 1)
        self.assertIn('<atlas.skill_instructions name="skill-creator">', adapter.sent_messages[0])
        self.assertIn("Skill Creator", adapter.sent_messages[0])

    async def test_skill_command_suffix_runs_prompt_with_skill_instructions(self) -> None:
        adapter = FakeTgenieAdapter(responses=["Updated notes."])

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            skill_dir = workspace / ".atlas" / "skills" / "repair-notes"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "# Repair Notes\n\nFix notes.",
                encoding="utf-8",
            )
            app = AtlasApp(
                workspace=workspace,
                fake_adapter=adapter,
            )

            async with app.run_test() as pilot:
                prompt = pilot.app.query_one("#prompt")
                prompt.value = "/repair-notes summarize latest changes"
                await prompt.action_submit()
                await pilot.pause()

                messages = rich_log_text(pilot.app.query_one("#messages", RichLog))
                self.assertIn("Loaded skill: repair-notes", messages)
                self.assertIn("Updated notes.", messages)

        self.assertEqual(len(adapter.sent_messages), 1)
        self.assertIn('<atlas.skill_instructions name="repair-notes">', adapter.sent_messages[0])
        self.assertIn("User task:\nsummarize latest changes", adapter.sent_messages[0])


if __name__ == "__main__":
    unittest.main()
