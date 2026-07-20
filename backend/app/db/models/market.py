from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base
from app.db.types import GUID


class Instrument(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # e.g. USD_JPY
    display_name: Mapped[str] = mapped_column(String(50))
    pip_size: Mapped[float] = mapped_column(Float, default=0.01)
    price_precision: Mapped[int] = mapped_column(Integer, default=3)
    margin_rate: Mapped[float] = mapped_column(Float, default=0.04)
    is_watched: Mapped[bool] = mapped_column(Boolean, default=True)


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("instrument_id", "granularity", "open_time", name="uq_candle_bucket"),
        Index("ix_candle_lookup", "instrument_id", "granularity", "open_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    granularity: Mapped[str] = mapped_column(String(5))  # M1, M5, M15, H1, H4, D
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    is_final: Mapped[bool] = mapped_column(Boolean, default=True)

    instrument: Mapped["Instrument"] = relationship()


class MarketTick(Base):
    """Down-sampled raw ticks, short retention (docs/04_DATABASE_DESIGN.md)."""

    __tablename__ = "market_ticks"
    __table_args__ = (Index("ix_tick_lookup", "instrument_id", "ts"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bid: Mapped[float] = mapped_column(Float)
    ask: Mapped[float] = mapped_column(Float)
