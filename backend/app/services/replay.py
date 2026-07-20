"""Replay mode (docs/01_REQUIREMENTS.md FR-9): step through historical candles one
at a time with future bars hidden, let the user commit to BUY/SELL/skip, then show
the outcome plus (if TRAINING_ON, or always after the decision) the rule-based
breakdown for that moment.

Persisted to the DB (`app/db/models/replay.py::ReplaySession`/`ReplayTrade`) —
previously in-process-memory only, so a server restart silently lost every
in-progress session and there was no record to review later
(docs/15_PRODUCTION_READINESS_REVIEW.md "Replay"). The candle set is stored
as a fixed JSON snapshot at session creation and never re-fetched, which is
what actually enforces the no-future-leak invariant here: `visible_candles()`
only ever slices that frozen list up to `current_index`, so there is no code
path — response serialization, state, or otherwise — that can expose a bar
beyond what the user has stepped to. `judge_decision()`
(app/services/replay_judgment.py) grades each decision qualitatively, not by
whether it ended up profitable.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.brokers.schemas import Candle
from app.db.models.replay import ReplaySession, ReplayTrade
from app.services.replay_judgment import judge_decision
from app.services.signal_engine import SignalResult, evaluate

Decision = Literal["BUY", "SELL", "SKIP"]

WARMUP_BARS = 210


def _rehydrate_candles(raw: list[dict]) -> list[Candle]:
    return [Candle.model_validate(c) for c in raw]


def visible_candles(session: ReplaySession) -> list[Candle]:
    candles = _rehydrate_candles(session.candles)
    return candles[: session.current_index + 1]


def _visible_df(session: ReplaySession) -> pd.DataFrame:
    visible = visible_candles(session)
    return pd.DataFrame(
        {
            "open_time": [c.open_time for c in visible],
            "open": [c.open for c in visible],
            "high": [c.high for c in visible],
            "low": [c.low for c in visible],
            "close": [c.close for c in visible],
        }
    )


def is_at_end(session: ReplaySession) -> bool:
    return session.current_index >= len(session.candles) - 1


def _open_trade(session: ReplaySession) -> ReplayTrade | None:
    for trade in session.trades:
        if trade.action != "SKIP" and trade.exit_price is None:
            return trade
    return None


async def create_session(
    db: AsyncSession,
    instrument_id: uuid.UUID,
    granularity: str,
    candles: list[Candle],
    training_mode: bool,
    initial_balance: float = 1_000_000.0,
) -> ReplaySession:
    start_index = min(WARMUP_BARS, max(0, len(candles) - 2))
    session = ReplaySession(
        instrument_id=instrument_id,
        granularity=granularity,
        start_time=candles[0].open_time,
        current_time=candles[start_index].open_time,
        speed=1.0,
        status="active",
        initial_balance=initial_balance,
        current_balance=initial_balance,
        training_mode=training_mode,
        current_index=start_index,
        candles=[c.model_dump(mode="json") for c in candles],
    )
    db.add(session)
    await db.commit()
    # `attribute_names=["trades"]` loads the (empty, for a brand-new session)
    # relationship the proper async-safe way — a bare attribute access here
    # would trigger an implicit lazy-load query outside of an awaited
    # context and raise MissingGreenlet.
    await db.refresh(session, attribute_names=["trades"])
    return session


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> ReplaySession | None:
    result = await db.execute(
        select(ReplaySession).where(ReplaySession.id == session_id).options(selectinload(ReplaySession.trades))
    )
    return result.scalar_one_or_none()


async def step(db: AsyncSession, session: ReplaySession) -> Candle | None:
    if is_at_end(session):
        return None
    session.current_index += 1
    candles = _rehydrate_candles(session.candles)
    new_candle = candles[session.current_index]
    session.current_time = new_candle.open_time

    open_trade = _open_trade(session)
    if open_trade is not None:
        entry = open_trade.entry_price or new_candle.close
        direction = open_trade.action
        diff = (new_candle.close - entry) if direction == "BUY" else (entry - new_candle.close)
        open_trade.max_favorable = max(open_trade.max_favorable, diff)
        open_trade.max_adverse = min(open_trade.max_adverse, diff)

    if is_at_end(session):
        session.status = "finished"
    await db.commit()
    return new_candle


def _signal_snapshot(signal: SignalResult | None) -> dict:
    if signal is None:
        return {}
    return {
        "direction": signal.direction,
        "score": signal.score,
        "buy_score": signal.buy_score,
        "sell_score": signal.sell_score,
        "label": signal.label,
        "regime_trend": signal.regime.trend,
        "regime_volatility": signal.regime.volatility,
        "reasons": [{"status": r.status, "text": r.text, "points": r.points} for r in signal.reasons],
    }


async def decide(
    db: AsyncSession,
    session: ReplaySession,
    action: Decision,
    stop_loss_pips: float | None = None,
    take_profit_pips: float | None = None,
) -> ReplayTrade:
    candles = _rehydrate_candles(session.candles)
    current_candle = candles[session.current_index]
    # Evaluated for every decision (not just non-SKIP) so skip judgment has
    # the same signal context an entry decision would - evaluate() itself
    # only ever sees visible_candles(), so this carries no future leak.
    signal = evaluate(_visible_df(session))

    trade = ReplayTrade(
        session_id=session.id,
        decided_at_index=session.current_index,
        decided_at_time=current_candle.open_time,
        action=action,
        entry_price=current_candle.close if action != "SKIP" else None,
        stop_loss_pips=stop_loss_pips,
        take_profit_pips=take_profit_pips,
        signal_snapshot=_signal_snapshot(signal),
    )
    result = judge_decision(action, signal, stop_loss_pips, take_profit_pips)
    trade.judgment = result.judgment
    trade.judgment_criteria = result.criteria_dicts()

    db.add(trade)
    session.trades.append(trade)
    await db.commit()
    await db.refresh(trade)
    return trade


async def close_open_decision(db: AsyncSession, session: ReplaySession) -> ReplayTrade | None:
    trade = _open_trade(session)
    if trade is None:
        return None
    candles = _rehydrate_candles(session.candles)
    current_candle = candles[session.current_index]
    trade.exit_price = current_candle.close
    diff = (
        (trade.exit_price - trade.entry_price)
        if trade.action == "BUY"
        else (trade.entry_price - trade.exit_price)
    )
    trade.pnl = diff
    session.current_balance += diff
    await db.commit()
    await db.refresh(trade)
    return trade
