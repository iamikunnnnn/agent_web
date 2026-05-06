from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from server.web_driver_monitor.events import BusEvent, EventResult


@dataclass(frozen=True)
class HandleStep:
    event_type: str
    payload: dict[str, Any]


def _single_step(event_type: str, payload: dict[str, Any]) -> list[HandleStep]:
    return [HandleStep(event_type=event_type, payload=payload)]


def _build_fill_form_steps(args: dict[str, Any]) -> list[HandleStep]:
    fields = args.get("fields")
    timeout_ms = args.get("timeout_ms")

    steps: list[HandleStep] = []
    if isinstance(fields, dict):
        items = list(fields.items())
    elif isinstance(fields, list):
        items = []
        for item in fields:
            if not isinstance(item, dict):
                raise ValueError("fill_form fields list items must be objects")
            selector = item.get("selector")
            text = item.get("text")
            items.append((selector, text))
    else:
        raise ValueError("fill_form requires fields as dict or list")

    for selector, text in items:
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("fill_form requires a non-empty selector for each field")
        payload: dict[str, Any] = {"selector": selector, "text": "" if text is None else str(text)}
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        steps.append(HandleStep(event_type="page.fill", payload=payload))

    if not steps:
        raise ValueError("fill_form requires at least one field")
    return steps


def _build_click_step(args: dict[str, Any]) -> HandleStep:
    click = args.get("click")
    timeout_ms = args.get("timeout_ms")

    if isinstance(click, dict):
        event_type = click.get("event_type")
        payload = click.get("payload")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("click action requires event_type")
        if not isinstance(payload, dict):
            raise ValueError("click action requires payload")
        return HandleStep(event_type=event_type, payload=payload)

    if isinstance(args.get("selector"), str) and args["selector"].strip():
        payload = {"selector": args["selector"]}
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        return HandleStep(event_type="page.click", payload=payload)

    if isinstance(args.get("text"), str) and args["text"].strip():
        payload = {"text": args["text"]}
        if "exact" in args:
            payload["exact"] = bool(args["exact"])
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        return HandleStep(event_type="page.click_text", payload=payload)

    if isinstance(args.get("role"), str) and args["role"].strip():
        payload = {"role": args["role"]}
        if "name" in args:
            payload["name"] = args["name"]
        if "exact" in args:
            payload["exact"] = bool(args["exact"])
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        return HandleStep(event_type="page.click_role", payload=payload)

    raise ValueError("click step requires selector, text, role, or explicit click action")


def _build_wait_step(args: dict[str, Any]) -> HandleStep:
    timeout_ms = args.get("timeout_ms")

    if isinstance(args.get("wait_for"), dict):
        payload = dict(args["wait_for"])
        if timeout_ms is not None and "timeout_ms" not in payload:
            payload["timeout_ms"] = timeout_ms
        return HandleStep(event_type="page.wait_for", payload=payload)

    if isinstance(args.get("wait_for_url"), str) and args["wait_for_url"].strip():
        payload = {"url": args["wait_for_url"]}
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        return HandleStep(event_type="page.wait_for_url", payload=payload)

    if isinstance(args.get("wait_for_load_state"), str) and args["wait_for_load_state"].strip():
        payload = {"state": args["wait_for_load_state"]}
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        return HandleStep(event_type="page.wait_for_load_state", payload=payload)

    raise ValueError("wait step requires wait_for, wait_for_url, or wait_for_load_state")


def _build_click_then_wait_steps(args: dict[str, Any]) -> list[HandleStep]:
    return [_build_click_step(args), _build_wait_step(args)]


def _build_type_and_submit_steps(args: dict[str, Any]) -> list[HandleStep]:
    selector = args.get("selector")
    text = args.get("text")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("type_and_submit requires selector")
    if not isinstance(text, str):
        raise ValueError("type_and_submit requires text")

    timeout_ms = args.get("timeout_ms")
    delay_ms = args.get("delay_ms")
    key = args.get("key", "Enter")

    type_payload: dict[str, Any] = {"selector": selector, "text": text}
    press_payload: dict[str, Any] = {"key": key, "selector": selector}
    if timeout_ms is not None:
        type_payload["timeout_ms"] = timeout_ms
        press_payload["timeout_ms"] = timeout_ms
    if delay_ms is not None:
        type_payload["delay_ms"] = delay_ms

    return [
        HandleStep(event_type="page.type", payload=type_payload),
        HandleStep(event_type="page.press", payload=press_payload),
    ]


def _build_login_form_steps(args: dict[str, Any]) -> list[HandleStep]:
    username_selector = args.get("username_selector") or args.get("email_selector") or args.get("user_selector")
    username = args.get("username") or args.get("email") or args.get("user")
    password_selector = args.get("password_selector")
    password = args.get("password")

    if not isinstance(username_selector, str) or not username_selector.strip():
        raise ValueError("login_form requires username_selector")
    if not isinstance(password_selector, str) or not password_selector.strip():
        raise ValueError("login_form requires password_selector")
    if username is None:
        raise ValueError("login_form requires username")
    if password is None:
        raise ValueError("login_form requires password")

    timeout_ms = args.get("timeout_ms")
    steps: list[HandleStep] = [
        HandleStep(event_type="page.fill", payload={"selector": username_selector, "text": str(username)}),
        HandleStep(event_type="page.fill", payload={"selector": password_selector, "text": str(password)}),
    ]

    if timeout_ms is not None:
        steps[0].payload["timeout_ms"] = timeout_ms
        steps[1].payload["timeout_ms"] = timeout_ms

    click_args: dict[str, Any] = {}
    if isinstance(args.get("submit_selector"), str) and args["submit_selector"].strip():
        click_args["selector"] = args["submit_selector"]
    elif isinstance(args.get("submit_text"), str) and args["submit_text"].strip():
        click_args["text"] = args["submit_text"]
        if "submit_exact" in args:
            click_args["exact"] = bool(args["submit_exact"])
    elif isinstance(args.get("submit_role"), str) and args["submit_role"].strip():
        click_args["role"] = args["submit_role"]
        if "submit_name" in args:
            click_args["name"] = args["submit_name"]
        if "submit_exact" in args:
            click_args["exact"] = bool(args["submit_exact"])
    else:
        click_args["selector"] = "button[type='submit']"

    if timeout_ms is not None:
        click_args["timeout_ms"] = timeout_ms
    steps.append(_build_click_step(click_args))

    wait_args: dict[str, Any] = {}
    if isinstance(args.get("wait_for"), dict):
        wait_args["wait_for"] = dict(args["wait_for"])
    elif isinstance(args.get("wait_for_url"), str) and args["wait_for_url"].strip():
        wait_args["wait_for_url"] = args["wait_for_url"]
    elif isinstance(args.get("wait_for_load_state"), str) and args["wait_for_load_state"].strip():
        wait_args["wait_for_load_state"] = args["wait_for_load_state"]

    if wait_args:
        if timeout_ms is not None:
            wait_args["timeout_ms"] = timeout_ms
        steps.append(_build_wait_step(wait_args))

    return steps


def _build_dismiss_modal_then_click_steps(args: dict[str, Any]) -> list[HandleStep]:
    timeout_ms = args.get("timeout_ms")
    dismiss_selector = args.get("dismiss_selector")
    target_selector = args.get("target_selector")

    if not isinstance(dismiss_selector, str) or not dismiss_selector.strip():
        raise ValueError("dismiss_modal_then_click requires dismiss_selector")
    if not isinstance(target_selector, str) or not target_selector.strip():
        raise ValueError("dismiss_modal_then_click requires target_selector")

    dismiss_payload: dict[str, Any] = {"selector": dismiss_selector}
    target_payload: dict[str, Any] = {"selector": target_selector}
    if timeout_ms is not None:
        dismiss_payload["timeout_ms"] = timeout_ms
        target_payload["timeout_ms"] = timeout_ms

    return [
        HandleStep(event_type="page.click", payload=dismiss_payload),
        HandleStep(event_type="page.click", payload=target_payload),
    ]


def _build_wait_and_retry_click_steps(args: dict[str, Any]) -> list[HandleStep]:
    steps: list[HandleStep] = []
    timeout_ms = args.get("timeout_ms")

    if isinstance(args.get("wait_for"), dict):
        before_args = {"wait_for": dict(args["wait_for"])}
        if timeout_ms is not None:
            before_args["timeout_ms"] = timeout_ms
        steps.append(_build_wait_step(before_args))

    click_args = {key: value for key, value in args.items() if key in {"selector", "text", "role", "name", "exact", "click"}}
    if timeout_ms is not None:
        click_args["timeout_ms"] = timeout_ms
    steps.append(_build_click_step(click_args))

    after_wait_args: dict[str, Any] = {}
    if isinstance(args.get("after_wait_for"), dict):
        after_wait_args["wait_for"] = dict(args["after_wait_for"])
    elif isinstance(args.get("after_wait_for_url"), str) and args["after_wait_for_url"].strip():
        after_wait_args["wait_for_url"] = args["after_wait_for_url"]
    elif isinstance(args.get("after_wait_for_load_state"), str) and args["after_wait_for_load_state"].strip():
        after_wait_args["wait_for_load_state"] = args["after_wait_for_load_state"]

    if after_wait_args:
        if timeout_ms is not None:
            after_wait_args["timeout_ms"] = timeout_ms
        steps.append(_build_wait_step(after_wait_args))

    return steps


def build_handle_steps(name: str, args: dict[str, Any] | None = None) -> list[HandleStep]:
    handle_name = (name or "").strip()
    if not handle_name:
        raise ValueError("handle name is required")

    payload = dict(args or {})
    atomic_aliases = {
        "goto": "page.goto",
        "click": "page.click",
        "click_text": "page.click_text",
        "click_role": "page.click_role",
        "fill": "page.fill",
        "type": "page.type",
        "press": "page.press",
        "hover": "page.hover",
        "scroll": "page.scroll",
        "scroll_into_view": "page.scroll_into_view",
        "wait_for": "page.wait_for",
        "wait_for_url": "page.wait_for_url",
        "wait_for_load_state": "page.wait_for_load_state",
        "select_option": "page.select_option",
        "check": "page.check",
        "uncheck": "page.uncheck",
        "focus": "page.focus",
        "go_back": "page.go_back",
        "go_forward": "page.go_forward",
        "reload": "page.reload",
        "new_tab": "page.new_tab",
        "switch_tab": "page.switch_tab",
        "close_tab": "page.close_tab",
        "eval": "page.eval",
        "screenshot": "page.screenshot",
        "locator_count": "page.locator_count",
        "get_text": "page.get_text",
    }
    if handle_name in atomic_aliases:
        return _single_step(atomic_aliases[handle_name], payload)

    if handle_name == "fill_form":
        return _build_fill_form_steps(payload)
    if handle_name == "click_then_wait":
        return _build_click_then_wait_steps(payload)
    if handle_name == "type_and_submit":
        return _build_type_and_submit_steps(payload)
    if handle_name == "login_form":
        return _build_login_form_steps(payload)
    if handle_name == "dismiss_modal_then_click":
        return _build_dismiss_modal_then_click_steps(payload)
    if handle_name == "wait_and_retry_click":
        return _build_wait_and_retry_click_steps(payload)

    raise ValueError(f"Unknown handle: {handle_name}")


def create_handle_execute_handler(event_handlers: dict[str, Any]):
    async def _handle_execute(event: BusEvent) -> EventResult:
        raw_name = event.payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return EventResult(event_id=event.id, status="error", message="payload.name is required")

        raw_args = event.payload.get("args", {})
        if raw_args is None:
            raw_args = {}
        if not isinstance(raw_args, dict):
            return EventResult(event_id=event.id, status="error", message="payload.args must be an object")

        try:
            steps = build_handle_steps(raw_name, raw_args)
        except ValueError as exc:
            return EventResult(event_id=event.id, status="error", message=str(exc))

        executed_steps: list[str] = []
        step_results: list[dict[str, Any]] = []
        last_data: dict[str, Any] = {}

        for step in steps:
            handler = event_handlers.get(step.event_type)
            if handler is None:
                return EventResult(
                    event_id=event.id,
                    status="error",
                    message=f"No handler registered for {step.event_type}",
                    data={"handle_name": raw_name, "failed_step": {"event_type": step.event_type, "payload": step.payload}},
                )

            child_result = await handler(BusEvent(type=step.event_type, payload=step.payload))
            executed_steps.append(step.event_type)
            step_results.append(
                {
                    "event_type": step.event_type,
                    "payload": step.payload,
                    "status": child_result.status,
                    "message": child_result.message,
                }
            )

            if child_result.data:
                last_data = dict(child_result.data)

            if child_result.status != "ok":
                return EventResult(
                    event_id=event.id,
                    status="error",
                    message=f"Handle '{raw_name}' failed at {step.event_type}: {child_result.message}",
                    data={
                        "handle_name": raw_name,
                        "executed_steps": executed_steps,
                        "failed_step": {"event_type": step.event_type, "payload": step.payload},
                        "step_results": step_results,
                    },
                )

        final_data = dict(last_data)
        final_data["handle_name"] = raw_name
        final_data["executed_steps"] = executed_steps
        final_data["step_results"] = step_results
        return EventResult(
            event_id=event.id,
            status="ok",
            message=f"Handle '{raw_name}' executed",
            data=final_data,
        )

    return _handle_execute
