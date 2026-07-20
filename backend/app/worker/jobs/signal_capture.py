"""Periodic signal snapshot capture (docs/08_SIGNAL_ENGINE.md "Signal outcome
history"). Runs independently of FULL_AUTO mode / auto_trader.py — this exists
purely to build a historical record for the Analytics score-bucket accuracy
view, not to trade. Evaluates the entry-timeframe signal for every watched
instrument and persists a row (app/db/models/strategy.py::Signal) whenever the
score crosses MIN_SCORE_THRESHOLD, deduplicated by (instrument, granularity,
candle) so re-running against the same still-current candle is a no-op.
"""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.brokers.base import BrokerAdapter
from app.brokers.factory import get_market_data_provider
from app.brokers.schemas import Granularity
from app.core.config import get_settings
from app.db.models.strategy import Signal
from app.db.session import AsyncSessionLocal
from app.services.backtest.engine import MIN_SCORE_THRESHOLD
from app.services.market_data import ensure_instruments
from app.services.signal_engine import evaluate

logger = logging.getLogger(__name__)

ENTRY_TIMEFRAME = Granularity.M15
HIGHER_TIMEFRAMES = {"H1": Granularity.H1, "H4": Granularity.H4}


def _candles_to_df(candles) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": [c.open_time for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )


async def _capture_one(broker: BrokerAdapter, instrument_id, symbol: str) -> bool:
    entry_candles = await broker.get_candles(symbol, ENTRY_TIMEFRAME, 300)
    if len(entry_candles) < 210:
        return False
    higher_tf = {}
    for label, gran in HIGHER_TIMEFRAMES.items():
        candles = await broker.get_candles(symbol, gran, 300)
        if len(candles) >= 200:
            higher_tf[label] = _candles_to_df(candles)

    entry_df = _candles_to_df(entry_candles)
    signal = evaluate(entry_df, higher_tf)
    if signal.score < MIN_SCORE_THRESHOLD:
        return False

    last_bar = entry_df.iloc[-1]
    row = dict(
        instrument_id=instrument_id,
        granularity=ENTRY_TIMEFRAME.value,
        ts=last_bar["open_time"],
        direction=signal.direction,
        score=signal.score,
        label=signal.label,
        regime_trend=signal.regime.trend,
        regime_volatility=signal.regime.volatility,
        reasons=[{"status": r.status, "text": r.text, "points": r.points} for r in signal.reasons],
        entry_price=float(last_bar["close"]),
    )

    async with AsyncSessionLocal() as session:
        stmt = pg_insert(Signal).values(**row).on_conflict_do_nothing(
            constraint="uq_signal_instrument_granularity_ts"
        )
        result = await session.execute(stmt)
        await session.commit()
    return bool(result.rowcount)


async def run() -> dict[str, int]:
    settings = get_settings()
    broker = get_market_data_provider()
    instruments = await ensure_instruments(settings.watchlist)

    captured = 0
    for symbol, instrument in instruments.items():
        try:
            if await _capture_one(broker, instrument.id, symbol):
                captured += 1
        except Exception:
            logger.exception("signal_capture failed for %s", symbol)

    logger.info("signal_capture job complete: captured=%d watchlist=%d", captured, len(instruments))
    return {"captured": captured}
