from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
AGNO_LIBS = Path(r"C:\Users\WUJIEAI\PycharmProjects\project_zip\agno\libs\agno")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(AGNO_LIBS) not in sys.path:
    sys.path.insert(0, str(AGNO_LIBS))

from server.computer_mcp.main import computer_mcp_app  # noqa: E402


class ComputerMcpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(computer_mcp_app)

    def test_default_environment_keeps_browser_first_behavior(self) -> None:
        with patch("server.computer_mcp.main.submit_browser_event", return_value={"accepted": True}) as submit_mock:
            response = self.client.post(
                "/computer/action",
                json={"action": "click", "payload": {"selector": "#submit"}},
            )

        self.assertEqual(response.status_code, 200)
        submit_mock.assert_called_once_with(
            event_type="page.click",
            payload={"selector": "#submit"},
            wait=True,
        )

    def test_desktop_click_routes_to_pyautogui(self) -> None:
        fake_gui = SimpleNamespace(click=Mock())

        with patch("server.computer_mcp.main._get_pyautogui", return_value=fake_gui):
            response = self.client.post(
                "/computer/action",
                json={
                    "action": "click",
                    "payload": {"environment": "desktop", "x": 120, "y": 240, "button": "right"},
                },
            )

        self.assertEqual(response.status_code, 200)
        fake_gui.click.assert_called_once_with(x=120, y=240, button="right")
        self.assertEqual(response.json()["environment"], "desktop")

    def test_desktop_wait_uses_timeout_ms_fallback(self) -> None:
        with patch("server.computer_mcp.main.time.sleep") as sleep_mock:
            response = self.client.post(
                "/computer/action",
                json={"action": "wait", "payload": {"environment": "desktop", "timeout_ms": 1500}},
            )

        self.assertEqual(response.status_code, 200)
        sleep_mock.assert_called_once_with(1.5)

    def test_invalid_environment_returns_clear_error(self) -> None:
        response = self.client.post(
            "/computer/action",
            json={"action": "click", "payload": {"environment": "mobile", "selector": "#submit"}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "unsupported environment: mobile. expected 'browser' or 'desktop'",
        )


if __name__ == "__main__":
    unittest.main()
