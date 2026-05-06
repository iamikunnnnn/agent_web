from __future__ import annotations

import asyncio
import base64
from typing import Any

from server.web_driver_monitor.config import settings
from server.web_driver_monitor.events import BusEvent, EventResult
from server.web_driver_monitor.playwright_runtime import PlaywrightRuntime


def _int(payload: dict[str, Any], key: str, default: int) -> int:
    raw = payload.get(key, default)
    try:
        return int(raw)
    except Exception:
        return default


async def _get_interactable_dom(page, *, limit: int) -> dict[str, Any]:
    """
    Return a filtered DOM snapshot containing only interactable elements.

    Output is intentionally compact and stable for LLM consumption:
    - a list of elements with basic attributes and a best-effort CSS selector
    - capped to `limit` to prevent huge responses
    """
    js = r"""
    (limit) => {
      const MAX_TEXT = 200;
      const MAX_ATTR = 200;

      const norm = (s) => (s || "").toString().replace(/\s+/g, " ").trim();

      const isVisible = (el) => {
        try {
          const style = window.getComputedStyle(el);
          if (!style) return false;
          if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") return false;
          if (parseFloat(style.opacity || "1") <= 0) return false;
          if (style.pointerEvents === "none") return false;
          const rect = el.getBoundingClientRect();
          if (!rect || rect.width <= 0 || rect.height <= 0) return false;
          if (el.getClientRects().length === 0) return false;
          return true;
        } catch {
          return false;
        }
      };

      const isDisabled = (el) => {
        const ariaDisabled = el.getAttribute && el.getAttribute("aria-disabled");
        if (ariaDisabled && ariaDisabled.toLowerCase() === "true") return true;
        // @ts-ignore
        if (typeof el.disabled === "boolean" && el.disabled) return true;
        return false;
      };

      const isInteractable = (el) => {
        if (!el || el.nodeType !== 1) return false;
        if (!isVisible(el)) return false;
        if (isDisabled(el)) return false;
        const tag = (el.tagName || "").toLowerCase();

        if (tag === "a") return !!el.getAttribute("href");
        if (tag === "button") return true;
        if (tag === "input" || tag === "textarea" || tag === "select") return true;
        if (tag === "summary") return true;

        const role = (el.getAttribute("role") || "").toLowerCase();
        if (role === "button" || role === "link" || role === "textbox" || role === "menuitem" || role === "tab") return true;

        const tabindex = el.getAttribute("tabindex");
        if (tabindex !== null && tabindex !== "-1") return true;

        if (el.hasAttribute("contenteditable") && el.getAttribute("contenteditable") !== "false") return true;
        if (el.hasAttribute("onclick")) return true;

        return false;
      };

      const cssEscape = (s) => {
        try {
          // @ts-ignore
          return CSS && CSS.escape ? CSS.escape(s) : s.replace(/([ #;?%&,.+*~\':"!^$[\]()=>|\/@])/g, "\\$1");
        } catch {
          return s;
        }
      };

      const cssPath = (el) => {
        if (!el || el.nodeType !== 1) return "";
        if (el.id) return `#${cssEscape(el.id)}`;
        const parts = [];
        let cur = el;
        for (let i = 0; i < 6 && cur && cur.nodeType === 1 && cur.tagName; i++) {
          let part = cur.tagName.toLowerCase();
          if (cur.classList && cur.classList.length) {
            // keep a few classes as hints
            const classes = Array.from(cur.classList).slice(0, 2).map(c => `.${cssEscape(c)}`).join("");
            part += classes;
          }
          const parent = cur.parentElement;
          if (parent) {
            const siblings = Array.from(parent.children).filter(ch => (ch.tagName || "").toLowerCase() === (cur.tagName || "").toLowerCase());
            if (siblings.length > 1) {
              const idx = siblings.indexOf(cur) + 1;
              part += `:nth-of-type(${idx})`;
            }
          }
          parts.unshift(part);
          if (!parent) break;
          cur = parent;
        }
        return parts.join(" > ");
      };

      const pickAttr = (el, name) => {
        const v = el.getAttribute ? el.getAttribute(name) : null;
        if (!v) return null;
        const s = norm(v);
        if (!s) return null;
        return s.slice(0, MAX_ATTR);
      };

      const els = Array.from(document.querySelectorAll("*")).filter(isInteractable);
      const out = [];
      for (const el of els.slice(0, limit)) {
        const tag = (el.tagName || "").toLowerCase();
        const text = norm(el.textContent || "").slice(0, MAX_TEXT);
        const item = {
          tag,
          text,
          selector: cssPath(el),
          role: pickAttr(el, "role"),
          id: el.id ? el.id.slice(0, MAX_ATTR) : null,
          name: pickAttr(el, "name"),
          type: pickAttr(el, "type"),
          placeholder: pickAttr(el, "placeholder"),
          title: pickAttr(el, "title"),
          aria_label: pickAttr(el, "aria-label"),
          href: tag === "a" ? pickAttr(el, "href") : null,
          tabindex: pickAttr(el, "tabindex"),
        };
        out.push(item);
      }
      return {
        url: location.href,
        count: els.length,
        returned: out.length,
        elements: out,
      };
    }
    """
    dom = await page.evaluate(js, limit)
    # Ensure dict for serialization even if playwright returns a mapping proxy type.
    return dict(dom) if isinstance(dom, dict) else {"dom": dom}


async def _collect_snapshot(page) -> dict[str, Any]:
    dom = await _get_interactable_dom(page, limit=settings.snapshot_dom_limit)
    image_type = (settings.snapshot_image_type or "jpeg").lower()
    full_page = bool(settings.snapshot_full_page)
    if image_type not in {"png", "jpeg"}:
        image_type = "jpeg"

    if image_type == "jpeg":
        raw = await page.screenshot(type="jpeg", full_page=full_page, quality=settings.snapshot_jpeg_quality)
    else:
        raw = await page.screenshot(type="png", full_page=full_page)

    return {
        "dom": dom,
        "screenshot_base64": base64.b64encode(raw).decode("ascii"),
        "screenshot_type": image_type,
        "screenshot_full_page": full_page,
    }


async def _run_action_with_snapshot(
    runtime: PlaywrightRuntime,
    action,
) -> tuple[dict[str, Any], dict[str, Any]]:
    async def _op(page):
        data = await action(page)
        snap = await _collect_snapshot(page)
        return data, snap

    return await runtime.run(_op)


def _ok(event: BusEvent, message: str, *, data: dict[str, Any], snapshot: dict[str, Any]) -> EventResult:
    merged = dict(data)
    merged.update(snapshot)
    return EventResult(event_id=event.id, status="ok", message=message, data=merged)

async def handle_goto(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    url = str(event.payload.get("url", "")).strip()
    if not url:
        return EventResult(event_id=event.id, status="error", message="payload.url is required")
    wait_until = str(event.payload.get("wait_until", "load"))
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        return page.url

    (final_url, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "navigated", data={"url": final_url}, snapshot=snapshot)


async def handle_click(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        locator = page.locator(selector).first
        await locator.click(timeout=timeout_ms)
        return page.url

    (url, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "clicked", data={"url": url, "selector": selector}, snapshot=snapshot)


async def handle_click_text(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    text = str(event.payload.get("text", "")).strip()
    if not text:
        return EventResult(event_id=event.id, status="error", message="payload.text is required")
    exact = bool(event.payload.get("exact", False))
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        locator = page.get_by_text(text, exact=exact).first
        await locator.click(timeout=timeout_ms)
        return page.url

    (url, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "clicked text", data={"url": url, "text": text, "exact": exact}, snapshot=snapshot)


async def handle_fill(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    text = str(event.payload.get("text", ""))
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        locator = page.locator(selector).first
        await locator.fill(text, timeout=timeout_ms)
        return page.url

    (url, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "filled", data={"url": url, "selector": selector}, snapshot=snapshot)


async def handle_press(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    key = str(event.payload.get("key", "")).strip()
    if not key:
        return EventResult(event_id=event.id, status="error", message="payload.key is required (e.g. Enter, Control+L)")
    selector = str(event.payload.get("selector", "")).strip()
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        if selector:
            await page.locator(selector).first.press(key, timeout=timeout_ms)
        else:
            await page.keyboard.press(key)
        return page.url

    (url, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "pressed", data={"url": url, "key": key, "selector": selector or None}, snapshot=snapshot)


async def handle_wait_for(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)
    state = str(event.payload.get("state", "visible"))

    if not selector:
        # Allow a simple sleep to help sequencing when needed.
        await asyncio.sleep(timeout_ms / 1000)
        async def _action(_page):
            return {"timeout_ms": timeout_ms}

        (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
        return _ok(event, "slept", data=data, snapshot=snapshot)

    async def _action(page):
        await page.wait_for_selector(selector, state=state, timeout=timeout_ms)
        return page.url

    (url, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "waited", data={"url": url, "selector": selector, "state": state}, snapshot=snapshot)


async def handle_screenshot(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    full_page = bool(event.payload.get("full_page", True))
    type_ = str(event.payload.get("type", "png"))

    async def _action(page):
        raw = await page.screenshot(type=type_, full_page=full_page)
        b64 = base64.b64encode(raw).decode("ascii")
        return {"url": page.url, "type": type_, "full_page": full_page, "requested_screenshot_base64": b64}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "screenshot", data=data, snapshot=snapshot)


async def handle_eval(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    script = event.payload.get("script")
    if not isinstance(script, str) or not script.strip():
        return EventResult(event_id=event.id, status="error", message="payload.script (string) is required")

    async def _action(page):
        result = await page.evaluate(script)
        return {"url": page.url, "result": result}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "evaluated", data=data, snapshot=snapshot)


async def handle_hover(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.locator(selector).first.hover(timeout=timeout_ms)
        return {"url": page.url, "selector": selector}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "hovered", data=data, snapshot=snapshot)


async def handle_scroll(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    dy = _int(event.payload, "dy", 800)
    dx = _int(event.payload, "dx", 0)

    async def _action(page):
        try:
            await page.mouse.wheel(dx, dy)
        except Exception:
            await page.evaluate("(dx,dy) => window.scrollBy(dx, dy)", dx, dy)
        return {"url": page.url, "dx": dx, "dy": dy}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "scrolled", data=data, snapshot=snapshot)


async def handle_scroll_into_view(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.locator(selector).first.scroll_into_view_if_needed(timeout=timeout_ms)
        return {"url": page.url, "selector": selector}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "scrolled into view", data=data, snapshot=snapshot)


async def handle_select_option(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)
    value = event.payload.get("value")
    label = event.payload.get("label")
    index = event.payload.get("index")
    option: Any
    if value is not None:
        option = str(value)
    elif label is not None:
        option = {"label": str(label)}
    elif index is not None:
        option = {"index": int(index)}
    else:
        return EventResult(event_id=event.id, status="error", message="payload.value|label|index is required")

    async def _action(page):
        await page.locator(selector).first.select_option(option, timeout=timeout_ms)
        return {"url": page.url, "selector": selector, "option": option}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "selected option", data=data, snapshot=snapshot)


async def handle_check(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.locator(selector).first.check(timeout=timeout_ms)
        return {"url": page.url, "selector": selector}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "checked", data=data, snapshot=snapshot)


async def handle_uncheck(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.locator(selector).first.uncheck(timeout=timeout_ms)
        return {"url": page.url, "selector": selector}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "unchecked", data=data, snapshot=snapshot)


async def handle_set_input_files(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    files = event.payload.get("files")
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    if not files:
        return EventResult(event_id=event.id, status="error", message="payload.files is required (string or list)")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)
    if isinstance(files, str):
        file_list = [files]
    elif isinstance(files, list):
        file_list = [str(x) for x in files]
    else:
        return EventResult(event_id=event.id, status="error", message="payload.files must be string or list")

    async def _action(page):
        await page.locator(selector).first.set_input_files(file_list, timeout=timeout_ms)
        return {"url": page.url, "selector": selector, "files": file_list}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "set input files", data=data, snapshot=snapshot)


async def handle_focus(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.locator(selector).first.focus(timeout=timeout_ms)
        return {"url": page.url, "selector": selector}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "focused", data=data, snapshot=snapshot)


async def handle_wait_for_url(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    url_pattern = event.payload.get("url")
    if not isinstance(url_pattern, str) or not url_pattern.strip():
        return EventResult(event_id=event.id, status="error", message="payload.url (string pattern) is required")
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.wait_for_url(url_pattern, timeout=timeout_ms)
        return {"url": page.url, "url_pattern": url_pattern}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "waited for url", data=data, snapshot=snapshot)


async def handle_wait_for_load_state(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    state = str(event.payload.get("state", "load"))
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.wait_for_load_state(state, timeout=timeout_ms)
        return {"url": page.url, "state": state}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "waited for load state", data=data, snapshot=snapshot)


async def handle_go_back(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.go_back(timeout=timeout_ms)
        return {"url": page.url}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "went back", data=data, snapshot=snapshot)


async def handle_go_forward(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.go_forward(timeout=timeout_ms)
        return {"url": page.url}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "went forward", data=data, snapshot=snapshot)


async def handle_reload(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.reload(timeout=timeout_ms)
        return {"url": page.url}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "reloaded", data=data, snapshot=snapshot)


async def handle_click_role(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    role = event.payload.get("role")
    name = event.payload.get("name")
    if not isinstance(role, str) or not role.strip():
        return EventResult(event_id=event.id, status="error", message="payload.role is required")
    if name is not None and not isinstance(name, str):
        return EventResult(event_id=event.id, status="error", message="payload.name must be string when provided")
    exact = bool(event.payload.get("exact", False))
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        locator = page.get_by_role(role, name=name, exact=exact).first if name is not None else page.get_by_role(role).first
        await locator.click(timeout=timeout_ms)
        return {"url": page.url, "role": role, "name": name, "exact": exact}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "clicked role", data=data, snapshot=snapshot)


async def handle_type(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    text = event.payload.get("text")
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    if not isinstance(text, str):
        return EventResult(event_id=event.id, status="error", message="payload.text (string) is required")
    delay_ms = _int(event.payload, "delay_ms", 0)
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        await page.locator(selector).first.type(text, delay=delay_ms, timeout=timeout_ms)
        return {"url": page.url, "selector": selector, "delay_ms": delay_ms}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "typed", data=data, snapshot=snapshot)


async def handle_locator_count(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")

    async def _action(page):
        count = await page.locator(selector).count()
        return {"url": page.url, "selector": selector, "count": count}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "locator count", data=data, snapshot=snapshot)


async def handle_get_text(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    selector = str(event.payload.get("selector", "")).strip()
    if not selector:
        return EventResult(event_id=event.id, status="error", message="payload.selector is required")
    mode = str(event.payload.get("mode", "inner_text"))  # inner_text|text_content|input_value
    timeout_ms = _int(event.payload, "timeout_ms", settings.default_timeout_ms)

    async def _action(page):
        loc = page.locator(selector).first
        if mode == "input_value":
            val = await loc.input_value(timeout=timeout_ms)
        elif mode == "text_content":
            val = await loc.text_content(timeout=timeout_ms)
        else:
            val = await loc.inner_text(timeout=timeout_ms)
        return {"url": page.url, "selector": selector, "mode": mode, "text": val}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "got text", data=data, snapshot=snapshot)


async def handle_new_tab(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    url = event.payload.get("url")
    if url is not None and not isinstance(url, str):
        return EventResult(event_id=event.id, status="error", message="payload.url must be string when provided")

    async def _action(_page):
        info = await runtime.new_tab(url=url)
        return {"tab": info, "tabs": await runtime.tabs()}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "new tab", data=data, snapshot=snapshot)


async def handle_switch_tab(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    index = event.payload.get("index")
    if index is None:
        return EventResult(event_id=event.id, status="error", message="payload.index is required")
    try:
        idx = int(index)
    except Exception:
        return EventResult(event_id=event.id, status="error", message="payload.index must be int")

    async def _action(_page):
        info = await runtime.switch_tab(idx)
        return {"tab": info, "tabs": await runtime.tabs()}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "switched tab", data=data, snapshot=snapshot)


async def handle_close_tab(event: BusEvent, runtime: PlaywrightRuntime) -> EventResult:
    index = event.payload.get("index")
    idx: int | None
    if index is None:
        idx = None
    else:
        try:
            idx = int(index)
        except Exception:
            return EventResult(event_id=event.id, status="error", message="payload.index must be int when provided")

    async def _action(_page):
        info = await runtime.close_tab(idx)
        return {"tab": info, "tabs": await runtime.tabs()}

    (data, snapshot) = await _run_action_with_snapshot(runtime, _action)
    return _ok(event, "closed tab", data=data, snapshot=snapshot)
