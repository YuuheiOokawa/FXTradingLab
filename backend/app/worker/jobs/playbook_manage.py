"""Manages exits for positions opened by the playbook auto-trader.

The 23-year study behind app/services/playbook.py does not use fixed brackets
alone — its results depend on two things a set-and-forget stop/target cannot do:

* **Trailing stops** (USD/JPY, EUR/JPY): the stop ratchets to
  `extreme - trail_atr * ATR` as the trade goes the right way, and never
  loosens. This is what let the winners run — the biggest single trade in the
  study was +2,505 pips held 498 days, which any fixed target would have cut short.
* **Mean-reversion exits** (GBP/JPY): the trade closes when price reaches the
  20-day mean, or after `max_hold_bars` days if the reversion never comes. A
  fade with no time limit turns into an unintended long-term position.

The protective stop itself is enforced by the broker/paper bracket; this job
only tightens it and closes on the non-price conditions. It runs on a schedule
from app/worker/main.py.

Positions opened by hand are left alone: only rows whose opening order came
from the auto-trader (`opening_idempotency_key` starting "auto-") are managed,
so a manual trade never has its stop moved underneath the operator.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select

from app.brokers.factory import get_market_data_provider
from app.brokers.schemas import Granularity
from app.db.models.market import Instrument
from app.db.models.trading import PaperPosition
from app.db.session import AsyncSessionLocal
from app.services import playbook
from app.services.auto_trader import candles_to_df
from app.services.indicators import atr, sma
from app.services.order_orchestrator import OrderOrchestrator

logger = logging.getLogger(__name__)

TIMEFRAME = Granularity.D
CANDLE_COUNT = 300
AUTO_PREFIX = "auto-"


def compute_trailing_stop(
    direction: str,
    entry_price: float,
    current_stop: float | None,
    extreme_price: float,
    atr_value: float,
    trail_atr: float,
) -> float | None:
    """Return a tightened stop, or None when it should not move.

    `extreme_price` is the best price seen since entry (highest high for a long,
    lowest low for a short). The stop only ever moves in the profitable
    direction — a trailing stop that could loosen would silently widen risk.
    """
    if atr_value <= 0:
        return None
    if direction == "BUY":
        candidate = extreme_price - trail_atr * atr_value
        if current_stop is not None and candidate <= current_stop:
            return None
        return candidate
    candidate = extreme_price + trail_atr * atr_value
    if current_stop is not None and candidate >= current_stop:
        return None
    return candidate


def mean_exit_reached(direction: str, close: float, mean_value: float) -> bool:
    return close >= mean_value if direction == "BUY" else close <= mean_value


async def run() -> dict[str, int]:
    broker = get_market_data_provider()
    orchestrator = OrderOrchestrator(broker)
    trailed = closed = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PaperPosition, Instrument.symbol)
            .join(Instrument, Instrument.id == PaperPosition.instrument_id)
            .where(PaperPosition.status == "open")
        )
        rows = result.all()

        for position, symbol in rows:
            key = position.opening_idempotency_key or ""
            if not key.startswith(AUTO_PREFIX):
                continue
            cfg = playbook.config_for(symbol)
            if cfg is None:
                continue

            try:
                candles = await broker.get_candles(symbol, TIMEFRAME, CANDLE_COUNT)
                if len(candles) < 30:
                    continue
                df = candles_to_df(candles)
                close = float(df["close"].iloc[-1])
                atr_value = float(atr(df["high"], df["low"], df["close"], 14).iloc[-1])

                # Bars elapsed since entry, used for the fade styles' time stop.
                held_days = (datetime.now(UTC) - position.opened_at).days

                if cfg.exit_style == "mean":
                    mean_value = float(sma(df["close"], cfg.mean_period).iloc[-1])
                    if pd.notna(mean_value) and mean_exit_reached(position.direction, close, mean_value):
                        await orchestrator.close_paper_position(
                            session, position.id, reason="mean reversion target"
                        )
                        closed += 1
                        logger.info(
                            "playbook_manage: closed %s at mean %.5f", symbol, mean_value, extra={"symbol": symbol}
                        )
                        continue
                    if cfg.max_hold_bars is not None and held_days >= cfg.max_hold_bars:
                        await orchestrator.close_paper_position(
                            session, position.id, reason="max hold reached"
                        )
                        closed += 1
                        logger.info(
                            "playbook_manage: closed %s on max hold (%d days)",
                            symbol, held_days, extra={"symbol": symbol},
                        )
                    continue

                # Trailing styles: ratchet the stop toward the best price seen.
                if cfg.trail_atr is None or pd.isna(atr_value):
                    continue
                since = df.tail(max(held_days + 1, 2))
                extreme = float(since["high"].max()) if position.direction == "BUY" else float(since["low"].min())
                new_stop = compute_trailing_stop(
                    position.direction, position.entry_price, position.stop_loss,
                    extreme, atr_value, cfg.trail_atr,
                )
                if new_stop is not None:
                    position.stop_loss = round(new_stop, 5)
                    trailed += 1
                    logger.info(
                        "playbook_manage: trailed %s stop -> %.5f", symbol, position.stop_loss, extra={"symbol": symbol}
                    )
            except Exception:
                logger.exception("playbook_manage: failed managing %s", symbol, extra={"symbol": symbol})

        await session.commit()

    logger.info("playbook_manage job complete: trailed=%d closed=%d", trailed, closed)
    return {"trailed": trailed, "closed": closed}
