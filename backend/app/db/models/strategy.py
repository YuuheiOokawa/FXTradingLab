from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base
from app.db.types import GUID, PortableJSON


class Strategy(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "strategies"

    code: Mapped[str] = mapped_column(String(50), unique=True)  # e.g. "trend_follow_v1"
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")


class StrategyConfig(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "strategy_configs"

    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"))
    name: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict] = mapped_column(PortableJSON, default=dict)

    strategy: Mapped["Strategy"] = relationship()


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        # One captured signal per (instrument, granularity, candle) — the
        # natural dedup key for app/worker/jobs/signal_capture.py running
        # repeatedly against the same recent candles.
        UniqueConstraint("instrument_id", "granularity", "ts", name="uq_signal_instrument_granularity_ts"),
        Index("ix_signal_outcome_pending", "outcome_computed_at", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    strategy_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_configs.id"), nullable=True
    )
    granularity: Mapped[str] = mapped_column(String(5))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    direction: Mapped[str] = mapped_column(String(10))  # BUY | SELL
    score: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(20))
    regime_trend: Mapped[str] = mapped_column(String(20))
    regime_volatility: Mapped[str] = mapped_column(String(20))
    reasons: Mapped[list] = mapped_column(PortableJSON, default=list)

    # Outcome tracking (docs/08_SIGNAL_ENGINE.md "Signal outcome history"),
    # populated by app/worker/jobs/signal_outcome.py once
    # OUTCOME_HORIZON_MINUTES has actually elapsed after `ts` and enough
    # candle history exists to cover the full window — all null until then.
    entry_price: Mapped[float] = mapped_column(Float)
    outcome_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_favorable_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_adverse_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_horizon_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp_reached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sl_reached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
