from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from server.web_driver_monitor.events import BusEvent, EventResult

EventHandler = Callable[[BusEvent], Awaitable[EventResult]]


class EventBus:
    """
    In-memory, single-process event bus.

    - Serializes event handling via an asyncio.Queue.
    - Dispatches to a handler based on event.type.
    - Provides a Future per submitted event for "wait for completion" semantics.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[BusEvent] = asyncio.Queue()
        self._handlers: dict[str, EventHandler] = {}
        self._runner_task: asyncio.Task[None] | None = None
        self._futures: dict[UUID, asyncio.Future[EventResult]] = {}

        # Best-effort recent results, for debugging/status queries.
        self._recent_results: dict[UUID, EventResult] = {}
        self._recent_max: int = 200
        self._lock = asyncio.Lock()

    def register(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type] = handler

    async def start(self) -> None:
        if self._runner_task and not self._runner_task.done():
            return
        self._runner_task = asyncio.create_task(self._runner(), name="wdm-event-bus-runner")

    async def stop(self) -> None:
        if not self._runner_task:
            return
        self._runner_task.cancel()
        try:
            await self._runner_task
        except asyncio.CancelledError:
            pass
        self._runner_task = None

    async def submit(self, event: BusEvent) -> asyncio.Future[EventResult]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[EventResult] = loop.create_future()
        async with self._lock:
            self._futures[event.id] = fut
        await self._queue.put(event)
        return fut

    async def get_result(self, event_id: UUID) -> EventResult | None:
        return self._recent_results.get(event_id)

    async def _set_recent(self, result: EventResult) -> None:
        self._recent_results[result.event_id] = result
        if len(self._recent_results) > self._recent_max:
            # Drop oldest by insertion order (Python 3.7+ dict preserves order).
            oldest = next(iter(self._recent_results.keys()))
            self._recent_results.pop(oldest, None)

    async def _runner(self) -> None:
        while True:
            event = await self._queue.get()
            handler = self._handlers.get(event.type)
            if handler is None:
                result = EventResult(
                    event_id=event.id,
                    status="error",
                    message=f"Unknown event type: {event.type}",
                    data={"known_types": sorted(self._handlers.keys())},
                )
            else:
                try:
                    result = await handler(event)
                except Exception as exc:  # noqa: BLE001
                    result = EventResult(
                        event_id=event.id,
                        status="error",
                        message=f"{type(exc).__name__}: {exc}",
                    )

            await self._set_recent(result)

            fut: asyncio.Future[EventResult] | None
            async with self._lock:
                fut = self._futures.pop(event.id, None)
            if fut and not fut.done():
                fut.set_result(result)
