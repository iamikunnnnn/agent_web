# Web Driver Monitor: Event Bus + Watchdogs (Minimal)

## Goal

Run a separate service (`server/web_driver_monitor`) that owns a single long-lived browser session and executes **atomic** Playwright DOM operations in response to **events**. Agents trigger operations by calling a tool that submits events to this service. This enables multi-turn browser workflows (e.g., “open site” → later “click first video” → later “like”) without rebuilding state each turn.

Non-goals for this iteration:
- Complex reasoning/automation inside the service
- Multi-browser orchestration, retries, or long-running workflows
- Screenshot+vision / OCR or non-DOM interaction

## Architecture

**Service process**
- FastAPI app exposes a small HTTP API to submit events and query status.
- An in-memory `EventBus` serializes events through an `asyncio.Queue`.
- A `PlaywrightRuntime` manages a single `browser/context/page` and persists it for the service lifetime.

**Watchdogs**
- A watchdog is a handler for one event type. Each handler performs exactly one Playwright action (goto, click, fill, wait, etc.).
- The bus dispatches the event to a watchdog based on `event.type`. Unknown types return an error.

## Event Model

Each event:
- `id`: uuid
- `type`: string (e.g., `page.goto`, `page.click`, `page.click_text`, `page.fill`)
- `payload`: JSON object (type-specific)
- `created_at`: unix timestamp

Each result:
- `status`: `ok`/`error`
- `message`: human readable
- `data`: optional JSON (e.g., `page_url`, `screenshot_base64`)

## Data Flow

1) Agent tool calls `POST /v1/events:submit` with `{type,payload}`.
2) Service enqueues event and (optionally) waits for completion, returning the result.
3) The watchdog executes the atomic Playwright operation on the persistent `page`.

## Error Handling

- Playwright import/start failures surface as 500 with actionable message.
- Each event is wrapped in a try/except; failures return structured error result.
- Timeouts are explicit in payload where applicable.

## Testing Strategy (Minimal)

- Unit-ish: import/py_compile on new modules.
- Manual: run service, submit `page.goto` then `page.click_text` and observe browser behavior.

