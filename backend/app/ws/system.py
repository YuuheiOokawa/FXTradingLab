"""WS /ws/system — pushes system_events/notifications as they occur. Uses a Redis
pub/sub channel that the API process publishes to whenever a notification or
system event is created (docs/07_REALTIME_DATA_DESIGN.md)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.redis_client import get_redis
from app.ws.auth import check_ws_auth

router = APIRouter()

SYSTEM_CHANNEL = "system:events"


@router.websocket("/ws/system")
async def ws_system(websocket: WebSocket) -> None:
    if not await check_ws_auth(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(SYSTEM_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            await websocket.send_text(data if isinstance(data, str) else data.decode())
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.close()
