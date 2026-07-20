"""FULL_AUTO evaluation loop (docs/10_RISK_MANAGEMENT.md): when
`risk_settings.auto_mode == "full_auto"`, periodically evaluates the Signal Engine
for each watched instrument and, on a qualifying signal, submits a PAPER order
through the same `OrderOrchestrator.submit_paper_order` path used by manual orders —
so it is impossible for this loop to bypass the Risk Engine.

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

from app.brokers.factory import get_market_data_provider
from app.brokers.schemas import Granularity
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.indicators import atr
from app.services.order_orchestrator import OrderOrchestrator
from app.services.repo import get_or_create_risk_settings
from app.services.risk_engine import RiskRejected
from app.services.signal_engine import evaluate

logger = logging.getLogger(__name__)

EVAL_INTERVAL_SECONDS = 60
ENTRY_TIMEFRAME = Granularity.M15
HIGHER_TIMEFRAMES = {"H1": Granularity.H1, "H4": Granularity.H4}
ATR_STOP_MULT = 1.5
ATR_TARGET_MULT = 3.0


def _candles_to_df(candles) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )


async def _evaluate_and_maybe_trade(orchestrator: OrderOrchestrator, instrument: str) -> None:
    broker = orchestrator._broker  # noqa: SLF001 - internal use within the same service layer
    entry_candles = await broker.get_candles(instrument, ENTRY_TIMEFRAME, 300)
    if len(entry_candles) < 210:
        return
    higher_tf = {}
    for label, gran in HIGHER_TIMEFRAMES.items():
        candles = await broker.get_candles(instrument, gran, 300)
        if len(candles) >= 200:
            higher_tf[label] = _candles_to_df(candles)

    entry_df = _candles_to_df(entry_candles)
    signal = evaluate(entry_df, higher_tf)
    if signal.label not in ("買い", "強い買い", "売り", "強い売り"):
        return

    atr_series = atr(entry_df["high"], entry_df["low"], entry_df["close"], 14)
    atr_value = float(atr_series.iloc[-1])
    if pd.isna(atr_value) or atr_value <= 0:
        return

    price = float(entry_df["close"].iloc[-1])
    if signal.direction == "BUY":
        stop_loss = price - ATR_STOP_MULT * atr_value
        take_profit = price + ATR_TARGET_MULT * atr_value
    else:
        stop_loss = price + ATR_STOP_MULT * atr_value
        take_profit = price - ATR_TARGET_MULT * atr_value

    from app.brokers.schemas import OrderRequest

    order = OrderRequest(
        instrument=instrument,
        direction=signal.direction,
        size=1000,
        stop_loss=round(stop_loss, 5),
        take_profit=round(take_profit, 5),
        idempotency_key=f"auto-{instrument}-{signal.direction}-{uuid.uuid4()}",
    )
    async with AsyncSessionLocal() as session:
        try:
            outcome = await orchestrator.submit_paper_order(session, order)
            logger.info("FULL_AUTO order placed: %s %s score=%s", instrument, signal.direction, signal.score)
        except RiskRejected as exc:
            logger.info("FULL_AUTO order rejected by Risk Engine: %s (%s)", exc.code, exc.message)


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
