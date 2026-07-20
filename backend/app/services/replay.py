"""Replay mode (docs/01_REQUIREMENTS.md FR-9): step through historical candles one
at a time with future bars hidden, let the user commit to BUY/SELL/skip, then show
the outcome plus (if TRAINING_ON, or always after the decision) the rule-based
breakdown for that moment. In-memory session store — see simulator.py's docstring
for why that's an acceptable v1 simplification for this kind of ephemeral,
practice-oriented state.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import pandas as pd

from app.brokers.schemas import Candle
from app.services.signal_engine import SignalResult, evaluate

Decision = Literal["BUY", "SELL", "SKIP"]

WARMUP_BARS = 210


@dataclass
class ReplayDecisionRecord:
    decided_at_index: int
    action: Decision
    entry_price: float | None
    exit_price: float | None = None
    pnl: float | None = None
    max_favorable: float = 0.0
    max_adverse: float = 0.0
    signal_at_decision: SignalResult | None = None


@dataclass
class ReplaySession:
    id: str
    instrument: str
    granularity: str
    candles: list[Candle]
    training_mode: bool
    current_index: int = WARMUP_BARS
    decisions: list[ReplayDecisionRecord] = field(default_factory=list)
    open_decision: ReplayDecisionRecord | None = None

    def visible_candles(self) -> list[Candle]:
        return self.candles[: self.current_index + 1]

    def visible_df(self) -> pd.DataFrame:
        visible = self.visible_candles()
        return pd.DataFrame(
            {
                "open_time": [c.open_time for c in visible],
                "open": [c.open for c in visible],
                "high": [c.high for c in visible],
                "low": [c.low for c in visible],
                "close": [c.close for c in visible],
            }
        )

    def is_at_end(self) -> bool:
        return self.current_index >= len(self.candles) - 1


_STORE: dict[str, ReplaySession] = {}


def create_session(instrument: str, granularity: str, candles: list[Candle], training_mode: bool) -> ReplaySession:
    session_id = str(uuid.uuid4())
    start_index = min(WARMUP_BARS, max(0, len(candles) - 2))
    session = ReplaySession(
        id=session_id,
        instrument=instrument,
        granularity=granularity,
        candles=candles,
        training_mode=training_mode,
        current_index=start_index,
    )
    _STORE[session_id] = session
    return session


def get_session(session_id: str) -> ReplaySession | None:
    return _STORE.get(session_id)


def step(session: ReplaySession) -> Candle | None:
    if session.is_at_end():
        return None
    session.current_index += 1
    new_candle = session.candles[session.current_index]
    if session.open_decision is not None:
        entry = session.open_decision.entry_price or new_candle.close
        direction = session.open_decision.action
        diff = (new_candle.close - entry) if direction == "BUY" else (entry - new_candle.close)
        session.open_decision.max_favorable = max(session.open_decision.max_favorable, diff)
        session.open_decision.max_adverse = min(session.open_decision.max_adverse, diff)
    return new_candle


def decide(session: ReplaySession, action: Decision) -> ReplayDecisionRecord:
    current_candle = session.candles[session.current_index]
    signal = evaluate(session.visible_df()) if action != "SKIP" or session.training_mode else None
    record = ReplayDecisionRecord(
        decided_at_index=session.current_index,
        action=action,
        entry_price=current_candle.close if action != "SKIP" else None,
        signal_at_decision=signal,
    )
    session.decisions.append(record)
    if action != "SKIP":
        session.open_decision = record
    return record


def close_open_decision(session: ReplaySession) -> ReplayDecisionRecord | None:
    if session.open_decision is None:
        return None
    current_candle = session.candles[session.current_index]
    record = session.open_decision
    record.exit_price = current_candle.close
    direction = record.action
    diff = (record.exit_price - record.entry_price) if direction == "BUY" else (record.entry_price - record.exit_price)
    record.pnl = diff
    session.open_decision = None
    return record
