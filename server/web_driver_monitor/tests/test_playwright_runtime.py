from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from server.web_driver_monitor.playwright_runtime import PlaywrightRuntime


class _FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self.evaluate_calls: list[tuple[str, object]] = []
        self.close_calls = 0

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def evaluate(self, script: str, arg=None) -> None:  # noqa: ANN001
        self.evaluate_calls.append((script, arg))

    async def close(self) -> None:
        self.close_calls += 1

    async def bring_to_front(self) -> None:
        return None


class _FakeContext:
    def __init__(self, pages: list[_FakePage] | None = None) -> None:
        self.pages = list(pages or [])
        self.new_page_calls = 0
        self.close_calls = 0
        self.add_cookies_calls: list[list[dict]] = []

    async def new_page(self) -> _FakePage:
        self.new_page_calls += 1
        page = _FakePage()
        self.pages.append(page)
        return page

    async def add_cookies(self, cookies: list[dict]) -> None:
        self.add_cookies_calls.append(cookies)

    async def close(self) -> None:
        self.close_calls += 1


class _FakeBrowserLauncher:
    def __init__(self, *, persistent_context: _FakeContext | None = None) -> None:
        self.persistent_context = persistent_context
        self.launch_persistent_context_calls: list[dict] = []

    async def launch_persistent_context(self, user_data_dir: str, **kwargs):
        self.launch_persistent_context_calls.append({"user_data_dir": user_data_dir, **kwargs})
        return self.persistent_context


class _FakePlaywright:
    def __init__(self, launcher: _FakeBrowserLauncher) -> None:
        self.chromium = launcher
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakeAsyncPlaywrightManager:
    def __init__(self, playwright: _FakePlaywright) -> None:
        self.playwright = playwright

    async def start(self) -> _FakePlaywright:
        return self.playwright


class PlaywrightRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_uses_persistent_context_with_user_data_dir(self) -> None:
        existing_page = _FakePage(url="https://example.com")
        persistent_context = _FakeContext(pages=[existing_page])
        launcher = _FakeBrowserLauncher(persistent_context=persistent_context)
        playwright = _FakePlaywright(launcher)
        fake_module = types.SimpleNamespace(async_playwright=lambda: _FakeAsyncPlaywrightManager(playwright))

        runtime = PlaywrightRuntime(
            browser_type="chromium",
            headless=False,
            user_data_dir=r"C:\Users\demo\AppData\Local\Google\Chrome\User Data",
            browser_channel="chrome",
            browser_profile_directory="Default",
        )

        with patch.dict(sys.modules, {"playwright.async_api": fake_module}):
            await runtime.start()

        self.assertTrue(runtime.started)
        self.assertEqual(
            launcher.launch_persistent_context_calls,
            [
                {
                    "user_data_dir": r"C:\Users\demo\AppData\Local\Google\Chrome\User Data",
                    "headless": False,
                    "channel": "chrome",
                    "args": ["--profile-directory=Default"],
                }
            ],
        )
        self.assertEqual(persistent_context.new_page_calls, 0)
        self.assertEqual(await runtime.page_url(), "https://example.com")
        await runtime.stop()
        self.assertEqual(persistent_context.close_calls, 1)
        self.assertEqual(playwright.stop_calls, 1)

    async def test_start_uses_default_dedicated_profile_dir_when_user_data_dir_not_set(self) -> None:
        persistent_context = _FakeContext()
        launcher = _FakeBrowserLauncher(persistent_context=persistent_context)
        playwright = _FakePlaywright(launcher)
        fake_module = types.SimpleNamespace(async_playwright=lambda: _FakeAsyncPlaywrightManager(playwright))

        runtime = PlaywrightRuntime(browser_type="chromium", headless=True)

        with patch.dict(sys.modules, {"playwright.async_api": fake_module}):
            await runtime.start()

        self.assertTrue(runtime.started)
        self.assertEqual(len(launcher.launch_persistent_context_calls), 1)
        user_data_dir = launcher.launch_persistent_context_calls[0]["user_data_dir"]
        self.assertTrue(user_data_dir.endswith("web_driver_monitor_profile"))
        self.assertEqual(persistent_context.new_page_calls, 1)

    async def test_start_imports_storage_state_into_persistent_profile(self) -> None:
        persistent_context = _FakeContext()
        launcher = _FakeBrowserLauncher(persistent_context=persistent_context)
        playwright = _FakePlaywright(launcher)
        fake_module = types.SimpleNamespace(async_playwright=lambda: _FakeAsyncPlaywrightManager(playwright))

        storage_state_path = Path(__file__).resolve().parent / "fixtures" / "storage_state.json"

        runtime = PlaywrightRuntime(
            browser_type="chromium",
            headless=False,
            storage_state_path=str(storage_state_path),
            user_data_dir=r"C:\Users\demo\AppData\Local\Microsoft\Edge\User Data\AutomationProfile",
        )

        with patch.dict(sys.modules, {"playwright.async_api": fake_module}):
            await runtime.start()

        self.assertEqual(
            persistent_context.add_cookies_calls,
            [[{"name": "sessionid", "value": "abc123", "domain": ".example.com", "path": "/"}]],
        )
        self.assertEqual(persistent_context.new_page_calls, 2)
        seeded_page = persistent_context.pages[-1]
        self.assertEqual(seeded_page.goto_calls, ["https://example.com"])
        self.assertEqual(len(seeded_page.evaluate_calls), 1)
        script, payload = seeded_page.evaluate_calls[0]
        self.assertIn("window.localStorage.setItem", script)
        self.assertEqual(payload, [{"name": "token", "value": "secret-token"}])


if __name__ == "__main__":
    unittest.main()
