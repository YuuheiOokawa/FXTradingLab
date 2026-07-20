"""Worker process entrypoint: continuous market data polling + scheduled maintenance
jobs. Runs separately from the API process (docs/02_SYSTEM_ARCHITECTURE.md) so a
slow API request never blocks price monitoring, and so it can be restarted/scaled
independently.

Run with: python -m app.worker.main
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.brokers.factory import get_market_data_provider
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis_client import get_redis
from app.services.market_data import MarketDataService
from app.worker.jobs import heartbeat, retention, signal_capture, signal_outcome

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    settings = get_settings()
    market_data_broker = get_market_data_provider()
    redis = get_redis()

    logger.info(
        "worker starting: market_data_provider=%s broker_provider=%s environment=%s watchlist=%s",
        market_data_broker.provider,
        settings.broker_provider,
        settings.broker_environment,
        settings.watchlist,
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(retention.run, "cron", hour=3, minute=0, id="retention")
    # Signal outcome history (docs/08_SIGNAL_ENGINE.md): capture runs often
    # enough to catch each new M15 candle close; outcome computation runs
    # less often since OUTCOME_HORIZON_MINUTES (4h) means most runs find
    # nothing newly eligible.
    scheduler.add_job(signal_capture.run, "interval", minutes=5, id="signal_capture")
    scheduler.add_job(signal_outcome.run, "interval", minutes=20, id="signal_outcome")
    scheduler.add_job(heartbeat.run, "interval", seconds=30, id="heartbeat")
    scheduler.start()

    market_data = MarketDataService(market_data_broker, redis)

    # The FULL_AUTO risk->signal->order evaluation loop (docs/10_RISK_MANAGEMENT.md)
    # is registered here once enabled — see app/services/auto_trader.py.
    try:
        from app.services.auto_trader import run_auto_trader_loop

        asyncio.create_task(run_auto_trader_loop())
    except ImportError:
        logger.info("auto_trader not yet available; FULL_AUTO loop not started")

    await market_data.run(settings.watchlist)


if __name__ == "__main__":
    asyncio.run(main())
