# web_driver_monitor

Minimal standalone service that owns a long-lived Playwright browser page and executes **atomic** DOM operations via an in-memory event bus.

## Install

1) Install python deps:
- `pip install -r requirements.txt`
- `playwright install` (installs browser binaries)

## Run

Default: `http://localhost:8010`

- `python -m server.web_driver_monitor.main`

Env:
- `WDM_HOST` (default `0.0.0.0`)
- `WDM_PORT` (default `8010`)
- `WDM_BROWSER` (default `chromium`)
- `WDM_HEADLESS` (default `true`)
- `WDM_BROWSER_CHANNEL` (optional, for example `chrome` or `msedge`)
- `WDM_USER_DATA_DIR` (default dedicated automation profile directory under `db/user_data/web_driver_monitor_profile`)
- `WDM_BROWSER_PROFILE_DIR` (optional profile directory name inside the user data dir, for example `Default`)
- `WDM_STORAGE_STATE_PATH` (optional Playwright storage state JSON to seed cookies/localStorage)
- `WDM_URL` (agent tool client base URL; default `http://localhost:8010`)

Notes:
- This service loads the repo root `.env` (via `python-dotenv`) so you can put `WDM_HEADLESS=false` there, but you still need to restart the service process after changes.
- The browser runtime now always uses a dedicated persistent automation profile so it does not contend with your daily browser profile lock.
- If `WDM_STORAGE_STATE_PATH` is set, the runtime imports cookies and localStorage from that Playwright storage state JSON into the automation profile on startup.
- This is intended for reusing login state, not attaching to a currently open manual browser window.

Recommended `.env`:
```env
WDM_BROWSER=chromium
WDM_HEADLESS=false
WDM_BROWSER_CHANNEL=msedge
WDM_USER_DATA_DIR=C:\Users\你的用户名\AppData\Local\my_agents\web_driver_monitor_profile
WDM_STORAGE_STATE_PATH=C:\path\to\storage_state.json
```

## API

- `GET /health`
- `POST /v1/events:submit` body: `{ "type": "...", "payload": {...}, "wait": true }`
- `GET /v1/events/{event_id}`
- `GET /v1/page`

Example (goto):
```bash
curl -s -X POST http://localhost:8010/v1/events:submit ^
  -H "content-type: application/json" ^
  -d "{\"type\":\"page.goto\",\"payload\":{\"url\":\"https://example.com\"},\"wait\":true}"
```

## DOM snapshot in responses

Each successful event result includes:
- `result.data.dom`: filtered DOM snapshot with only interactable elements (links/buttons/inputs/etc.), capped for size
- `result.data.screenshot_base64`: screenshot taken immediately after the event, aligned with the DOM snapshot

Supported event types (watchdogs):
- `handle.execute` - execute a named browser handle composed from one or more atomic page events
- `page.goto`
- `page.click`
- `page.click_text`
- `page.click_role`
- `page.fill`
- `page.type`
- `page.press`
- `page.hover`
- `page.scroll`
- `page.scroll_into_view`
- `page.wait_for`
- `page.wait_for_url`
- `page.wait_for_load_state`
- `page.go_back`
- `page.go_forward`
- `page.reload`
- `page.focus`
- `page.select_option`
- `page.check`
- `page.uncheck`
- `page.set_input_files`
- `page.screenshot`
- `page.eval`
- `page.locator_count`
- `page.get_text`
- `page.new_tab`
- `page.switch_tab`
- `page.close_tab`

Built-in handles:
- `goto` -> `page.goto`
- `click` -> `page.click`
- `click_text` -> `page.click_text`
- `click_role` -> `page.click_role`
- `fill` -> `page.fill`
- `type` -> `page.type`
- `press` -> `page.press`
- `wait_for` -> `page.wait_for`
- `wait_for_url` -> `page.wait_for_url`
- `wait_for_load_state` -> `page.wait_for_load_state`
- `fill_form` -> expands a field map into multiple `page.fill` steps
- `click_then_wait` -> click first, then wait for selector/url/load-state
- `type_and_submit` -> type into a field, then press a submit key (default `Enter`)
- `login_form` -> fill username/password, submit the form, optionally wait for selector/url/load-state
- `dismiss_modal_then_click` -> close an overlay or modal first, then click the target element
- `wait_and_retry_click` -> optionally wait for a target, click it, then optionally wait for the post-click condition

Snapshot env:
- `WDM_SNAPSHOT_DOM_LIMIT` (default `200`)
- `WDM_SNAPSHOT_FULL_PAGE` (default `false`)
- `WDM_SNAPSHOT_IMAGE_TYPE` (default `jpeg`)
- `WDM_SNAPSHOT_JPEG_QUALITY` (default `60`)
