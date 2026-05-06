from __future__ import annotations

from server.web_driver_monitor.bus import EventBus
from server.web_driver_monitor.playwright_runtime import PlaywrightRuntime
from server.web_driver_monitor.watchdogs.handles import create_handle_execute_handler
from server.web_driver_monitor.watchdogs.page_actions import (
    handle_check,
    handle_click,
    handle_click_role,
    handle_click_text,
    handle_close_tab,
    handle_eval,
    handle_fill,
    handle_focus,
    handle_get_text,
    handle_go_back,
    handle_go_forward,
    handle_goto,
    handle_hover,
    handle_locator_count,
    handle_new_tab,
    handle_press,
    handle_reload,
    handle_screenshot,
    handle_scroll,
    handle_scroll_into_view,
    handle_select_option,
    handle_set_input_files,
    handle_switch_tab,
    handle_type,
    handle_uncheck,
    handle_wait_for,
    handle_wait_for_load_state,
    handle_wait_for_url,
)


def create_default_event_handlers(runtime: PlaywrightRuntime):
    page_handlers = {
        "page.goto": lambda e: handle_goto(e, runtime),
        "page.click": lambda e: handle_click(e, runtime),
        "page.click_text": lambda e: handle_click_text(e, runtime),
        "page.click_role": lambda e: handle_click_role(e, runtime),
        "page.fill": lambda e: handle_fill(e, runtime),
        "page.type": lambda e: handle_type(e, runtime),
        "page.press": lambda e: handle_press(e, runtime),
        "page.hover": lambda e: handle_hover(e, runtime),
        "page.scroll": lambda e: handle_scroll(e, runtime),
        "page.scroll_into_view": lambda e: handle_scroll_into_view(e, runtime),
        "page.wait_for": lambda e: handle_wait_for(e, runtime),
        "page.wait_for_url": lambda e: handle_wait_for_url(e, runtime),
        "page.wait_for_load_state": lambda e: handle_wait_for_load_state(e, runtime),
        "page.go_back": lambda e: handle_go_back(e, runtime),
        "page.go_forward": lambda e: handle_go_forward(e, runtime),
        "page.reload": lambda e: handle_reload(e, runtime),
        "page.focus": lambda e: handle_focus(e, runtime),
        "page.select_option": lambda e: handle_select_option(e, runtime),
        "page.check": lambda e: handle_check(e, runtime),
        "page.uncheck": lambda e: handle_uncheck(e, runtime),
        "page.set_input_files": lambda e: handle_set_input_files(e, runtime),
        "page.screenshot": lambda e: handle_screenshot(e, runtime),
        "page.eval": lambda e: handle_eval(e, runtime),
        "page.locator_count": lambda e: handle_locator_count(e, runtime),
        "page.get_text": lambda e: handle_get_text(e, runtime),
        "page.new_tab": lambda e: handle_new_tab(e, runtime),
        "page.switch_tab": lambda e: handle_switch_tab(e, runtime),
        "page.close_tab": lambda e: handle_close_tab(e, runtime),
    }
    page_handlers["handle.execute"] = create_handle_execute_handler(page_handlers)
    return page_handlers


def register_default_watchdogs(bus: EventBus, runtime: PlaywrightRuntime) -> None:
    for event_type, handler in create_default_event_handlers(runtime).items():
        bus.register(event_type, handler)
