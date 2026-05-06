from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

_LOCAL_STORAGE_SEED_SCRIPT = """
(items) => {
    for (const item of items) {
        window.localStorage.setItem(item.name, item.value);
    }
}
""".strip()


def _default_profile_dir() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return str((repo_root / "db" / "user_data" / "web_driver_monitor_profile").resolve())


class PlaywrightRuntime:
    """
    Owns a single long-lived Playwright persistent browser context/page.

    All operations are serialized through an asyncio.Lock to keep DOM operations
    atomic and deterministic.
    """

    def __init__(
        self,
        *,
        browser_type: Literal["chromium", "firefox", "webkit"] = "chromium",
        headless: bool = True,
        user_data_dir: str | None = None,
        browser_channel: str | None = None,
        browser_profile_directory: str | None = None,
        storage_state_path: str | None = None,
    ) -> None:
        import asyncio

        self._browser_type = browser_type
        self._headless = headless
        self._user_data_dir = str(Path(user_data_dir).expanduser()) if user_data_dir else _default_profile_dir()
        self._browser_channel = browser_channel.strip() if browser_channel else None
        self._browser_profile_directory = browser_profile_directory.strip() if browser_profile_directory else None
        self._storage_state_path = str(Path(storage_state_path).expanduser()) if storage_state_path else None

        self._lock = asyncio.Lock()
        self._started = False

        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._pages: list[Any] = []
        self._active_page_index: int = 0

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        try:
            from playwright.async_api import (
                async_playwright,  # type: ignore[import-not-found]
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Playwright is not available. Install it (pip install playwright) and run `playwright install`."
            ) from exc

        self._playwright = await async_playwright().start()
        browser_launcher = getattr(self._playwright, self._browser_type)
        launch_kwargs: dict[str, Any] = {"headless": self._headless}
        if self._browser_channel:
            launch_kwargs["channel"] = self._browser_channel
        if self._browser_profile_directory:
            launch_kwargs["args"] = [f"--profile-directory={self._browser_profile_directory}"]

        self._context = await browser_launcher.launch_persistent_context(self._user_data_dir, **launch_kwargs)
        self._browser = None
        existing_pages = list(getattr(self._context, "pages", []) or [])
        self._pages = existing_pages if existing_pages else [await self._context.new_page()]

        if self._storage_state_path:
            await self._seed_storage_state(self._storage_state_path)

        self._active_page_index = 0
        self._started = True

    async def _seed_storage_state(self, storage_state_path: str) -> None:
        storage_state_file = Path(storage_state_path)
        if not storage_state_file.exists():
            raise RuntimeError(f"storage_state_path does not exist: {storage_state_path}")

        try:
            state = json.loads(storage_state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid storage state JSON: {storage_state_path}") from exc

        if not isinstance(state, dict):
            raise RuntimeError(f"Storage state must be a JSON object: {storage_state_path}")

        cookies = state.get("cookies", [])
        if cookies:
            if not isinstance(cookies, list) or not all(isinstance(cookie, dict) for cookie in cookies):
                raise RuntimeError("storage_state cookies must be a list of objects")
            await self._context.add_cookies(cookies)

        origins = state.get("origins", [])
        if not isinstance(origins, list):
            raise RuntimeError("storage_state origins must be a list")

        for origin_state in origins:
            if not isinstance(origin_state, dict):
                continue
            origin = origin_state.get("origin")
            local_storage = origin_state.get("localStorage", [])
            if not isinstance(origin, str) or not origin.strip() or not local_storage:
                continue
            if not isinstance(local_storage, list) or not all(isinstance(item, dict) for item in local_storage):
                raise RuntimeError("storage_state localStorage must be a list of objects")

            page = await self._context.new_page()
            try:
                await page.goto(origin)
                await page.evaluate(_LOCAL_STORAGE_SEED_SCRIPT, local_storage)
            finally:
                await page.close()

    async def stop(self) -> None:
        if not self._started:
            return
        async with self._lock:
            try:
                if self._context:
                    await self._context.close()
            finally:
                self._context = None
                self._browser = None
                try:
                    if self._playwright:
                        await self._playwright.stop()
                finally:
                    self._playwright = None
                    self._pages = []
                    self._active_page_index = 0
                    self._started = False

    def _get_active_page(self) -> Any:
        if not self._pages:
            raise RuntimeError("No pages are available")
        if self._active_page_index < 0 or self._active_page_index >= len(self._pages):
            self._active_page_index = 0
        return self._pages[self._active_page_index]

    async def run(self, fn, /, *args, **kwargs):
        if not self._started:
            await self.start()
        async with self._lock:
            page = self._get_active_page()
            return await fn(page, *args, **kwargs)

    async def page_url(self) -> str | None:
        if not self._started or not self._pages:
            return None
        async with self._lock:
            try:
                return self._get_active_page().url
            except Exception:
                return None

    async def tabs(self) -> list[dict[str, Any]]:
        if not self._started:
            await self.start()
        async with self._lock:
            out: list[dict[str, Any]] = []
            for idx, page in enumerate(self._pages):
                try:
                    url = page.url
                except Exception:
                    url = None
                out.append({"index": idx, "active": idx == self._active_page_index, "url": url})
            return out

    async def new_tab(self, url: str | None = None) -> dict[str, Any]:
        if not self._started:
            await self.start()
        async with self._lock:
            if not self._context:
                raise RuntimeError("Browser context is not available")
            page = await self._context.new_page()
            self._pages.append(page)
            self._active_page_index = len(self._pages) - 1
            if url:
                await page.goto(url)
            return {"active_index": self._active_page_index, "url": page.url}

    async def switch_tab(self, index: int) -> dict[str, Any]:
        if not self._started:
            await self.start()
        async with self._lock:
            if index < 0 or index >= len(self._pages):
                raise ValueError(f"Invalid tab index {index}; available: 0..{len(self._pages)-1}")
            self._active_page_index = index
            page = self._get_active_page()
            try:
                await page.bring_to_front()
            except Exception:
                pass
            return {"active_index": self._active_page_index, "url": page.url}

    async def close_tab(self, index: int | None = None) -> dict[str, Any]:
        if not self._started:
            await self.start()
        async with self._lock:
            if not self._pages:
                raise RuntimeError("No tabs to close")
            idx = self._active_page_index if index is None else index
            if idx < 0 or idx >= len(self._pages):
                raise ValueError(f"Invalid tab index {idx}; available: 0..{len(self._pages)-1}")
            page = self._pages.pop(idx)
            try:
                await page.close()
            except Exception:
                pass

            if not self._pages:
                if not self._context:
                    raise RuntimeError("Browser context is not available")
                self._pages = [await self._context.new_page()]
                self._active_page_index = 0
            else:
                self._active_page_index = min(self._active_page_index, len(self._pages) - 1)
            active = self._get_active_page()
            return {"active_index": self._active_page_index, "url": active.url}
