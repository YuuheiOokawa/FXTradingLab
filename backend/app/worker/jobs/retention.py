"""Tick/candle retention job (docs/04_DATABASE_DESIGN.md).

Deliberately written as a plain `async def run(ctx)` with no APScheduler-specific
state so migrating the scheduler to Celery later is a swap of the caller, not a
rewrite of this logic (docs/03_TECH_STACK.md).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import Settings, get_settings
from app.db.models.market import Candle, MarketTick
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


@dataclass
class JobContext:
    settings: Settings


async def run(ctx: JobContext | None = None) -> dict[str, int]:
    settings = (ctx or JobContext(get_settings())).settings
    now = datetime.now(UTC)
    tick_cutoff = now - timedelta(days=settings.tick_retention_days)
    candle_cutoff = now - timedelta(days=settings.candle_1m_retention_days)

    async with AsyncSessionLocal() as session:
        tick_result = await session.execute(delete(MarketTick).where(MarketTick.ts < tick_cutoff))
        candle_result = await session.execute(
            delete(Candle).where(Candle.granularity == "M1", Candle.open_time < candle_cutoff)
        )
        await session.commit()

    deleted = {
        "ticks_deleted": tick_result.rowcount or 0,
        "m1_candles_deleted": candle_result.rowcount or 0,
    }
    logger.info("retention job complete: %s", deleted)
    return deleted
