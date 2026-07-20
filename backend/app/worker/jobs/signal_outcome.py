"""Signal outcome computation (docs/08_SIGNAL_ENGINE.md "Signal outcome
history"). For each captured Signal (app/worker/jobs/signal_capture.py) whose
OUTCOME_HORIZON has actually elapsed, reads the candles that followed it from
the DB (never re-fetched from the broker — this is purely retrospective) and
records what happened: how far price moved in the signal's favor and against
it, where price ended up after a fixed horizon, and whether it technically
touched an assumed TP/SL distance.

Deliberately NOT a trade simulation: unlike Backtest/Paper Trading, this does
not apply conservative same-bar SL-before-TP ordering, spread, or slippage —
tp_reached and sl_reached are independently "did price touch this level at
any point", which can both be true in the same window. This is intentionally
looser: it exists to answer "does a high-score signal usually move favorably
afterward", not to simulate a specific tradeable outcome. See
docs/08_SIGNAL_ENGINE.md for this distinction spelled out for anyone reading
the Analytics page.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models.market import Candle, Instrument
from app.db.models.strategy import Signal
from app.db.session import AsyncSessionLocal
from app.services.backtest.engine import pip_size_for

logger = logging.getLogger(__name__)

OUTCOME_HORIZON_MINUTES = 240  # 4 hours
# Same defaults BacktestConfig uses — not a live trade, just a familiar,
# documented reference distance for "did price move this far".
ASSUMED_STOP_LOSS_PIPS = 30.0
ASSUMED_TAKE_PROFIT_PIPS = 60.0


async def _compute_one(session, signal: Signal, pip: float) -> bool:
    horizon_end = signal.ts + timedelta(minutes=OUTCOME_HORIZON_MINUTES)
    result = await session.execute(
        select(Candle)
        .where(
            Candle.instrument_id == signal.instrument_id,
            Candle.granularity == signal.granularity,
            Candle.open_time > signal.ts,
            Candle.open_time <= horizon_end,
        )
        .order_by(Candle.open_time.asc())
    )
    window = result.scalars().all()
    if not window or window[-1].open_time < horizon_end:
        return False  # not enough history yet to cover the full horizon — try again later

    entry = signal.entry_price
    direction = signal.direction
    sign = 1.0 if direction == "BUY" else -1.0

    highs = [c.high for c in window]
    lows = [c.low for c in window]
    if direction == "BUY":
        max_favorable = (max(highs) - entry) / pip
        max_adverse = (entry - min(lows)) / pip
    else:
        max_favorable = (entry - min(lows)) / pip
        max_adverse = (max(highs) - entry) / pip

    price_after = (window[-1].close - entry) * sign / pip

    tp_level = entry + sign * ASSUMED_TAKE_PROFIT_PIPS * pip
    sl_level = entry - sign * ASSUMED_STOP_LOSS_PIPS * pip
    if direction == "BUY":
        tp_reached = any(c.high >= tp_level for c in window)
        sl_reached = any(c.low <= sl_level for c in window)
    else:
        tp_reached = any(c.low <= tp_level for c in window)
        sl_reached = any(c.high >= sl_level for c in window)

    signal.max_favorable_pips = round(max_favorable, 2)
    signal.max_adverse_pips = round(max_adverse, 2)
    signal.price_after_horizon_pips = round(price_after, 2)
    signal.tp_reached = tp_reached
    signal.sl_reached = sl_reached
    signal.outcome_computed_at = datetime.now(UTC)
    return True


async def run() -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(minutes=OUTCOME_HORIZON_MINUTES)
    computed = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Signal).where(Signal.outcome_computed_at.is_(None), Signal.ts <= cutoff)
        )
        pending = result.scalars().all()

        instrument_pips: dict = {}
        for signal in pending:
            try:
                pip = instrument_pips.get(signal.instrument_id)
                if pip is None:
                    inst = await session.get(Instrument, signal.instrument_id)
                    pip = pip_size_for(inst.symbol) if inst else 0.01
                    instrument_pips[signal.instrument_id] = pip
                if await _compute_one(session, signal, pip):
                    computed += 1
            except Exception:
                logger.exception("signal_outcome failed for signal_id=%s", signal.id)
        await session.commit()

    logger.info("signal_outcome job complete: computed=%d pending=%d", computed, len(pending))
    return {"computed": computed, "pending": len(pending)}
