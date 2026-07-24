"""FULL_AUTO evaluation loop (docs/10_RISK_MANAGEMENT.md): when
`risk_settings.auto_mode == "full_auto"`, periodically evaluates each watched
instrument's OWN rulebook (app/services/playbook.py) and, on a qualifying
signal, submits a PAPER order through the same `OrderOrchestrator.submit_paper_order`
path used by manual orders — so it is impossible for this loop to bypass the
Risk Engine.

Two things changed when the playbook replaced the shared Signal Engine rules
here, both driven by the 23-year study in app/services/playbook.py's docstring:

1. **Per instrument rules.** One strategy across all pairs lost money over 23
   years; each pair now gets the style its own variance ratio calls for.
2. **Daily candles.** The playbook was measured on daily bars, so it is
   evaluated on daily bars. Running a daily-validated rule on M15 data would be
   a different (unvalidated) strategy that merely shares its name.

Exits are NOT set-and-forget: trailing stops and mean-reversion targets are
managed continuously by app/worker/jobs/playbook_manage.py.

This loop only ever trades PAPER accounts. LIVE auto-trading would additionally
require `submit_live_order`'s three-gate check (docs/10_RISK_MANAGEMENT.md), which
is not wired to any automatic loop in this build — LIVE order submission is manual
even when FULL_AUTO is selected, pending a real funded broker account to test
against (docs/14_IMPLEMENTATION_PLAN.md).
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import pandas as pd
from sqlalchemy import select

from app.brokers.factory import get_market_data_provider
from app.brokers.schemas import Granularity, OrderRequest
from app.core.config import get_settings
from app.core.request_context import order_context
from app.db.models.market import Instrument
from app.db.models.trading import PaperPosition
from app.db.session import AsyncSessionLocal
from app.services import playbook
from app.services.indicators import atr
from app.services.order_orchestrator import OrderOrchestrator
from app.services.position_sizing import size_for_risk, volatility_multiplier
from app.services.repo import get_or_create_paper_account, get_or_create_risk_settings
from app.services.risk_engine import RiskRejected

logger = logging.getLogger(__name__)

# Daily rules only change on a daily close, so evaluating every 15 minutes is
# already far more often than needed; it exists so a restart mid-session picks
# the day's signal up promptly rather than waiting for the next midnight.
EVAL_INTERVAL_SECONDS = 900
TIMEFRAME = Granularity.D
CANDLE_COUNT = 400


def candles_to_df(candles) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )


def _drop_forming_candle(candles) -> list:
    """Playbook rules must only ever see CLOSED candles — reading a still-forming
    bar's close is look-ahead, since that price can still move before the bar ends."""
    if candles and getattr(candles[-1], "is_final", True) is False:
        return list(candles[:-1])
    return list(candles)


async def _has_open_position(session, instrument: str) -> bool:
    """One position per instrument at a time, matching how the strategy was
    measured (the backtest never stacked entries on the same pair)."""
    result = await session.execute(
        select(PaperPosition.id)
        .join(Instrument, Instrument.id == PaperPosition.instrument_id)
        .where(Instrument.symbol == instrument, PaperPosition.status == "open")
        .limit(1)
    )
    return result.first() is not None


async def _evaluate_and_maybe_trade(orchestrator: OrderOrchestrator, instrument: str) -> None:
    if playbook.config_for(instrument) is None:
        return

    broker = orchestrator._broker  # noqa: SLF001 - internal use within the same service layer
    candles = _drop_forming_candle(await broker.get_candles(instrument, TIMEFRAME, CANDLE_COUNT))
    if len(candles) < playbook.MIN_BARS:
        return

    df = candles_to_df(candles)
    signal = playbook.evaluate(instrument, df)
    if signal is None:
        return

    async with AsyncSessionLocal() as session:
        if await _has_open_position(session, instrument):
            return

        risk_settings = await get_or_create_risk_settings(session)
        account = await get_or_create_paper_account(session)

        # Size so a stop-out costs the same fraction of equity every time,
        # instead of a fixed lot whose risk swings with each pair's volatility.
        baseline_atr = float(atr(df["high"], df["low"], df["close"], 14).median())
        sizing = size_for_risk(
            equity=float(account.balance),
            risk_pct=float(risk_settings.max_risk_per_trade_pct),
            entry_price=signal.price,
            stop_loss=signal.stop_loss,
            multiplier=volatility_multiplier(signal.atr, baseline_atr),
        )
        if sizing is None:
            logger.info(
                "FULL_AUTO skipped %s: no size fits the %.2f%% risk budget",
                instrument,
                risk_settings.max_risk_per_trade_pct,
                extra={"symbol": instrument},
            )
            return

        order = OrderRequest(
            instrument=instrument,
            direction=signal.direction,
            size=sizing.size,
            stop_loss=round(signal.stop_loss, 5),
            take_profit=round(signal.take_profit, 5) if signal.take_profit is not None else None,
            idempotency_key=f"auto-{instrument}-{signal.direction}-{uuid.uuid4()}",
        )
        with order_context(order.idempotency_key):
            try:
                await orchestrator.submit_paper_order(session, order)
                logger.info(
                    "FULL_AUTO order placed: %s %s style=%s size=%.0f risk=%.2f%% (%s) reason=%s",
                    instrument,
                    signal.direction,
                    signal.style,
                    sizing.size,
                    sizing.risk_pct_of_equity,
                    sizing.note,
                    signal.reason,
                    extra={"symbol": instrument},
                )
            except RiskRejected as exc:
                logger.info(
                    "FULL_AUTO order rejected by Risk Engine: %s (%s)",
                    exc.code,
                    exc.message,
                    extra={"symbol": instrument},
                )


async def run_auto_trader_loop() -> None:
    # Paper trading only ever reads prices — it never touches the trading
    # broker — so the market-data provider is the correct (and only) source
    # here even when MARKET_DATA_PROVIDER differs from BROKER_PROVIDER.
    broker = get_market_data_provider()
    orchestrator = OrderOrchestrator(broker)
    settings = get_settings()
    while True:
        try:
            async with AsyncSessionLocal() as session:
                risk_settings = await get_or_create_risk_settings(session)
                auto_mode = risk_settings.auto_mode
                kill_switch = risk_settings.kill_switch_active
            if auto_mode == "full_auto" and not kill_switch:
                for instrument in settings.watchlist:
                    await _evaluate_and_maybe_trade(orchestrator, instrument)
        except Exception:
            logger.exception("auto_trader loop iteration failed; will retry next interval")
        await asyncio.sleep(EVAL_INTERVAL_SECONDS)
