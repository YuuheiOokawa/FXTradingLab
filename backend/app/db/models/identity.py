from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class User(UUIDPKMixin, TimestampMixin, Base):
    """Single-operator today; kept normalized for future multi-user support."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100), default="Operator")


class BrokerAccount(UUIDPKMixin, TimestampMixin, Base):
    """One row per configured broker connection. Never stores the secret token —
    that lives only in environment variables (see docs/11_SECURITY.md)."""

    __tablename__ = "broker_accounts"

    provider: Mapped[str] = mapped_column(String(30))  # mock | oanda | gmo_coin
    environment: Mapped[str] = mapped_column(String(20))  # practice | live
    masked_account_id: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
