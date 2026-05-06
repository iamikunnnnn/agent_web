from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder

from server.web_driver_monitor.bus import EventBus
from server.web_driver_monitor.config import settings
from server.web_driver_monitor.events import (
    BusEvent,
    EventResult,
    SubmitEventRequest,
    SubmitEventResponse,
)
from server.web_driver_monitor.playwright_runtime import PlaywrightRuntime
from server.web_driver_monitor.watchdogs import register_default_watchdogs

bus = EventBus()
runtime = PlaywrightRuntime(
    browser_type=settings.browser_type,
    headless=settings.headless,
    user_data_dir=settings.user_data_dir,
    browser_channel=settings.browser_channel,
    browser_profile_directory=settings.browser_profile_directory,
    storage_state_path=settings.storage_state_path,
)
register_default_watchdogs(bus, runtime)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bus.start()
    # Start Playwright lazily on first event; but warm-start is cheap to enable via env.
    if settings.headless is False:
        # In non-headless mode, it's common to want the window immediately.
        try:
            await runtime.start()
        except Exception:
            # Keep server alive; the first event will return an actionable error.
            pass
    yield
    await runtime.stop()
    await bus.stop()


app = FastAPI(title="web_driver_monitor", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "web_driver_monitor",
        "playwright_started": runtime.started,
        "browser_type": settings.browser_type,
        "headless": settings.headless,
        "browser_channel": settings.browser_channel,
        "user_data_dir": settings.user_data_dir,
        "browser_profile_directory": settings.browser_profile_directory,
        "storage_state_path": settings.storage_state_path,
    }


@app.get("/v1/page")
async def get_page():
    return {"url": await runtime.page_url()}


@app.post("/v1/events:submit", response_model=SubmitEventResponse)
async def submit_event(req: SubmitEventRequest):
    event = BusEvent(type=req.type, payload=req.payload)
    fut = await bus.submit(event)

    if not req.wait:
        return SubmitEventResponse(event_id=event.id, accepted=True, result=None)

    timeout_s = settings.submit_wait_timeout_ms / 1000
    try:
        _result: EventResult = await asyncio.wait_for(fut, timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"Timed out waiting for event completion after {timeout_s}s") from exc

    if _result.status != "ok":
        raise HTTPException(status_code=400, detail=jsonable_encoder(_result.model_dump()))

    return SubmitEventResponse(event_id=event.id, accepted=True, result=_result)


@app.get("/v1/events/{event_id}", response_model=EventResult)
async def get_event_result(event_id: UUID):
    result = await bus.get_result(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail="event not found (not completed or evicted from memory)")
    return result
