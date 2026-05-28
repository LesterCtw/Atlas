from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from atlas.tgenie_setup import AtlasConfigStore, TgenieBrowserLaunchError, TgenieBrowserLauncher


class RecordingPage:
    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, str]] = []

    async def goto(self, url: str, wait_until: str) -> None:
        self.goto_calls.append((url, wait_until))


class RecordingContext:
    def __init__(self) -> None:
        self.page = RecordingPage()
        self.pages = [self.page]

    async def close(self) -> None:
        pass


class RecordingChromium:
    def __init__(self) -> None:
        self.context = RecordingContext()
        self.launch_kwargs: dict[str, object] | None = None

    async def launch_persistent_context(self, **kwargs: object) -> RecordingContext:
        self.launch_kwargs = kwargs
        return self.context


class RecordingPlaywright:
    def __init__(self) -> None:
        self.chromium = RecordingChromium()
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class RecordingPlaywrightManager:
    def __init__(self) -> None:
        self.playwright = RecordingPlaywright()

    async def start(self) -> RecordingPlaywright:
        return self.playwright


class FailingChromium:
    async def launch_persistent_context(self, **kwargs: object) -> RecordingContext:
        raise RuntimeError("executable doesn't exist")


class FailingPlaywright:
    def __init__(self) -> None:
        self.chromium = FailingChromium()
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FailingPlaywrightManager:
    def __init__(self) -> None:
        self.playwright = FailingPlaywright()

    async def start(self) -> FailingPlaywright:
        return self.playwright


class FailingStartPlaywrightManager:
    async def start(self) -> FailingPlaywright:
        raise RuntimeError("It looks like you are using Playwright Sync API inside the asyncio loop.")


class AtlasTgenieSetupTests(unittest.IsolatedAsyncioTestCase):
    def test_saved_tgenie_url_is_reused_by_later_startups(self) -> None:
        with TemporaryDirectory() as directory:
            store = AtlasConfigStore(config_dir=Path(directory))

            store.save_tgenie_url("https://tgenie.example.test")

            later_store = AtlasConfigStore(config_dir=Path(directory))
            self.assertEqual(later_store.load().tgenie_url, "https://tgenie.example.test")

    def test_blank_tgenie_url_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            store = AtlasConfigStore(config_dir=Path(directory))

            with self.assertRaises(ValueError):
                store.save_tgenie_url("   ")

            self.assertIsNone(store.load().tgenie_url)

    def test_chrome_profile_dir_lives_under_user_config_dir(self) -> None:
        with TemporaryDirectory() as config_directory:
            with TemporaryDirectory() as workspace_directory:
                store = AtlasConfigStore(config_dir=Path(config_directory))

                self.assertEqual(store.chrome_profile_dir, Path(config_directory) / "chrome-profile")
                self.assertNotIn(Path(workspace_directory), store.chrome_profile_dir.parents)

    async def test_browser_launcher_opens_system_chrome_headed_with_persistent_profile(self) -> None:
        with TemporaryDirectory() as profile_directory:
            manager = RecordingPlaywrightManager()
            launcher = TgenieBrowserLauncher(playwright_manager_factory=lambda: manager)

            await launcher.open_login_browser(
                url="https://tgenie.example.test",
                profile_dir=Path(profile_directory),
            )

            launch_kwargs = manager.playwright.chromium.launch_kwargs
            self.assertIsNotNone(launch_kwargs)
            assert launch_kwargs is not None
            self.assertEqual(launch_kwargs["user_data_dir"], profile_directory)
            self.assertEqual(launch_kwargs["channel"], "chrome")
            self.assertIs(launch_kwargs["headless"], False)
            self.assertIsNone(launch_kwargs["viewport"])
            self.assertIn("--start-maximized", launch_kwargs["args"])
            self.assertEqual(
                manager.playwright.chromium.context.page.goto_calls,
                [("https://tgenie.example.test", "domcontentloaded")],
            )

    async def test_browser_launcher_reports_missing_chrome_as_user_facing_error(self) -> None:
        with TemporaryDirectory() as profile_directory:
            manager = FailingPlaywrightManager()
            launcher = TgenieBrowserLauncher(playwright_manager_factory=lambda: manager)

            with self.assertRaises(TgenieBrowserLaunchError) as captured:
                await launcher.open_login_browser(
                    url="https://tgenie.example.test",
                    profile_dir=Path(profile_directory),
                )

            self.assertIn("Could not open system Chrome", str(captured.exception))
            self.assertIn("Google Chrome", str(captured.exception))
            self.assertTrue(manager.playwright.stopped)

    async def test_browser_launcher_wraps_playwright_start_errors(self) -> None:
        with TemporaryDirectory() as profile_directory:
            launcher = TgenieBrowserLauncher(playwright_manager_factory=FailingStartPlaywrightManager)

            with self.assertRaises(TgenieBrowserLaunchError) as captured:
                await launcher.open_login_browser(
                    url="https://tgenie.example.test",
                    profile_dir=Path(profile_directory),
                )

            self.assertIn("Could not open system Chrome", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
