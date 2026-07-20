"""Replay session persistence (docs/01_REQUIREMENTS.md FR-9,
docs/15_PRODUCTION_READINESS_REVIEW.md "Replay"). Previously in-process-
memory only — a server restart silently lost every in-progress session, and
there was no record of past sessions to review later. `candles` is stored as
a JSON snapshot of exactly what `broker.get_candles()` returned at session
creation, not re-fetched later — this is deliberate: a replay session's
candle set must never change out from under it (see
`app/services/replay.py`'s no-future-leak invariant), and re-fetching later
against a live/mock feed could return a different window.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base
from app.db.types import GUID, PortableJSON


class ReplaySession(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "replay_sessions"
    __table_args__ = (Index("ix_replay_session_status", "status"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    granularity: Mapped[str] = mapped_column(String(5))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # open_time of candles[0]
    current_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # open_time of the current index's candle
    speed: Mapped[float] = mapped_column(Float, default=1.0)  # playback speed multiplier (UI concept, persisted for resume)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | finished
    initial_balance: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    current_balance: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    training_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    current_index: Mapped[int] = mapped_column(Integer)
    candles: Mapped[list] = mapped_column(PortableJSON)  # fixed snapshot, see module docstring

    trades: Mapped[list["ReplayTrade"]] = relationship(back_populates="session", order_by="ReplayTrade.decided_at_index")


class ReplayTrade(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "replay_trades"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("replay_sessions.id"))
    decided_at_index: Mapped[int] = mapped_column(Integer)
    decided_at_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[str] = mapped_column(String(10))  # BUY | SELL | SKIP
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_favorable: Mapped[float] = mapped_column(Float, default=0.0)
    max_adverse: Mapped[float] = mapped_column(Float, default=0.0)
    signal_snapshot: Mapped[dict] = mapped_column(PortableJSON, default=dict)  # score/direction/label/regime/reasons at decision time

    # Qualitative judgment (docs/01_REQUIREMENTS.md FR-9, explicitly NOT
    # profit/loss-based alone) — see app/services/replay_judgment.py.
    judgment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # good | neutral | risky
    judgment_criteria: Mapped[list] = mapped_column(PortableJSON, default=list)  # [{criterion, verdict, note}, ...]

    session: Mapped["ReplaySession"] = relationship(back_populates="trades")
