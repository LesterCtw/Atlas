from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


def default_atlas_config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "Atlas"
        return Path.home() / "AppData" / "Roaming" / "Atlas"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Atlas"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Atlas"


@dataclass(frozen=True)
class AtlasConfig:
    tgenie_url: str | None = None


class AtlasConfigStore:
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.config_path = config_dir / "config.json"

    @property
    def chrome_profile_dir(self) -> Path:
        return self.config_dir / "chrome-profile"

    def load(self) -> AtlasConfig:
        if not self.config_path.exists():
            return AtlasConfig()
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        tgenie_url = payload.get("tgenie_url")
        return AtlasConfig(tgenie_url=tgenie_url if isinstance(tgenie_url, str) else None)

    def save_tgenie_url(self, url: str) -> None:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise ValueError("tGenie URL is required.")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload = {"tgenie_url": cleaned_url}
        self.config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class TgenieBrowserLaunchError(RuntimeError):
    pass


@dataclass
class TgenieLoginBrowserSession:
    context: Any
    playwright: Any

    async def close(self) -> None:
        await self.context.close()
        await self.playwright.stop()


class TgenieBrowserLauncher:
    def __init__(self, playwright_manager_factory: Callable[[], Any] | None = None) -> None:
        self.playwright_manager_factory = playwright_manager_factory

    async def open_login_browser(self, url: str, profile_dir: Path) -> TgenieLoginBrowserSession:
        profile_dir.mkdir(parents=True, exist_ok=True)
        playwright: Any | None = None
        try:
            manager = self._create_playwright_manager()
            playwright = await manager.start()
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=False,
                viewport=None,
                args=["--start-maximized"],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            return TgenieLoginBrowserSession(context=context, playwright=playwright)
        except Exception as error:
            if playwright is not None:
                await playwright.stop()
            raise TgenieBrowserLaunchError(
                "Could not open system Chrome. Install Google Chrome or check whether company policy allows Atlas to launch it."
            ) from error

    def _create_playwright_manager(self) -> Any:
        if self.playwright_manager_factory is not None:
            return self.playwright_manager_factory()
        from playwright.async_api import async_playwright

        return async_playwright()
