from __future__ import annotations

import os
from typing import Any

import requests
from agno.run import RunContext
from agno.tools import Toolkit

BROWSER_SESSION_STATE_KEY = "browser_state"
BROWSER_CURRENT_ROUND_STATE_KEY = "_browser_current_round"
MAX_TOP_CANDIDATES = 8
MAX_TEXT_LENGTH = 120


def _wdm_base_url() -> str:
    return os.getenv("WDM_URL", "http://localhost:8010").rstrip("/")


def _submit(event_type: str, payload: dict[str, Any], wait: bool = True) -> dict[str, Any]:
    url = f"{_wdm_base_url()}/v1/events:submit"
    resp = requests.post(url, json={"type": event_type, "payload": payload, "wait": wait}, timeout=65)
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {"raw_text": resp.text}

    if resp.ok:
        return data
    return {"error": True, "status_code": resp.status_code, "detail": data}


def submit_browser_event(event_type: str, payload: dict[str, Any], wait: bool = True) -> dict[str, Any]:
    """Submit a browser event to the persistent web_driver_monitor service."""
    return _submit(event_type, payload, wait=wait)


def _ensure_session_state(run_context: RunContext | None) -> dict[str, Any]:
    if run_context is None:
        return {}
    if run_context.session_state is None:
        run_context.session_state = {}
    return run_context.session_state


def _ensure_browser_state(run_context: RunContext | None) -> dict[str, Any]:
    session_state = _ensure_session_state(run_context)
    return session_state.setdefault(BROWSER_SESSION_STATE_KEY, {})


def clear_browser_transient_state(run_context: RunContext | None = None, **_: Any) -> None:
    session_state = _ensure_session_state(run_context)
    session_state.pop(BROWSER_CURRENT_ROUND_STATE_KEY, None)


def _compact_text(value: Any, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    return text[:max_length]


def _extract_response_result(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    result = snapshot.get("result")
    return result if isinstance(result, dict) else {}


def _extract_response_data(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    result = _extract_response_result(snapshot)
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _extract_dom_elements(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = _extract_response_data(snapshot)
    dom = data.get("dom")
    if not isinstance(dom, dict):
        return []
    elements = dom.get("elements")
    if not isinstance(elements, list):
        return []
    return [element for element in elements if isinstance(element, dict)]


def _score_candidate(element: dict[str, Any]) -> int:
    score = 0
    tag = str(element.get("tag") or "").lower()
    role = str(element.get("role") or "").lower()
    text = _compact_text(element.get("text")) or ""

    if tag in {"button", "a", "input", "textarea", "select"}:
        score += 5
    if tag in {"input", "textarea", "select"}:
        score += 2
    if role in {"button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem", "tab"}:
        score += 4
    if element.get("selector"):
        score += 3
    if text:
        score += 2
    if element.get("placeholder"):
        score += 2
    if element.get("aria_label"):
        score += 2
    if tag == "input" and str(element.get("type") or "").lower() in {"email", "password", "search", "text"}:
        score += 2
    return score


def _summarize_candidate(element: dict[str, Any]) -> dict[str, Any]:
    return {
        "selector": _compact_text(element.get("selector")),
        "tag": _compact_text(element.get("tag")),
        "role": _compact_text(element.get("role")),
        "text": _compact_text(element.get("text")),
        "placeholder": _compact_text(element.get("placeholder")),
        "aria_label": _compact_text(element.get("aria_label")),
        "name": _compact_text(element.get("name")),
        "type": _compact_text(element.get("type")),
        "href": _compact_text(element.get("href")),
    }


def _extract_current_round_raw(snapshot: dict[str, Any]) -> dict[str, Any]:
    data = _extract_response_data(snapshot)
    return {
        "url": data.get("url"),
        "result": data.get("result"),
        "dom": data.get("dom"),
        "screenshot_base64": data.get("screenshot_base64"),
        "screenshot_type": data.get("screenshot_type"),
        "screenshot_full_page": data.get("screenshot_full_page"),
    }


def _summarize_browser_response(snapshot: dict[str, Any], event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = _extract_response_result(snapshot)
    data = _extract_response_data(snapshot)
    dom = data.get("dom") if isinstance(data.get("dom"), dict) else {}
    eval_result = data.get("result") if isinstance(data.get("result"), dict) else {}

    elements = _extract_dom_elements(snapshot)
    ranked_elements = sorted(elements, key=_score_candidate, reverse=True)
    top_candidates = [_summarize_candidate(element) for element in ranked_elements[:MAX_TOP_CANDIDATES]]

    page_url = _compact_text(data.get("url")) or _compact_text(dom.get("url")) or _compact_text(eval_result.get("locationHref"))
    page_title = _compact_text(eval_result.get("title"))
    ready_state = _compact_text(eval_result.get("readyState"))

    return {
        "event_type": event_type,
        "payload": payload,
        "page": {
            "url": page_url,
            "title": page_title,
            "ready_state": ready_state,
            "interactable_count": dom.get("count", len(elements)),
            "returned_count": dom.get("returned", len(elements)),
        },
        "last_result": {
            "status": _compact_text(result.get("status")),
            "message": _compact_text(result.get("message")),
        },
        "top_candidates": top_candidates,
    }


def process_browser_event_result(
    event_type: str,
    payload: dict[str, Any],
    response: dict[str, Any],
    run_context: RunContext | None = None,
) -> dict[str, Any]:
    browser_state = _ensure_browser_state(run_context)
    if response.get("error"):
        summary = {
            "event_type": event_type,
            "payload": payload,
            "status": "error",
            "detail": response.get("detail"),
        }
        browser_state["last_tool_result"] = summary
        return summary

    summary = _summarize_browser_response(response, event_type=event_type, payload=payload)
    browser_state["last_tool_result"] = summary
    _ensure_session_state(run_context)[BROWSER_CURRENT_ROUND_STATE_KEY] = {
        "event_type": event_type,
        "payload": payload,
        "raw_observation": _extract_current_round_raw(response),
        "observation_summary": summary,
    }
    return summary


class webDriverMonitorToolkit(Toolkit):
    def __init__(self, name: str = "NofxToolkit", *args, **kwargs) -> None:
        tools = [
            self.web_driver_event,
            self.web_driver_handle,
            self.web_driver_goto,
            self.web_driver_click,
            self.web_driver_click_text,
        ]
        super().__init__(name=name, tools=tools, *args, **kwargs)

    def web_driver_event(self, event_type: str, payload: dict, run_context: RunContext | None = None) -> dict:
        """
        Submit an atomic browser event to the web_driver_monitor service.

        Common event types (payload keys):
        - page.goto: {url, wait_until?, timeout_ms?}
        - page.click: {selector, timeout_ms?}
        - page.click_text: {text, exact?, timeout_ms?}
        - page.fill: {selector, text, timeout_ms?}
        - page.press: {key, selector?, timeout_ms?}
        - page.wait_for: {selector?, state?, timeout_ms?}  (if selector missing -> sleep)
        - page.screenshot: {full_page?, type?}
        - page.eval: {script}
        """
        return process_browser_event_result(
            event_type=event_type,
            payload=payload,
            response=_submit(event_type, payload, wait=True),
            run_context=run_context,
        )

    def web_driver_handle(self, name: str, args: dict | None = None, run_context: RunContext | None = None) -> dict:
        """
        Execute a named browser handle via the watchdog handle registry.

        Useful handles:
        - fill_form: {fields: {"#email": "...", "#password": "..."}}
        - click_then_wait: {selector, wait_for? | wait_for_url? | wait_for_load_state?}
        - type_and_submit: {selector, text, key?}
        - login_form: {username_selector, username, password_selector, password, submit_selector?, submit_text?, wait_for_url?}
        - dismiss_modal_then_click: {dismiss_selector, target_selector}
        - wait_and_retry_click: {selector, wait_for?, after_wait_for?}
        - atomic aliases: goto, click, click_text, click_role, fill, type, press, wait_for, wait_for_url, wait_for_load_state
        """
        payload = {"name": name, "args": args or {}}
        return process_browser_event_result(
            event_type="handle.execute",
            payload=payload,
            response=_submit("handle.execute", payload, wait=True),
            run_context=run_context,
        )

    def web_driver_goto(self, url: str, run_context: RunContext | None = None) -> dict:
        """Open a URL in the persistent Playwright page (atomic)."""
        payload = {"url": url}
        return process_browser_event_result(
            event_type="page.goto",
            payload=payload,
            response=_submit("page.goto", payload, wait=True),
            run_context=run_context,
        )

    def web_driver_click(self, selector: str, run_context: RunContext | None = None) -> dict:
        """Click a DOM element using a Playwright selector (atomic)."""
        payload = {"selector": selector}
        return process_browser_event_result(
            event_type="page.click",
            payload=payload,
            response=_submit("page.click", payload, wait=True),
            run_context=run_context,
        )

    def web_driver_click_text(self, text: str, exact: bool = False, run_context: RunContext | None = None) -> dict:
        """Click the first element that matches visible text (atomic)."""
        payload = {"text": text, "exact": exact}
        return process_browser_event_result(
            event_type="page.click_text",
            payload=payload,
            response=_submit("page.click_text", payload, wait=True),
            run_context=run_context,
        )
