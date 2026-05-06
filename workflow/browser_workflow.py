from __future__ import annotations

import json
import re
from typing import Any, Literal
from urllib.parse import urlparse

from agno.agent import Agent
from agno.run import RunContext
from agno.workflow import Loop, Step, StepInput, StepOutput, Workflow
from pydantic import BaseModel, Field

from config.db_config import create_base_db
from config.model_config import get_ai_model
from tools.web_driver_monitor_toolkit import submit_browser_event

OBSERVE_PAGE_SCRIPT = """
() => ({
  title: document.title || "",
  readyState: document.readyState || "",
  locationHref: window.location.href || ""
})
""".strip()

PERSISTENT_BROWSER_STATE_KEY = "browser_workflow"
CURRENT_ROUND_RAW_STATE_KEY = "_browser_workflow_current_round"
MAX_TOP_CANDIDATES = 8
MAX_TEXT_LENGTH = 120
DEFAULT_MAX_ITERATIONS = 8
MAX_ACTION_HISTORY = 12
LOOP_WARNING_REPEAT_THRESHOLD = 3
LOOP_WARNING_STAGNANT_THRESHOLD = 3
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_BROWSER_AGENT: Agent | None = None

KNOWN_SITES = {
    "baidu": "https://www.baidu.com",
    "\u767e\u5ea6": "https://www.baidu.com",
    "google": "https://www.google.com",
    "\u8c37\u6b4c": "https://www.google.com",
    "github": "https://github.com",
    "zhihu": "https://www.zhihu.com",
    "\u77e5\u4e4e": "https://www.zhihu.com",
    "bilibili": "https://www.bilibili.com",
    "\u54d4\u54e9\u54d4\u54e9": "https://www.bilibili.com",
}

OPEN_BROWSER_PATTERNS = (
    "open browser",
    "launch browser",
    "start browser",
    "\u6253\u5f00\u6d4f\u89c8\u5668",
    "\u542f\u52a8\u6d4f\u89c8\u5668",
)


class BrowserAction(BaseModel):
    event_type: str = Field(description="Atomic browser event type to execute")
    payload: dict[str, Any] = Field(default_factory=dict, description="Payload for the browser event")


class BrowserDecision(BaseModel):
    status: Literal["act", "done"] = Field(description="Whether to act or stop")
    reason: str = Field(description="Short reason for the choice")
    action: BrowserAction | None = Field(default=None, description="One atomic browser action when status='act'")


def _ensure_session_state(run_context: RunContext | None) -> dict[str, Any]:
    if run_context is None:
        return {}
    if run_context.session_state is None:
        run_context.session_state = {}
    return run_context.session_state


def _ensure_browser_state(run_context: RunContext | None) -> dict[str, Any]:
    session_state = _ensure_session_state(run_context)
    return session_state.setdefault(PERSISTENT_BROWSER_STATE_KEY, {})


def _ensure_current_round_state(run_context: RunContext | None) -> dict[str, Any]:
    session_state = _ensure_session_state(run_context)
    return session_state.setdefault(CURRENT_ROUND_RAW_STATE_KEY, {})


def clear_current_round_state(run_context: RunContext | None) -> None:
    session_state = _ensure_session_state(run_context)
    session_state.pop(CURRENT_ROUND_RAW_STATE_KEY, None)


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


def _response_is_error(snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(snapshot, dict):
        return True
    if snapshot.get("error"):
        return True
    if snapshot.get("accepted") is False:
        return True
    result = _extract_response_result(snapshot)
    return result.get("status") == "error"


def _response_error_detail(snapshot: dict[str, Any] | None) -> str:
    if not isinstance(snapshot, dict):
        return "Invalid browser response"
    if snapshot.get("error"):
        return _compact_text(snapshot.get("detail") or snapshot) or "Browser event failed"
    result = _extract_response_result(snapshot)
    return _compact_text(result.get("message") or snapshot.get("detail") or snapshot) or "Browser event failed"


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


def summarize_browser_snapshot(snapshot: dict[str, Any], goal: str | None = None) -> dict[str, Any]:
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
        "goal": _compact_text(goal, max_length=400),
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


def _parse_decision(raw: Any) -> BrowserDecision:
    if isinstance(raw, BrowserDecision):
        return raw
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(exclude_none=True)
    if isinstance(raw, dict):
        return BrowserDecision.model_validate(raw)
    raise ValueError(f"Unsupported browser decision payload: {type(raw).__name__}")


def _action_is_meaningful(action: BrowserAction | None) -> bool:
    if action is None or not action.event_type.strip():
        return False

    event_type = action.event_type.strip()
    payload = action.payload or {}

    if event_type in {"page.new_tab", "page.go_back", "page.go_forward", "page.reload", "page.screenshot"}:
        return True
    if event_type == "handle.execute":
        return isinstance(payload.get("name"), str) and bool(str(payload.get("name")).strip())
    if event_type in {"page.goto", "page.wait_for_url"}:
        return isinstance(payload.get("url"), str) and bool(str(payload.get("url")).strip())
    if event_type in {
        "page.click",
        "page.fill",
        "page.type",
        "page.hover",
        "page.scroll_into_view",
        "page.focus",
        "page.check",
        "page.uncheck",
        "page.get_text",
        "page.locator_count",
        "page.set_input_files",
    }:
        return isinstance(payload.get("selector"), str) and bool(str(payload.get("selector")).strip())
    if event_type == "page.click_text":
        return isinstance(payload.get("text"), str) and bool(str(payload.get("text")).strip())
    if event_type == "page.click_role":
        return isinstance(payload.get("role"), str) and bool(str(payload.get("role")).strip())
    if event_type == "page.press":
        return isinstance(payload.get("key"), str) and bool(str(payload.get("key")).strip())
    if event_type == "page.wait_for":
        selector = payload.get("selector")
        timeout_ms = payload.get("timeout_ms")
        return (isinstance(selector, str) and bool(selector.strip())) or timeout_ms is not None
    if event_type == "page.wait_for_load_state":
        return isinstance(payload.get("state"), str) and bool(str(payload.get("state")).strip())
    if event_type == "page.select_option":
        return isinstance(payload.get("selector"), str) and any(key in payload for key in ("value", "label", "index"))
    if event_type == "page.scroll":
        return "dx" in payload or "dy" in payload
    if event_type == "page.eval":
        return isinstance(payload.get("script"), str) and bool(str(payload.get("script")).strip())
    if event_type == "page.switch_tab":
        return payload.get("index") is not None
    if event_type == "page.close_tab":
        return True
    return bool(payload)


def _extract_url_from_goal(goal: str | None) -> str | None:
    if not goal:
        return None
    match = _URL_PATTERN.search(goal)
    return match.group(0) if match else None


def _extract_known_site_url(goal: str | None) -> str | None:
    if not goal:
        return None
    normalized_goal = goal.strip().lower()
    for site_name, site_url in KNOWN_SITES.items():
        if site_name.lower() in normalized_goal:
            return site_url
    return None


def _fallback_decision_for_goal(goal: str | None) -> BrowserDecision | None:
    normalized_goal = (goal or "").strip().lower()
    if not normalized_goal:
        return None

    direct_url = _extract_url_from_goal(goal)
    if direct_url:
        return BrowserDecision(
            status="act",
            reason="Goal contains a direct URL; navigate to it.",
            action=BrowserAction(event_type="page.goto", payload={"url": direct_url}),
        )

    known_site_url = _extract_known_site_url(goal)
    if known_site_url:
        return BrowserDecision(
            status="act",
            reason="Goal references a known site; navigate to it directly.",
            action=BrowserAction(event_type="page.goto", payload={"url": known_site_url}),
        )

    if any(pattern in normalized_goal for pattern in OPEN_BROWSER_PATTERNS):
        return BrowserDecision(
            status="act",
            reason="Goal is to open the browser; create a fresh tab.",
            action=BrowserAction(event_type="page.new_tab", payload={}),
        )
    return None


def _normalize_hostname(url: str | None) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urlparse(url.strip())
    host = (parsed.netloc or parsed.path).strip().lower()
    if not host:
        return None
    if "/" in host:
        host = host.split("/", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _page_matches_target_url(page_url: str | None, target_url: str | None) -> bool:
    if not page_url or not target_url:
        return False

    page_parsed = urlparse(page_url)
    target_parsed = urlparse(target_url)
    page_host = _normalize_hostname(page_url)
    target_host = _normalize_hostname(target_url)

    if not page_host or not target_host or page_host != target_host:
        return False

    target_path = (target_parsed.path or "").strip()
    if not target_path or target_path == "/":
        return True

    page_path = (page_parsed.path or "").strip()
    return page_path.startswith(target_path)


def _goal_target_url(goal: str | None) -> str | None:
    return _extract_url_from_goal(goal) or _extract_known_site_url(goal)


def _goal_completion_reason(goal: str | None, page: dict[str, Any] | None) -> str | None:
    if not isinstance(page, dict):
        return None

    page_url = _compact_text(page.get("url"))
    target_url = _goal_target_url(goal)
    if target_url and _page_matches_target_url(page_url, target_url):
        return "Goal already satisfied: the target page is already open."

    return None


def _canonical_action_signature(entry: dict[str, Any]) -> str | None:
    if not isinstance(entry, dict):
        return None
    event_type = _compact_text(entry.get("event_type"))
    if not event_type:
        return None
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    return json.dumps({"event_type": event_type, "payload": payload}, ensure_ascii=False, sort_keys=True)


def _build_loop_warning(action_history: list[dict[str, Any]]) -> str | None:
    if not action_history:
        return None

    repeated_actions = 1
    last_signature = _canonical_action_signature(action_history[-1])
    if last_signature is None:
        return None

    for entry in reversed(action_history[:-1]):
        if _canonical_action_signature(entry) != last_signature:
            break
        repeated_actions += 1

    stagnant_pages = 1
    last_page = action_history[-1].get("page") if isinstance(action_history[-1].get("page"), dict) else {}
    last_url = _compact_text(last_page.get("url"))
    for entry in reversed(action_history[:-1]):
        page = entry.get("page") if isinstance(entry.get("page"), dict) else {}
        if _compact_text(page.get("url")) != last_url:
            break
        stagnant_pages += 1

    if repeated_actions < LOOP_WARNING_REPEAT_THRESHOLD and stagnant_pages < LOOP_WARNING_STAGNANT_THRESHOLD:
        return None

    return (
        f"Recent loop warning: the last action pattern repeated {repeated_actions} time(s) "
        f"and the observed page URL stayed unchanged for {stagnant_pages} step(s). "
        "Avoid repeating the same ineffective action if the goal is already satisfied or no progress is visible."
    )


def normalize_browser_decision(decision: BrowserDecision, goal: str | None = None) -> BrowserDecision:
    if decision.status == "act" and _action_is_meaningful(decision.action):
        return decision

    fallback = _fallback_decision_for_goal(goal)

    if decision.status == "done":
        if _action_is_meaningful(decision.action):
            return BrowserDecision(
                status="act",
                reason=f"{decision.reason} (normalized contradictory done+action response)",
                action=decision.action,
            )
        return BrowserDecision(status="done", reason=decision.reason, action=None)

    if fallback is not None:
        return fallback

    return BrowserDecision(status="done", reason="Unable to determine a valid browser action.", action=None)


def _serialize_for_prompt(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(exclude_none=True)
    else:
        payload = value
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return str(payload)


def _build_persistent_state_summary(browser_state: dict[str, Any]) -> dict[str, Any]:
    action_history = browser_state.get("action_history")
    if not isinstance(action_history, list):
        action_history = []

    return {
        "goal": browser_state.get("goal"),
        "iteration": browser_state.get("iteration"),
        "last_decision": browser_state.get("last_decision"),
        "last_execution": browser_state.get("last_execution"),
        "last_verification": browser_state.get("last_verification"),
        "action_history": action_history[-5:],
        "loop_warning": _build_loop_warning(action_history),
    }


def _build_decision_prompt(goal: str | None, persistent_state: dict[str, Any], current_round_raw: dict[str, Any]) -> str:
    return (
        "Goal:\n"
        f"{goal or ''}\n\n"
        "Persistent browser state from previous rounds:\n"
        f"{_serialize_for_prompt(persistent_state)}\n\n"
        "Current round raw browser observation. This raw DOM and screenshot data is valid only for this round:\n"
        f"{_serialize_for_prompt(current_round_raw)}\n\n"
        "Return exactly one BrowserDecision."
    )


def observe_current_page(step_input: StepInput, run_context: RunContext | None = None) -> StepOutput:
    goal = step_input.get_input_as_string()
    clear_current_round_state(run_context)
    snapshot = submit_browser_event("page.eval", {"script": OBSERVE_PAGE_SCRIPT}, wait=True)

    if _response_is_error(snapshot):
        detail = _response_error_detail(snapshot)
        clear_current_round_state(run_context)
        return StepOutput(
            content={"status": "error", "reason": detail, "goal": goal},
            success=False,
            error=detail,
            stop=True,
        )

    summary = summarize_browser_snapshot(snapshot, goal=goal)
    browser_state = _ensure_browser_state(run_context)
    current_round_state = _ensure_current_round_state(run_context)

    browser_state["goal"] = goal
    browser_state["iteration"] = int(browser_state.get("iteration", 0)) + 1
    browser_state["last_observation_summary"] = summary

    current_round_state["raw_observation"] = _extract_current_round_raw(snapshot)
    current_round_state["observation_summary"] = summary

    return StepOutput(content=summary, success=True)


def _get_browser_agent() -> Agent:
    global _BROWSER_AGENT
    if _BROWSER_AGENT is None:
        _BROWSER_AGENT = create_browser_agent()
    return _BROWSER_AGENT


def decide_browser_action(step_input: StepInput, run_context: RunContext | None = None) -> StepOutput:
    goal = step_input.get_input_as_string()
    browser_state = _ensure_browser_state(run_context)
    current_round_state = _ensure_current_round_state(run_context)

    current_round_summary = current_round_state.get("observation_summary")
    completion_reason = _goal_completion_reason(
        goal,
        current_round_summary.get("page") if isinstance(current_round_summary, dict) else None,
    )
    if completion_reason is not None:
        decision = BrowserDecision(status="done", reason=completion_reason, action=None)
        browser_state["goal"] = goal
        browser_state["last_decision"] = decision.model_dump(exclude_none=True)
        return StepOutput(content=decision, success=True)

    deterministic_decision = _fallback_decision_for_goal(goal)

    if deterministic_decision is not None:
        browser_state["goal"] = goal
        browser_state["last_decision"] = deterministic_decision.model_dump(exclude_none=True)
        return StepOutput(content=deterministic_decision, success=True)

    persistent_state = _build_persistent_state_summary(browser_state)
    current_round_raw = current_round_state.get("raw_observation", {})

    browser_agent = _get_browser_agent()
    response = browser_agent.run(
        input=_build_decision_prompt(goal, persistent_state, current_round_raw),
        stream=False,
        stream_events=False,
        run_context=run_context,
    )
    decision = normalize_browser_decision(_parse_decision(response.content), goal=goal)
    browser_state["goal"] = goal
    browser_state["last_decision"] = decision.model_dump(exclude_none=True)
    return StepOutput(content=decision, success=True)


def execute_browser_action(step_input: StepInput, run_context: RunContext | None = None) -> StepOutput:
    goal = step_input.get_input_as_string()
    decision = normalize_browser_decision(_parse_decision(step_input.previous_step_content), goal=goal)
    browser_state = _ensure_browser_state(run_context)
    browser_state["goal"] = goal
    browser_state["last_decision"] = decision.model_dump(exclude_none=True)

    if decision.status == "done":
        clear_current_round_state(run_context)
        return StepOutput(
            content={"status": "done", "reason": decision.reason, "goal": goal},
            success=True,
            stop=True,
        )

    if decision.action is None:
        clear_current_round_state(run_context)
        return StepOutput(
            content={"status": "error", "reason": "Missing browser action", "goal": goal},
            success=False,
            error="Missing browser action",
            stop=True,
        )

    result = submit_browser_event(decision.action.event_type, decision.action.payload, wait=True)
    if _response_is_error(result):
        detail = _response_error_detail(result)
        error_content = {
            "status": "error",
            "reason": detail,
            "event_type": decision.action.event_type,
            "payload": decision.action.payload,
            "goal": goal,
        }
        browser_state["last_execution"] = error_content
        clear_current_round_state(run_context)
        return StepOutput(content=error_content, success=False, error=detail, stop=True)

    summary = summarize_browser_snapshot(result, goal=goal)
    execution_content = {
        "status": "acted",
        "reason": decision.reason,
        "event_type": decision.action.event_type,
        "payload": decision.action.payload,
        "page": summary["page"],
        "last_result": summary["last_result"],
        "top_candidates": summary["top_candidates"],
    }
    browser_state["last_execution"] = execution_content
    action_history = browser_state.setdefault("action_history", [])
    if isinstance(action_history, list):
        action_history.append(
            {
                "event_type": decision.action.event_type,
                "payload": decision.action.payload,
                "reason": decision.reason,
                "page": execution_content["page"],
            }
        )
        if len(action_history) > MAX_ACTION_HISTORY:
            del action_history[:-MAX_ACTION_HISTORY]

    return StepOutput(content=execution_content, success=True)


def verify_browser_progress(step_input: StepInput, run_context: RunContext | None = None) -> StepOutput:
    goal = step_input.get_input_as_string()
    previous_content = step_input.previous_step_content
    if isinstance(previous_content, BaseModel):
        previous_content = previous_content.model_dump(exclude_none=True)

    if not isinstance(previous_content, dict):
        clear_current_round_state(run_context)
        return StepOutput(content={"status": "unknown"}, success=True)

    verification = {
        "status": previous_content.get("status"),
        "reason": previous_content.get("reason"),
        "page": previous_content.get("page"),
    }

    completion_reason = _goal_completion_reason(
        goal,
        verification.get("page") if isinstance(verification.get("page"), dict) else None,
    )
    if completion_reason is not None:
        verification = {
            "status": "done",
            "reason": completion_reason,
            "page": verification.get("page"),
        }

    browser_state = _ensure_browser_state(run_context)
    browser_state["last_verification"] = verification
    clear_current_round_state(run_context)
    return StepOutput(
        content=verification,
        success=True,
        stop=bool(previous_content.get("stop")) or verification.get("status") == "done",
    )


def browser_loop_end_condition(iteration_results: list[StepOutput]) -> bool:
    return any(result.stop for result in iteration_results)


def create_browser_agent() -> Agent:
    return Agent(
        name="Browser Workflow Agent",
        model=get_ai_model(),
        instructions=[
            "You are a single browser automation agent controlled by a workflow loop.",
            "You will see persistent browser state from previous rounds and raw DOM/screenshot data for the current round only.",
            "Raw DOM and screenshot data are valid only for the current round and should not be assumed to persist.",
            "Choose exactly one next atomic browser action or declare the task complete.",
            "When status='done', action must be null. When action is present, status must be 'act'.",
            "Allowed events include page.goto, page.click, page.click_text, page.click_role, page.fill, page.type, page.press, page.wait_for, page.scroll, page.scroll_into_view, page.select_option, page.check, page.uncheck, page.focus, page.go_back, page.go_forward, page.reload.",
            "You may also use handle.execute for reusable browser handles.",
            "Useful handles: fill_form, click_then_wait, type_and_submit, login_form, dismiss_modal_then_click, wait_and_retry_click, plus atomic aliases such as goto, click, fill, type, press, wait_for.",
            "For requests like opening the browser, use page.new_tab. For direct URLs, use page.goto.",
            "Do not describe multiple steps. Return one BrowserDecision only.",
        ],
        output_schema=BrowserDecision,
        structured_outputs=True,
        markdown=False,
        add_history_to_context=False,
        store_history_messages=False,
        enable_agentic_memory=False,
        search_knowledge=False,
        update_knowledge=False,
        stream=False,
        debug_mode=True,
    )


def create_browser_workflow(workflow_id: str = "browser_use_agent") -> Workflow:
    return Workflow(
        id=workflow_id,
        name="browser use workflow",
        description="Single-agent browser workflow with current-round raw DOM isolation",
        db=create_base_db(workflow_id),
        steps=[
            Loop(
                name="Browser Control Loop",
                steps=[
                    Step(name="Observe", executor=observe_current_page),
                    Step(name="Decide", executor=decide_browser_action),
                    Step(name="Execute", executor=execute_browser_action),
                    Step(name="Verify", executor=verify_browser_progress),
                ],
                max_iterations=DEFAULT_MAX_ITERATIONS,
                end_condition=browser_loop_end_condition,
            )
        ],
        stream=False,
        stream_events=False,
        stream_executor_events=False,
        store_executor_outputs=False,
        add_workflow_history_to_steps=False,
        session_state={PERSISTENT_BROWSER_STATE_KEY: {"max_iterations": DEFAULT_MAX_ITERATIONS}},
        debug_mode=True,
    )
