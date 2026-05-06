from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from server.web_driver_monitor.app import app
from server.web_driver_monitor.events import EventResult


class WebDriverMonitorAppTests(unittest.TestCase):
    def test_submit_event_returns_json_error_instead_of_internal_server_error(self) -> None:
        async def fake_submit(_event):  # noqa: ANN001
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            fut.set_result(
                EventResult(
                    event_id=uuid4(),
                    status="error",
                    message="PermissionError: access denied",
                )
            )
            return fut

        with patch("server.web_driver_monitor.app.bus.submit", side_effect=fake_submit):
            with patch("server.web_driver_monitor.app.bus.start", new=AsyncMock()):
                with patch("server.web_driver_monitor.app.bus.stop", new=AsyncMock()):
                    with patch("server.web_driver_monitor.app.runtime.start", new=AsyncMock()):
                        with patch("server.web_driver_monitor.app.runtime.stop", new=AsyncMock()):
                            with TestClient(app) as client:
                                response = client.post(
                                    "/v1/events:submit",
                                    json={"type": "page.eval", "payload": {"script": "() => 1"}, "wait": True},
                                )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("detail", payload)
        self.assertEqual(payload["detail"]["status"], "error")
        self.assertEqual(payload["detail"]["message"], "PermissionError: access denied")
        self.assertIsInstance(payload["detail"]["event_id"], str)


if __name__ == "__main__":
    unittest.main()
