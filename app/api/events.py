from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..events import Broker

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def stream_events(request: Request, since: int | None = None) -> EventSourceResponse:
    broker: Broker = request.app.state.broker

    async def generator():
        async for event in broker.subscribe(since):
            if await request.is_disconnected():
                break
            yield {"id": str(event["id"]), "data": json.dumps(event)}

    return EventSourceResponse(generator(), ping=15)
