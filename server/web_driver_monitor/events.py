from __future__ import annotations

import time
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BusEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: str = Field(..., description="Event type, e.g. page.goto, page.click, page.fill")
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=lambda: time.time())


class SubmitEventRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    wait: bool = True


class SubmitEventResponse(BaseModel):
    event_id: UUID
    accepted: bool = True
    result: EventResult | None = None


class EventResult(BaseModel):
    event_id: UUID
    status: Literal["ok", "error"]
    message: str = ""
    data: dict[str, Any] | None = None
