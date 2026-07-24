"""Enforces stop-loss and take-profit on OPEN paper positions.

Paper positions stored a `stop_loss` and `take_profit` but nothing ever acted
on them: only the backtest engine (app/services/backtest/engine.py) checked
brackets, so a live paper position could run past its stop indefinitely. That
made every risk figure the app reported — `max_risk_per_trade_pct`, the sizing
in app/services/position_sizing.py, and the whole playbook study, all of which
assume a stop actually fills — fiction in forward testing. This job closes that
gap.

Fill convention matches `OrderOrchestrator.close_paper_position`: a long exits
on the BID, a short on the ASK, so the spread is paid on the way out exactly as
it is in the backtest's cost model.

When both levels are breached in the same poll, the STOP is taken. Real
intra-poll order is unknowable here, and assuming the worse of the two is the
only assumption that cannot flatter results.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.brokers.factory import get_market_data_provider
from app.db.models.market import Instrument
from app.db.models.trading import PaperPosition
from app.db.session import AsyncSessionLocal
from app.services.order_orchestrator import OrderOrchestrator

logger = logging.getLogger(__name__)


def breach(
    direction: str,
    bid: float,
    ask: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[str, float] | None:
    """Return (reason, fill_price) when a bracket is breached, else None.

    The stop is evaluated before the target so a bar that touches both is
    resolved pessimistically.
    """
    exit_price = bid if direction == "BUY" else ask
    if direction == "BUY":
        if stop_loss is not None and exit_price <= stop_loss:
            return "stop loss", stop_loss
        if take_profit is not None and exit_price >= take_profit:
            return "take profit", take_profit
        return None
    if stop_loss is not None and exit_price >= stop_loss:
        return "stop loss", stop_loss
    if take_profit is not None and exit_price <= take_profit:
        return "take profit", take_profit
    return None


async def run() -> dict[str, int]:
    broker = get_market_data_provider()
    orchestrator = OrderOrchestrator(broker)
    closed = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PaperPosition, Instrument.symbol)
            .join(Instrument, Instrument.id == PaperPosition.instrument_id)
            .where(PaperPosition.status == "open")
        )
        rows = result.all()

        for position, symbol in rows:
            if position.stop_loss is None and position.take_profit is None:
                continue
            try:
                quote = await broker.get_current_price(symbol)
                hit = breach(
                    position.direction, quote.bid, quote.ask, position.stop_loss, position.take_profit
                )
                if hit is None:
                    continue
                reason, fill = hit
                await orchestrator.close_paper_position(
                    session, position.id, reason=reason, close_price=fill
                )
                closed += 1
                logger.info(
                    "paper_brackets: closed %s on %s at %.5f", symbol, reason, fill, extra={"symbol": symbol}
                )
            except Exception:
                logger.exception("paper_brackets: failed checking %s", symbol, extra={"symbol": symbol})

    if closed:
        logger.info("paper_brackets job complete: closed=%d of %d open", closed, len(rows))
    return {"closed": closed, "checked": len(rows)}
