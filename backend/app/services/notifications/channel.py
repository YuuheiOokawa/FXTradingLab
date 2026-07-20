"""Pluggable notification channels (docs/01_REQUIREMENTS.md FR-21).

`InAppChannel` is the only channel with a real implementation in v1 — it persists
a `Notification` row and publishes to the `system:events` Redis channel that
`/ws/system` forwards to the browser. `DiscordChannel` and `LineChannel` are
interface-ready stubs: the `NotificationChannel` protocol is exactly what
`OrderOrchestrator` and other callers use, so adding a real Discord/LINE/email
integration later is a matter of implementing `send()` in these classes and
including them in `get_active_channels()` — no caller-side changes needed.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.journal import Notification

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    async def send(self, session: AsyncSession, kind: str, title: str, body: str) -> None: ...


class InAppChannel:
    """Writes to the `notifications` table and pushes a live update over
    `/ws/system` via Redis pub/sub (docs/07_REALTIME_DATA_DESIGN.md)."""

    async def send(self, session: AsyncSession, kind: str, title: str, body: str) -> None:
        session.add(Notification(ts=datetime.now(UTC), channel="in_app", kind=kind, title=title, body=body))
        try:
            import orjson

            from app.core.redis_client import get_redis

            await get_redis().publish(
                "system:events", orjson.dumps({"type": "notification", "kind": kind, "title": title, "body": body})
            )
        except Exception:  # noqa: BLE001 - best-effort live push; the DB row is the source of truth
            logger.debug("failed to publish notification to system:events", exc_info=True)


class DiscordChannel:
    """Stub — set `DISCORD_WEBHOOK_URL` and implement the webhook POST here."""

    async def send(self, session: AsyncSession, kind: str, title: str, body: str) -> None:
        settings = get_settings()
        if not settings.discord_webhook_url:
            return
        logger.info("DiscordChannel is a stub; would have sent: %s — %s", title, body)


class LineChannel:
    """Stub — set `LINE_NOTIFY_TOKEN` and implement the LINE Notify API call here."""

    async def send(self, session: AsyncSession, kind: str, title: str, body: str) -> None:
        settings = get_settings()
        if not settings.line_notify_token:
            return
        logger.info("LineChannel is a stub; would have sent: %s — %s", title, body)


def get_active_channels() -> list[NotificationChannel]:
    settings = get_settings()
    channels: list[NotificationChannel] = [InAppChannel()]
    if settings.discord_webhook_url:
        channels.append(DiscordChannel())
    if settings.line_notify_token:
        channels.append(LineChannel())
    return channels


async def notify(session: AsyncSession, kind: str, title: str, body: str) -> None:
    for channel in get_active_channels():
        await channel.send(session, kind, title, body)
