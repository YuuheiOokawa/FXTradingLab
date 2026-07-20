"""WS /ws/prices — forwards Redis-published ticks/candle updates to the browser
(docs/07_REALTIME_DATA_DESIGN.md). The frontend never polls REST for live price
data; this is the only channel for that.
"""
from __future__ import annotations

import asyncio
import logging

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)
router = APIRouter()


async def _subscribe(pubsub, instruments: set[str]) -> None:
    patterns = []
    for instrument in instruments:
        patterns.append(f"ticks:{instrument}")
        patterns.append(f"candles:{instrument}:*")
    if patterns:
        await pubsub.psubscribe(*patterns)


@router.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket) -> None:
    await websocket.accept()
    redis = get_redis()
    pubsub = redis.pubsub()

    instruments: set[str] = set()
    initial = websocket.query_params.get("instruments")
    if initial:
        instruments = {s.strip() for s in initial.split(",") if s.strip()}
        await _subscribe(pubsub, instruments)

    async def reader() -> None:
        """Forward Redis pub/sub messages to the browser."""
        async for message in pubsub.listen():
            if message["type"] not in ("pmessage", "message"):
                continue
            try:
                await websocket.send_text(message["data"] if isinstance(message["data"], str) else message["data"].decode())
            except Exception:
                return

    async def writer() -> None:
        """Handle client control frames: {"type": "subscribe"/"unsubscribe", "instruments": [...]}."""
        while True:
            raw = await websocket.receive_text()
            try:
                msg = orjson.loads(raw)
            except orjson.JSONDecodeError:
                continue
            requested = set(msg.get("instruments", []))
            if msg.get("type") == "subscribe":
                new = requested - instruments
                instruments.update(new)
                await _subscribe(pubsub, new)
            elif msg.get("type") == "unsubscribe":
                to_remove = requested & instruments
                for instrument in to_remove:
                    await pubsub.punsubscribe(f"ticks:{instrument}", f"candles:{instrument}:*")
                instruments.difference_update(to_remove)

    reader_task = asyncio.create_task(reader())
    writer_task = asyncio.create_task(writer())
    try:
        done, pending = await asyncio.wait({reader_task, writer_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        writer_task.cancel()
        await pubsub.close()
