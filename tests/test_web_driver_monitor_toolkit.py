from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
AGNO_LIBS = Path(r"C:\Users\WUJIEAI\PycharmProjects\project_zip\agno\libs\agno")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(AGNO_LIBS) not in sys.path:
    sys.path.insert(0, str(AGNO_LIBS))

from tools.web_driver_monitor_toolkit import (  # noqa: E402
    BROWSER_CURRENT_ROUND_STATE_KEY,
    BROWSER_SESSION_STATE_KEY,
    clear_browser_transient_state,
    process_browser_event_result,
)


def _sample_browser_response() -> dict:
    return {
        "accepted": True,
        "result": {
            "status": "ok",
            "message": "clicked",
            "data": {
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "result": {"title": "一个视频", "readyState": "complete"},
                "dom": {
                    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                    "count": 2,
                    "returned": 2,
                    "elements": [
                        {"tag": "button", "text": "播放", "selector": ".play-btn", "role": "button"},
                        {"tag": "input", "text": "", "selector": ".search-input", "role": "textbox", "placeholder": "搜索"},
                    ],
                },
                "screenshot_base64": "abc123",
                "screenshot_type": "jpeg",
                "screenshot_full_page": False,
            },
        },
    }


class WebDriverMonitorToolkitTests(unittest.TestCase):
    def test_process_browser_event_result_returns_compact_summary_and_stores_raw_transient_state(self) -> None:
        run_context = SimpleNamespace(session_state={})

        summary = process_browser_event_result(
            event_type="page.click",
            payload={"selector": ".play-btn"},
            response=_sample_browser_response(),
            run_context=run_context,
        )

        self.assertEqual(summary["event_type"], "page.click")
        self.assertEqual(summary["page"]["url"], "https://www.bilibili.com/video/BV1xx411c7mD")
        self.assertEqual(summary["top_candidates"][0]["selector"], ".search-input")
        self.assertNotIn("screenshot_base64", str(summary))

        browser_state = run_context.session_state[BROWSER_SESSION_STATE_KEY]
        current_round = run_context.session_state[BROWSER_CURRENT_ROUND_STATE_KEY]
        self.assertEqual(browser_state["last_tool_result"]["event_type"], "page.click")
        self.assertNotIn("screenshot_base64", str(browser_state))
        self.assertEqual(current_round["raw_observation"]["screenshot_base64"], "abc123")
        self.assertIn("dom", current_round["raw_observation"])

    def test_clear_browser_transient_state_removes_only_current_round_raw_snapshot(self) -> None:
        run_context = SimpleNamespace(
            session_state={
                BROWSER_SESSION_STATE_KEY: {"last_tool_result": {"event_type": "page.goto"}},
                BROWSER_CURRENT_ROUND_STATE_KEY: {"raw_observation": {"screenshot_base64": "abc123"}},
            }
        )

        clear_browser_transient_state(run_context)

        self.assertIn(BROWSER_SESSION_STATE_KEY, run_context.session_state)
        self.assertNotIn(BROWSER_CURRENT_ROUND_STATE_KEY, run_context.session_state)


if __name__ == "__main__":
    unittest.main()
