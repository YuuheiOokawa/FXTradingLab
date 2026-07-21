from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base
from app.db.types import GUID, PortableJSON


class TradeJournal(Base):
    """Denormalized analytics read-model for every closed trade regardless of
    source (backtest/paper/demo/live). See docs/04_DATABASE_DESIGN.md."""

    __tablename__ = "trade_journals"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(10))  # backtest|paper|demo|live
    source_ref_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    pair: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_price: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(500), default="")
    signal_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiskSettings(UUIDPKMixin, TimestampMixin, Base):
    """Singleton-per-operator row (docs/10_RISK_MANAGEMENT.md)."""

    __tablename__ = "risk_settings"

    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=1.0)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=3.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_concurrent_positions: Mapped[int] = mapped_column(Integer, default=3)
    max_same_symbol_positions: Mapped[int] = mapped_column(Integer, default=1)
    consecutive_loss_stop_count: Mapped[int] = mapped_column(Integer, default=4)
    max_spread_pips_default: Mapped[float] = mapped_column(Float, default=3.0)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, default=False)
    live_trading_admin_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_mode: Mapped[str] = mapped_column(String(15), default="manual")  # manual|semi_auto|full_auto


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category: Mapped[str] = mapped_column(String(30))  # broker|price_feed|risk|kill_switch|order|db
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info|warning|error
    message: Mapped[str] = mapped_column(String(500))
    context: Mapped[dict] = mapped_column(PortableJSON, default=dict)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String(15), default="in_app")  # in_app|discord|line|email
    kind: Mapped[str] = mapped_column(String(30))  # strong_buy|strong_sell|sl_hit|tp_hit|daily_loss|disconnect|spread
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(1000), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    """Deliberately separate from SystemEvent (docs/15_PRODUCTION_READINESS_
    REVIEW.md "Audit Log"): SystemEvent is free-form operational logging
    (broker hiccups, price-quality rejections); this table is only for the
    specific named sensitive actions an operator or reviewer would want a
    reliable "who/when/what/before/after" trail for — login/logout, kill
    switch, risk-setting changes, LIVE trading enablement, and every LIVE
    order lifecycle step (preview/submit/reject/result). `before`/`after`
    hold field-level diffs where applicable (e.g. a risk setting change);
    `context` holds action-specific detail. Never store a secret/token
    value in any of these three JSON columns — see `write_audit_log()`."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Always "operator" today (single-operator app, docs/01_REQUIREMENTS.md) —
    # the column exists so a future multi-user build doesn't need a migration.
    actor: Mapped[str] = mapped_column(String(50), default="operator")
    action: Mapped[str] = mapped_column(String(50))
    # login|logout|kill_switch_on|kill_switch_off|risk_setting_change|
    # live_trading_admin_enable|live_trading_admin_disable|live_order_preview|
    # live_order_submit|live_order_reject|live_order_result
    before: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    context: Mapped[dict] = mapped_column(PortableJSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
