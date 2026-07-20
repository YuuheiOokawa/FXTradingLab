from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base
from app.db.types import GUID, PortableJSON


class Backtest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "backtests"

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    strategy_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategy_configs.id"))
    config: Mapped[dict] = mapped_column(PortableJSON)
    status: Mapped[str] = mapped_column(String(20), default="completed")  # queued|running|completed|failed
    summary: Mapped[dict] = mapped_column(PortableJSON, default=dict)  # overall/in-sample/out-of-sample stats
    equity_curve: Mapped[list] = mapped_column(PortableJSON, default=list)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    backtest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtests.id"))
    segment: Mapped[str] = mapped_column(String(15), default="in_sample")  # in_sample|out_of_sample
    direction: Mapped[str] = mapped_column(String(10))
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    entry_reasons: Mapped[list] = mapped_column(PortableJSON, default=list)
    exit_reason: Mapped[str] = mapped_column(String(200), default="")


class PaperAccount(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "paper_accounts"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    balance: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    high_water_mark: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    currency: Mapped[str] = mapped_column(String(5), default="JPY")


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_accounts.id"))
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    direction: Mapped[str] = mapped_column(String(10))
    size: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open|closed
    # Links back to the PaperOrder that opened this position, so an idempotent
    # replay of that order can look the position up exactly rather than by
    # matching independently-generated timestamps (which don't reliably line up).
    opening_idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_paper_order_idem"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_accounts.id"))
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    direction: Mapped[str] = mapped_column(String(10))
    size: Mapped[float] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(10), default="market")
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="filled")  # filled|rejected
    reject_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LiveOrder(Base):
    __tablename__ = "live_orders"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_live_order_idem"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("broker_accounts.id"))
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    direction: Mapped[str] = mapped_column(String(10))
    size: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="pending")
    reject_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LivePosition(Base):
    __tablename__ = "live_positions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("broker_accounts.id"))
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    broker_trade_id: Mapped[str] = mapped_column(String(100))
    direction: Mapped[str] = mapped_column(String(10))
    size: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")
