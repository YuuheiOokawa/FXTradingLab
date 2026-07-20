from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.brokers.base import BrokerAdapter
from app.brokers.factory import get_market_data_provider, get_trading_broker
from app.core.config import Settings, get_settings
from app.db.session import get_db  # re-exported for convenience

__all__ = ["get_db", "get_broker", "get_market_data_broker", "get_live_trading_broker", "require_auth", "get_app_settings"]


def get_app_settings() -> Settings:
    return get_settings()


def get_market_data_broker() -> BrokerAdapter:
    """Price reads (candles, current price, signal evaluation) — see
    docs/15_PRODUCTION_READINESS_REVIEW.md "BrokerAdapter split"."""
    return get_market_data_provider()


def get_live_trading_broker() -> BrokerAdapter:
    """Where LIVE orders actually get submitted — always `BROKER_PROVIDER`,
    never implicitly redirected."""
    return get_trading_broker()


def get_broker() -> BrokerAdapter:
    """Back-compat alias — existing routes (market/signals/backtest/paper/
    simulate/replay data reads) use this for price reads, which is exactly
    what `get_market_data_broker()` does; `live.py` uses the explicit
    `get_live_trading_broker()` dependency instead since it must never
    silently follow a market-data-only override."""
    return get_market_data_provider()


async def require_auth(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
) -> None:
    """Bearer-token auth for /api/v1/* (docs/11_SECURITY.md). Skipped in
    development for convenience; every other environment requires it."""
    if not settings.auth_required:
        return
    if not settings.app_api_token:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "APP_API_TOKEN is not configured but auth is required in this environment.",
        )
    expected = f"Bearer {settings.app_api_token}"
    if authorization != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing bearer token")
