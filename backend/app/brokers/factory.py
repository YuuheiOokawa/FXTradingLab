from __future__ import annotations

import logging

from app.brokers.base import BrokerAdapter
from app.brokers.mock import MockAdapter
from app.core.config import BrokerProvider, Settings, get_settings

logger = logging.getLogger(__name__)

_market_data_instance: BrokerAdapter | None = None
_trading_instance: BrokerAdapter | None = None


def _build(provider: BrokerProvider, settings: Settings) -> BrokerAdapter:
    if provider == "oanda":
        if not settings.oanda_api_token or not settings.oanda_account_id:
            logger.warning(
                "provider=oanda but OANDA_API_TOKEN/OANDA_ACCOUNT_ID are not set; "
                "falling back to MockAdapter so the app remains usable."
            )
            return MockAdapter(poll_interval_ms=settings.poll_interval_ms)
        from app.brokers.oanda import OandaAdapter

        return OandaAdapter(
            api_token=settings.oanda_api_token,
            account_id=settings.oanda_account_id,
            environment=settings.oanda_environment,
        )
    if provider == "yahoo":
        from app.brokers.yahoo import YahooMarketDataAdapter

        return YahooMarketDataAdapter(poll_interval_ms=settings.poll_interval_ms)
    if provider == "gmo_coin":
        if not settings.gmo_coin_api_key or not settings.gmo_coin_api_secret:
            logger.warning("provider=gmo_coin but credentials are not set; falling back to MockAdapter.")
            return MockAdapter(poll_interval_ms=settings.poll_interval_ms)
        from app.brokers.gmo_coin import GmoCoinAdapter

        return GmoCoinAdapter(api_key=settings.gmo_coin_api_key, api_secret=settings.gmo_coin_api_secret)
    return MockAdapter(poll_interval_ms=settings.poll_interval_ms)


def get_market_data_provider() -> BrokerAdapter:
    """Where prices/candles come from (docs/15_PRODUCTION_READINESS_REVIEW.md
    "BrokerAdapter split"). Defaults to `BROKER_PROVIDER`; set
    `MARKET_DATA_PROVIDER` to use a different source than the trading broker.
    Cached as a process-wide singleton; call `reset_broker_adapter()` in tests."""
    global _market_data_instance
    if _market_data_instance is None:
        settings = get_settings()
        provider = settings.market_data_provider or settings.broker_provider
        _market_data_instance = _build(provider, settings)
        _warn_if_split(settings)
    return _market_data_instance


# Providers that can serve prices but can never execute an order. Setting one of
# these as BROKER_PROVIDER is a configuration mistake that would otherwise only
# surface at the moment an order is attempted.
MARKET_DATA_ONLY_PROVIDERS = frozenset({"yahoo"})


def get_trading_broker() -> BrokerAdapter:
    """Where orders actually get sent (docs/10_RISK_MANAGEMENT.md,
    docs/15_PRODUCTION_READINESS_REVIEW.md). Always `BROKER_PROVIDER` — trading
    is never implicitly redirected to a different provider than configured."""
    global _trading_instance
    if _trading_instance is None:
        settings = get_settings()
        if settings.broker_provider in MARKET_DATA_ONLY_PROVIDERS:
            raise ValueError(
                f"BROKER_PROVIDER={settings.broker_provider!r} is a market-data-only source and "
                "cannot execute orders. Set MARKET_DATA_PROVIDER to it instead, and leave "
                "BROKER_PROVIDER as a real broker (or 'mock' for paper trading)."
            )
        _trading_instance = _build(settings.broker_provider, settings)
        _warn_if_split(settings)
    return _trading_instance


def _warn_if_split(settings: Settings) -> None:
    market_data = settings.market_data_provider or settings.broker_provider
    if market_data != settings.broker_provider:
        logger.warning(
            "MARKET_DATA_PROVIDER (%s) differs from BROKER_PROVIDER (%s): prices shown to the "
            "user/signal engine come from a different source than the broker orders will fill "
            "at. This risks spread/latency skew between what's displayed and what's tradeable, "
            "and instrument symbols may not map 1:1 across providers — verify symbol mapping "
            "explicitly before relying on this in any mode beyond BACKTEST/PAPER "
            "(docs/15_PRODUCTION_READINESS_REVIEW.md).",
            market_data,
            settings.broker_provider,
        )


def get_broker_adapter() -> BrokerAdapter:
    """Backward-compatible alias for `get_trading_broker()` — most existing call
    sites (worker's FULL_AUTO paper-trading loop, API route dependencies) only
    ever dealt with one provider before the market-data/trading split existed.
    New code should call `get_market_data_provider()` or `get_trading_broker()`
    explicitly instead of this alias."""
    return get_trading_broker()


def reset_broker_adapter() -> None:
    global _market_data_instance, _trading_instance
    _market_data_instance = None
    _trading_instance = None
