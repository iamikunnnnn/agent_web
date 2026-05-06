from __future__ import annotations

import base64
import io
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from tools.web_driver_monitor_toolkit import submit_browser_event

computer_mcp_app = FastAPI(title="computer_mcp", version="0.1.0")


class ComputerActionRequest(BaseModel):
    action: str
    payload: dict = Field(default_factory=dict)


BROWSER_ENVIRONMENT = "browser"
DESKTOP_ENVIRONMENT = "desktop"
SUPPORTED_ENVIRONMENTS = {BROWSER_ENVIRONMENT, DESKTOP_ENVIRONMENT}
SUPPORTED_DESKTOP_BUTTONS = {"left", "right"}

ACTION_TO_EVENT = {
    "goto": "page.goto",
    "click": "page.click",
    "click_text": "page.click_text",
    "double_click": "page.click",
    "type": "page.fill",
    "fill": "page.fill",
    "press": "page.press",
    "scroll": "page.eval",
    "wait": "page.wait_for",
    "screenshot": "page.screenshot",
    "hover": "page.hover",
    "drag": "page.eval",
    "move": "page.eval",
    "select": "page.select_option",
}


@computer_mcp_app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "computer_mcp", "mode": "browser-first"}


def _bad_request(detail: str) -> None:
    raise HTTPException(status_code=400, detail=detail)


def _service_unavailable(detail: str) -> None:
    raise HTTPException(status_code=503, detail=detail)


def _get_pyautogui():
    try:
        import pyautogui
    except Exception as exc:  # noqa: BLE001
        _service_unavailable(f"desktop environment support requires pyautogui: {exc}")
    return pyautogui


def _normalize_environment(payload: dict[str, Any]) -> str:
    raw_environment = payload.pop("environment", BROWSER_ENVIRONMENT)
    if raw_environment in (None, ""):
        return BROWSER_ENVIRONMENT
    if not isinstance(raw_environment, str):
        _bad_request("payload.environment must be a string: 'browser' or 'desktop'")
    environment = raw_environment.strip().lower()
    if environment not in SUPPORTED_ENVIRONMENTS:
        _bad_request(f"unsupported environment: {raw_environment}. expected 'browser' or 'desktop'")
    return environment


def _require_number(payload: dict[str, Any], key: str, action: str) -> int | float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _bad_request(f"{action} action requires numeric '{key}'")
    return value


def _optional_number(payload: dict[str, Any], key: str, action: str) -> int | float | None:
    if key not in payload or payload.get(key) is None:
        return None
    return _require_number(payload, key, action)


def _require_button(payload: dict[str, Any], action: str) -> str:
    button = str(payload.get("button", "left")).strip().lower()
    if button not in SUPPORTED_DESKTOP_BUTTONS:
        _bad_request(f"{action} action supports button 'left' or 'right'")
    return button


def _require_xy(payload: dict[str, Any], action: str) -> tuple[int, int]:
    x = int(_require_number(payload, "x", action))
    y = int(_require_number(payload, "y", action))
    return x, y


def _desktop_success(action: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "accepted": True,
        "environment": DESKTOP_ENVIRONMENT,
        "action": action,
        "result": {
            "status": "ok",
            "message": message,
            "data": data or {},
        },
    }


def _run_browser_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_type = ACTION_TO_EVENT.get(action)
    if event_type is None:
        _bad_request(f"unsupported action: {action}")

    browser_payload = dict(payload)

    if action == "scroll":
        delta_y = browser_payload.pop("delta_y", 600)
        browser_payload = {"script": f"window.scrollBy(0, {int(delta_y)});", **browser_payload}

    if action == "double_click":
        x = browser_payload.get("x")
        y = browser_payload.get("y")
        if x is None or y is None:
            _bad_request("double_click action requires 'x' and 'y'")
        browser_payload = {
            "script": """
                ({ x, y }) => {
                    const target = document.elementFromPoint(x, y);
                    if (!target) {
                        throw new Error(`No element found at (${x}, ${y})`);
                    }
                    const options = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
                    target.dispatchEvent(new MouseEvent('mousemove', options));
                    target.dispatchEvent(new MouseEvent('mousedown', options));
                    target.dispatchEvent(new MouseEvent('mouseup', options));
                    target.dispatchEvent(new MouseEvent('click', options));
                    target.dispatchEvent(new MouseEvent('mousedown', options));
                    target.dispatchEvent(new MouseEvent('mouseup', options));
                    target.dispatchEvent(new MouseEvent('click', options));
                    target.dispatchEvent(new MouseEvent('dblclick', options));
                    return { x, y, tag: target.tagName, text: (target.textContent || '').trim().slice(0, 120) };
                }
            """,
            "x": x,
            "y": y,
        }

    if action == "move":
        x = browser_payload.get("x")
        y = browser_payload.get("y")
        if x is None or y is None:
            _bad_request("move action requires 'x' and 'y'")
        browser_payload = {
            "script": """
                ({ x, y }) => {
                    const target = document.elementFromPoint(x, y) || document.body;
                    const options = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
                    target.dispatchEvent(new PointerEvent('pointermove', options));
                    target.dispatchEvent(new MouseEvent('mousemove', options));
                    return {
                        x,
                        y,
                        moved: true,
                        semantics: 'page.mouse.move',
                        tag: target?.tagName || null,
                        text: ((target?.textContent) || '').trim().slice(0, 120),
                    };
                }
            """,
            "x": x,
            "y": y,
        }

    if action == "drag":
        start = browser_payload.get("start") or {}
        end = browser_payload.get("end") or {}
        start_x = start.get("x")
        start_y = start.get("y")
        end_x = end.get("x")
        end_y = end.get("y")
        if None in {start_x, start_y, end_x, end_y}:
            _bad_request("drag action requires start/end coordinates with x/y")
        browser_payload = {
            "script": """
                ({ startX, startY, endX, endY }) => {
                    const source = document.elementFromPoint(startX, startY);
                    const target = document.elementFromPoint(endX, endY);
                    if (!source) {
                        throw new Error(`No source element found at (${startX}, ${startY})`);
                    }
                    if (!target) {
                        throw new Error(`No target element found at (${endX}, ${endY})`);
                    }
                    const dataTransfer = new DataTransfer();
                    const fire = (el, type, x, y) => {
                        el.dispatchEvent(new DragEvent(type, {
                            bubbles: true,
                            cancelable: true,
                            clientX: x,
                            clientY: y,
                            dataTransfer,
                            view: window,
                        }));
                    };
                    source.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX: startX, clientY: startY, view: window }));
                    fire(source, 'dragstart', startX, startY);
                    fire(target, 'dragenter', endX, endY);
                    fire(target, 'dragover', endX, endY);
                    fire(target, 'drop', endX, endY);
                    fire(source, 'dragend', endX, endY);
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, clientX: endX, clientY: endY, view: window }));
                    return {
                        start: { x: startX, y: startY, tag: source.tagName },
                        end: { x: endX, y: endY, tag: target.tagName },
                    };
                }
            """,
            "startX": start_x,
            "startY": start_y,
            "endX": end_x,
            "endY": end_y,
        }

    if action == "select":
        selector = browser_payload.get("selector")
        values = browser_payload.get("values", [])
        if not selector:
            _bad_request("select action requires 'selector'")
        browser_payload = {"selector": selector, "values": values}

    response = submit_browser_event(event_type=event_type, payload=browser_payload, wait=True)
    if response.get("error"):
        _bad_request(str(response.get("detail")))
    return response


def _run_desktop_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action == "wait":
        seconds = _optional_number(payload, "seconds", action)
        if seconds is None:
            timeout_ms = _optional_number(payload, "timeout_ms", action)
            if timeout_ms is None:
                _bad_request("wait action requires 'seconds' or 'timeout_ms'")
            seconds = float(timeout_ms) / 1000.0
        if float(seconds) < 0:
            _bad_request("wait action requires non-negative 'seconds' or 'timeout_ms'")
        time.sleep(float(seconds))
        return _desktop_success(action, "desktop wait completed", {"seconds": float(seconds)})

    pyautogui = _get_pyautogui()

    if action == "screenshot":
        image_type = str(payload.get("type") or payload.get("format") or "png").strip().lower()
        if image_type not in {"png", "jpeg", "jpg"}:
            _bad_request("screenshot action supports type 'png' or 'jpeg'")
        normalized_type = "jpeg" if image_type in {"jpeg", "jpg"} else "png"
        image = pyautogui.screenshot()
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG" if normalized_type == "jpeg" else "PNG")
        return _desktop_success(
            action,
            "desktop screenshot captured",
            {
                "screenshot_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
                "screenshot_type": normalized_type,
                "screenshot_full_page": False,
                "width": getattr(image, "width", None),
                "height": getattr(image, "height", None),
            },
        )

    if action == "click":
        x, y = _require_xy(payload, action)
        button = _require_button(payload, action)
        pyautogui.click(x=x, y=y, button=button)
        return _desktop_success(action, "desktop click completed", {"x": x, "y": y, "button": button})

    if action == "double_click":
        x, y = _require_xy(payload, action)
        button = _require_button(payload, action)
        pyautogui.doubleClick(x=x, y=y, button=button)
        return _desktop_success(action, "desktop double click completed", {"x": x, "y": y, "button": button})

    if action == "scroll":
        x = _optional_number(payload, "x", action)
        y = _optional_number(payload, "y", action)
        if (x is None) ^ (y is None):
            _bad_request("scroll action requires both 'x' and 'y' when moving before scroll")
        clicks = int(_require_number(payload, "clicks", action))
        if x is not None and y is not None:
            pyautogui.moveTo(int(x), int(y))
        pyautogui.scroll(clicks)
        data: dict[str, Any] = {"clicks": clicks}
        if x is not None and y is not None:
            data["x"] = int(x)
            data["y"] = int(y)
        return _desktop_success(action, "desktop scroll completed", data)

    if action in {"type", "fill"}:
        text = payload.get("text")
        if not isinstance(text, str):
            _bad_request(f"{action} action requires string 'text'")
        interval = float(_optional_number(payload, "interval", action) or 0.0)
        pyautogui.write(text, interval=interval)
        return _desktop_success(action, "desktop text entry completed", {"text_length": len(text)})

    if action == "press":
        key = payload.get("key")
        keys = payload.get("keys")
        if isinstance(key, str) and key.strip():
            normalized_key = key.strip()
            pyautogui.press(normalized_key)
            return _desktop_success(action, "desktop key press completed", {"key": normalized_key})
        if isinstance(keys, list) and keys and all(isinstance(item, str) and item.strip() for item in keys):
            normalized_keys = [item.strip() for item in keys]
            pyautogui.hotkey(*normalized_keys)
            return _desktop_success(action, "desktop hotkey completed", {"keys": normalized_keys})
        _bad_request("press action requires 'key' or non-empty string list 'keys'")

    if action == "drag":
        start = payload.get("start")
        end = payload.get("end")
        if not isinstance(start, dict) or not isinstance(end, dict):
            _bad_request("drag action requires 'start' and 'end' objects with x/y")
        start_x = start.get("x")
        start_y = start.get("y")
        end_x = end.get("x")
        end_y = end.get("y")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (start_x, start_y, end_x, end_y)):
            _bad_request("drag action requires numeric start/end coordinates with x/y")
        duration = float(_optional_number(payload, "duration", action) or 0.0)
        button = _require_button(payload, action)
        pyautogui.moveTo(int(start_x), int(start_y))
        pyautogui.dragTo(int(end_x), int(end_y), duration=duration, button=button)
        return _desktop_success(
            action,
            "desktop drag completed",
            {
                "start": {"x": int(start_x), "y": int(start_y)},
                "end": {"x": int(end_x), "y": int(end_y)},
                "button": button,
            },
        )

    if action == "move":
        x, y = _require_xy(payload, action)
        duration = float(_optional_number(payload, "duration", action) or 0.0)
        pyautogui.moveTo(x, y, duration=duration)
        return _desktop_success(action, "desktop move completed", {"x": x, "y": y})

    _bad_request(
        f"unsupported desktop action: {action}. supported actions: screenshot, click, double_click, scroll, "
        "type, fill, press, drag, move, wait"
    )


@computer_mcp_app.post("/computer/action")
def run_action(req: ComputerActionRequest) -> dict:
    payload = dict(req.payload)
    environment = _normalize_environment(payload)
    if environment == DESKTOP_ENVIRONMENT:
        return _run_desktop_action(req.action, payload)
    return _run_browser_action(req.action, payload)


from fastmcp import FastMCP

mcp = FastMCP.from_fastapi(app=computer_mcp_app)

if __name__ == "__main__":
    import os
    import uvicorn

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8013"))
    uvicorn.run(computer_mcp_app, host=host, port=port)
