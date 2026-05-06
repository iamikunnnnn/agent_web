from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
AGNO_LIBS = Path(r"C:\Users\WUJIEAI\PycharmProjects\project_zip\agno\libs\agno")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(AGNO_LIBS) not in sys.path:
    sys.path.insert(0, str(AGNO_LIBS))

from agno.workflow import StepInput

from workflow.browser_workflow import (
    CURRENT_ROUND_RAW_STATE_KEY,
    PERSISTENT_BROWSER_STATE_KEY,
    BrowserAction,
    BrowserDecision,
    browser_loop_end_condition,
    decide_browser_action,
    execute_browser_action,
    observe_current_page,
    summarize_browser_snapshot,
    verify_browser_progress,
)


def _sample_snapshot() -> dict:
    return {
        "accepted": True,
        "result": {
            "status": "ok",
            "message": "evaluated",
            "data": {
                "url": "https://example.com/login",
                "result": {"title": "Login", "readyState": "complete"},
                "dom": {
                    "url": "https://example.com/login",
                    "count": 3,
                    "returned": 3,
                    "elements": [
                        {
                            "tag": "input",
                            "text": "",
                            "selector": "#email",
                            "role": "textbox",
                            "type": "email",
                            "placeholder": "Email",
                            "aria_label": "Email",
                        },
                        {
                            "tag": "input",
                            "text": "",
                            "selector": "#password",
                            "role": "textbox",
                            "type": "password",
                            "placeholder": "Password",
                            "aria_label": "Password",
                        },
                        {
                            "tag": "button",
                            "text": "Sign in",
                            "selector": "#submit",
                            "role": "button",
                            "aria_label": "Sign in",
                        },
                    ],
                },
                "screenshot_base64": "abc123",
                "screenshot_type": "jpeg",
            },
        },
    }


def _run_context(session_state: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(session_state=session_state or {})


class BrowserWorkflowTests(unittest.TestCase):
    def test_summarize_browser_snapshot_removes_large_fields(self) -> None:
        summary = summarize_browser_snapshot(_sample_snapshot(), goal="log in and reach the home page")

        self.assertEqual(summary["goal"], "log in and reach the home page")
        self.assertNotIn("screenshot_base64", summary)
        self.assertEqual(summary["page"]["url"], "https://example.com/login")
        self.assertEqual(summary["page"]["title"], "Login")
        self.assertEqual(summary["page"]["interactable_count"], 3)
        self.assertEqual(len(summary["top_candidates"]), 3)
        self.assertEqual(summary["top_candidates"][0]["selector"], "#email")

    def test_observe_current_page_stores_raw_only_in_current_round_state(self) -> None:
        run_context = _run_context()

        with patch("workflow.browser_workflow.submit_browser_event", return_value=_sample_snapshot()):
            output = observe_current_page(StepInput(input="log in"), run_context=run_context)

        self.assertTrue(output.success)
        self.assertEqual(output.content["page"]["url"], "https://example.com/login")
        self.assertNotIn("screenshot_base64", str(output.content))

        browser_state = run_context.session_state[PERSISTENT_BROWSER_STATE_KEY]
        current_round_state = run_context.session_state[CURRENT_ROUND_RAW_STATE_KEY]

        self.assertEqual(browser_state["goal"], "log in")
        self.assertEqual(browser_state["iteration"], 1)
        self.assertNotIn("screenshot_base64", str(browser_state["last_observation_summary"]))
        self.assertIn("raw_observation", current_round_state)
        self.assertEqual(current_round_state["raw_observation"]["screenshot_base64"], "abc123")
        self.assertIn("dom", current_round_state["raw_observation"])

    def test_decide_browser_action_sends_string_prompt_with_persistent_and_current_round_state(self) -> None:
        captured: dict[str, object] = {}
        run_context = _run_context(
            {
                PERSISTENT_BROWSER_STATE_KEY: {
                    "goal": "open baidu",
                    "iteration": 2,
                    "last_execution": {"status": "acted", "event_type": "page.goto"},
                    "action_history": [{"event_type": "page.goto", "payload": {"url": "https://example.com"}}],
                },
                CURRENT_ROUND_RAW_STATE_KEY: {
                    "raw_observation": {
                        "dom": {"elements": [{"selector": "#kw", "tag": "input"}]},
                        "screenshot_base64": "abc123",
                        "screenshot_type": "jpeg",
                    }
                },
            }
        )

        class FakeAgent:
            def run(self, *, input, stream, stream_events, run_context):  # noqa: ANN001
                captured["input"] = input
                captured["stream"] = stream
                captured["stream_events"] = stream_events
                captured["run_context"] = run_context

                class _Response:
                    content = BrowserDecision(
                        status="act",
                        reason="navigate",
                        action=BrowserAction(event_type="page.click", payload={"selector": "#kw"}),
                    )

                return _Response()

        with patch("workflow.browser_workflow._get_browser_agent", return_value=FakeAgent()):
            output = decide_browser_action(StepInput(input="search on current page"), run_context=run_context)

        self.assertIsInstance(captured["input"], str)
        self.assertIn("Persistent browser state from previous rounds", captured["input"])
        self.assertIn("Current round raw browser observation", captured["input"])
        self.assertIn("abc123", captured["input"])
        self.assertIn("#kw", captured["input"])
        self.assertFalse(captured["stream"])
        self.assertFalse(captured["stream_events"])
        self.assertIs(captured["run_context"], run_context)
        self.assertEqual(output.content.status, "act")
        self.assertEqual(output.content.action.event_type, "page.click")
        self.assertEqual(run_context.session_state[PERSISTENT_BROWSER_STATE_KEY]["last_decision"]["action"]["payload"]["selector"], "#kw")

    def test_decide_browser_action_short_circuits_known_site_goal(self) -> None:
        run_context = _run_context()

        with patch("workflow.browser_workflow._get_browser_agent") as get_agent:
            output = decide_browser_action(StepInput(input="打开百度"), run_context=run_context)

        get_agent.assert_not_called()
        self.assertEqual(output.content.status, "act")
        self.assertEqual(output.content.action.event_type, "page.goto")
        self.assertEqual(output.content.action.payload, {"url": "https://www.baidu.com"})

    def test_decide_browser_action_marks_known_site_goal_done_when_already_on_site(self) -> None:
        run_context = _run_context(
            {
                PERSISTENT_BROWSER_STATE_KEY: {"goal": "打开百度", "iteration": 1},
                CURRENT_ROUND_RAW_STATE_KEY: {
                    "observation_summary": {
                        "goal": "打开百度",
                        "page": {
                            "url": "https://www.baidu.com/s?wd=agno",
                            "title": "百度一下，你就知道",
                            "ready_state": "complete",
                        },
                        "last_result": {"status": "ok", "message": "evaluated"},
                        "top_candidates": [],
                    }
                },
            }
        )

        with patch("workflow.browser_workflow._get_browser_agent") as get_agent:
            output = decide_browser_action(StepInput(input="打开百度"), run_context=run_context)

        get_agent.assert_not_called()
        self.assertEqual(output.content.status, "done")
        self.assertIsNone(output.content.action)
        self.assertIn("already", output.content.reason.lower())

    def test_execute_browser_action_stops_immediately_when_done_and_clears_current_round(self) -> None:
        run_context = _run_context(
            {
                CURRENT_ROUND_RAW_STATE_KEY: {"raw_observation": {"dom": {"elements": []}, "screenshot_base64": "abc123"}}
            }
        )
        decision = BrowserDecision(status="done", reason="task complete", action=None)

        output = execute_browser_action(
            StepInput(input="log in and reach the home page", previous_step_content=decision),
            run_context=run_context,
        )

        self.assertTrue(output.stop)
        self.assertTrue(output.success)
        self.assertEqual(output.content["status"], "done")
        self.assertNotIn(CURRENT_ROUND_RAW_STATE_KEY, run_context.session_state)

    def test_execute_browser_action_dispatches_atomic_event_without_persisting_raw_fields(self) -> None:
        run_context = _run_context(
            {
                CURRENT_ROUND_RAW_STATE_KEY: {
                    "raw_observation": {"dom": {"elements": [{"selector": "#submit"}]}, "screenshot_base64": "abc123"}
                }
            }
        )
        calls: list[tuple[str, dict]] = []

        def fake_submit(event_type: str, payload: dict, wait: bool = True) -> dict:
            calls.append((event_type, payload))
            self.assertTrue(wait)
            return {
                "accepted": True,
                "result": {
                    "status": "ok",
                    "message": "clicked",
                    "data": {
                        "url": "https://example.com/dashboard",
                        "dom": {"count": 1, "returned": 1, "elements": []},
                        "screenshot_base64": "should_not_escape",
                    },
                },
            }

        decision = BrowserDecision(
            status="act",
            reason="click the sign in button",
            action=BrowserAction(event_type="page.click", payload={"selector": "#submit"}),
        )

        with patch("workflow.browser_workflow.submit_browser_event", side_effect=fake_submit):
            output = execute_browser_action(
                StepInput(input="log in and reach the home page", previous_step_content=decision),
                run_context=run_context,
            )

        self.assertEqual(calls, [("page.click", {"selector": "#submit"})])
        self.assertFalse(output.stop)
        self.assertTrue(output.success)
        self.assertEqual(output.content["status"], "acted")
        self.assertEqual(output.content["event_type"], "page.click")
        self.assertNotIn("screenshot_base64", str(output.content))

        browser_state = run_context.session_state[PERSISTENT_BROWSER_STATE_KEY]
        self.assertNotIn("screenshot_base64", str(browser_state["last_execution"]))
        self.assertEqual(browser_state["action_history"][-1]["event_type"], "page.click")
        self.assertIn(CURRENT_ROUND_RAW_STATE_KEY, run_context.session_state)

    def test_verify_browser_progress_clears_current_round_state_and_persists_summary(self) -> None:
        run_context = _run_context(
            {
                PERSISTENT_BROWSER_STATE_KEY: {"goal": "log in"},
                CURRENT_ROUND_RAW_STATE_KEY: {"raw_observation": {"dom": {"elements": []}, "screenshot_base64": "abc123"}},
            }
        )

        output = verify_browser_progress(
            StepInput(
                input="log in",
                previous_step_content={
                    "status": "acted",
                    "reason": "clicked sign in",
                    "page": {"url": "https://example.com/dashboard"},
                },
            ),
            run_context=run_context,
        )

        self.assertTrue(output.success)
        self.assertEqual(output.content["status"], "acted")
        self.assertNotIn(CURRENT_ROUND_RAW_STATE_KEY, run_context.session_state)
        self.assertEqual(
            run_context.session_state[PERSISTENT_BROWSER_STATE_KEY]["last_verification"],
            {
                "status": "acted",
                "reason": "clicked sign in",
                "page": {"url": "https://example.com/dashboard"},
            },
        )

    def test_verify_browser_progress_finishes_navigation_goal_when_target_page_reached(self) -> None:
        run_context = _run_context(
            {
                PERSISTENT_BROWSER_STATE_KEY: {"goal": "打开百度"},
                CURRENT_ROUND_RAW_STATE_KEY: {"raw_observation": {"dom": {"elements": []}, "screenshot_base64": "abc123"}},
            }
        )

        output = verify_browser_progress(
            StepInput(
                input="打开百度",
                previous_step_content={
                    "status": "acted",
                    "reason": "navigated",
                    "page": {"url": "https://www.baidu.com/", "title": "百度一下，你就知道"},
                },
            ),
            run_context=run_context,
        )

        self.assertTrue(output.success)
        self.assertTrue(output.stop)
        self.assertEqual(output.content["status"], "done")
        self.assertIn("target page", output.content["reason"].lower())
        self.assertNotIn(CURRENT_ROUND_RAW_STATE_KEY, run_context.session_state)

    def test_browser_loop_end_condition_checks_stop_flag(self) -> None:
        done = execute_browser_action(
            StepInput(input="task", previous_step_content=BrowserDecision(status="done", reason="ok", action=None)),
            run_context=_run_context(),
        )

        self.assertTrue(browser_loop_end_condition([done]))


if __name__ == "__main__":
    unittest.main()
