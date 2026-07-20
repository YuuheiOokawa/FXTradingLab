"""Fills pending Paper Trading limit/stop orders (docs/15_PRODUCTION_
READINESS_REVIEW.md "Paper Trading" — order-type groundwork). Placing a
limit/stop order via OrderOrchestrator.submit_paper_order only creates a
`pending` PaperOrder row with no position; this job is what actually
triggers the fill once the price crosses the order's limit_price, running
periodically against every watched instrument's current quote.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.brokers.factory import get_market_data_provider
from app.db.models.trading import PaperOrder
from app.db.session import AsyncSessionLocal
from app.services.order_orchestrator import OrderOrchestrator

logger = logging.getLogger(__name__)


async def run() -> dict[str, int]:
    broker = get_market_data_provider()
    orchestrator = OrderOrchestrator(broker)
    filled = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PaperOrder).where(PaperOrder.status == "pending"))
        pending = result.scalars().all()
        for order in pending:
            try:
                position = await orchestrator.try_fill_pending_order(session, order)
                if position is not None:
                    filled += 1
            except Exception:
                logger.exception("paper_pending_orders: failed checking order_id=%s", order.id)

    logger.info("paper_pending_orders job complete: filled=%d pending=%d", filled, len(pending))
    return {"filled": filled, "pending": len(pending)}
