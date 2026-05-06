from __future__ import annotations

import unittest

from server.web_driver_monitor.events import BusEvent, EventResult
from server.web_driver_monitor.watchdogs.handles import (
    build_handle_steps,
    create_handle_execute_handler,
)


class WatchdogHandleTests(unittest.IsolatedAsyncioTestCase):
    def test_build_handle_steps_fill_form_expands_atomic_fill_steps(self) -> None:
        steps = build_handle_steps(
            "fill_form",
            {"fields": {"#email": "user@example.com", "#password": "secret"}},
        )

        self.assertEqual(
            [(step.event_type, step.payload) for step in steps],
            [
                ("page.fill", {"selector": "#email", "text": "user@example.com"}),
                ("page.fill", {"selector": "#password", "text": "secret"}),
            ],
        )

    def test_build_handle_steps_click_then_wait_appends_wait_step(self) -> None:
        steps = build_handle_steps(
            "click_then_wait",
            {"selector": "#submit", "wait_for": {"selector": "#dashboard", "state": "visible"}},
        )

        self.assertEqual(
            [(step.event_type, step.payload) for step in steps],
            [
                ("page.click", {"selector": "#submit"}),
                ("page.wait_for", {"selector": "#dashboard", "state": "visible"}),
            ],
        )

    def test_build_handle_steps_login_form_expands_fill_submit_wait(self) -> None:
        steps = build_handle_steps(
            "login_form",
            {
                "username_selector": "#email",
                "username": "user@example.com",
                "password_selector": "#password",
                "password": "secret",
                "submit_selector": "#submit",
                "wait_for_url": "**/dashboard",
            },
        )

        self.assertEqual(
            [(step.event_type, step.payload) for step in steps],
            [
                ("page.fill", {"selector": "#email", "text": "user@example.com"}),
                ("page.fill", {"selector": "#password", "text": "secret"}),
                ("page.click", {"selector": "#submit"}),
                ("page.wait_for_url", {"url": "**/dashboard"}),
            ],
        )

    def test_build_handle_steps_dismiss_modal_then_click_uses_two_clicks(self) -> None:
        steps = build_handle_steps(
            "dismiss_modal_then_click",
            {"dismiss_selector": ".modal-close", "target_selector": "#continue"},
        )

        self.assertEqual(
            [(step.event_type, step.payload) for step in steps],
            [
                ("page.click", {"selector": ".modal-close"}),
                ("page.click", {"selector": "#continue"}),
            ],
        )

    def test_build_handle_steps_wait_and_retry_click_adds_before_and_after_waits(self) -> None:
        steps = build_handle_steps(
            "wait_and_retry_click",
            {
                "selector": "#submit",
                "wait_for": {"selector": "#submit", "state": "visible"},
                "after_wait_for": {"selector": "#dashboard", "state": "visible"},
            },
        )

        self.assertEqual(
            [(step.event_type, step.payload) for step in steps],
            [
                ("page.wait_for", {"selector": "#submit", "state": "visible"}),
                ("page.click", {"selector": "#submit"}),
                ("page.wait_for", {"selector": "#dashboard", "state": "visible"}),
            ],
        )

    async def test_handle_execute_runs_atomic_handlers_in_order(self) -> None:
        calls: list[tuple[str, dict]] = []

        async def click_handler(event: BusEvent) -> EventResult:
            calls.append((event.type, event.payload))
            return EventResult(event_id=event.id, status="ok", message="clicked", data={"url": "https://example.com"})

        async def wait_handler(event: BusEvent) -> EventResult:
            calls.append((event.type, event.payload))
            return EventResult(
                event_id=event.id,
                status="ok",
                message="waited",
                data={"url": "https://example.com/dashboard"},
            )

        handler = create_handle_execute_handler(
            {
                "page.click": click_handler,
                "page.wait_for": wait_handler,
            }
        )
        result = await handler(
            BusEvent(
                type="handle.execute",
                payload={
                    "name": "click_then_wait",
                    "args": {"selector": "#submit", "wait_for": {"selector": "#dashboard"}},
                },
            )
        )

        self.assertEqual(
            calls,
            [
                ("page.click", {"selector": "#submit"}),
                ("page.wait_for", {"selector": "#dashboard"}),
            ],
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["handle_name"], "click_then_wait")
        self.assertEqual(result.data["executed_steps"], ["page.click", "page.wait_for"])
        self.assertEqual(result.data["url"], "https://example.com/dashboard")

    async def test_handle_execute_stops_on_atomic_handler_error(self) -> None:
        calls: list[tuple[str, dict]] = []

        async def click_handler(event: BusEvent) -> EventResult:
            calls.append((event.type, event.payload))
            return EventResult(event_id=event.id, status="ok", message="clicked", data={"url": "https://example.com"})

        async def wait_handler(event: BusEvent) -> EventResult:
            calls.append((event.type, event.payload))
            return EventResult(event_id=event.id, status="error", message="timeout")

        handler = create_handle_execute_handler(
            {
                "page.click": click_handler,
                "page.wait_for": wait_handler,
            }
        )
        result = await handler(
            BusEvent(
                type="handle.execute",
                payload={
                    "name": "click_then_wait",
                    "args": {"selector": "#submit", "wait_for": {"selector": "#dashboard"}},
                },
            )
        )

        self.assertEqual(
            calls,
            [
                ("page.click", {"selector": "#submit"}),
                ("page.wait_for", {"selector": "#dashboard"}),
            ],
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["handle_name"], "click_then_wait")
        self.assertEqual(result.data["failed_step"]["event_type"], "page.wait_for")
        self.assertEqual(result.data["executed_steps"], ["page.click", "page.wait_for"])

    async def test_handle_execute_runs_login_form_sequence(self) -> None:
        calls: list[tuple[str, dict]] = []

        async def ok_handler(event: BusEvent) -> EventResult:
            calls.append((event.type, event.payload))
            return EventResult(event_id=event.id, status="ok", message=event.type, data={"url": "https://example.com"})

        handler = create_handle_execute_handler(
            {
                "page.fill": ok_handler,
                "page.click": ok_handler,
                "page.wait_for_url": ok_handler,
            }
        )
        result = await handler(
            BusEvent(
                type="handle.execute",
                payload={
                    "name": "login_form",
                    "args": {
                        "username_selector": "#email",
                        "username": "user@example.com",
                        "password_selector": "#password",
                        "password": "secret",
                        "submit_selector": "#submit",
                        "wait_for_url": "**/dashboard",
                    },
                },
            )
        )

        self.assertEqual(
            calls,
            [
                ("page.fill", {"selector": "#email", "text": "user@example.com"}),
                ("page.fill", {"selector": "#password", "text": "secret"}),
                ("page.click", {"selector": "#submit"}),
                ("page.wait_for_url", {"url": "**/dashboard"}),
            ],
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.data["executed_steps"],
            ["page.fill", "page.fill", "page.click", "page.wait_for_url"],
        )


if __name__ == "__main__":
    unittest.main()
