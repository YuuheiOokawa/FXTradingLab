from __future__ import annotations

import logging

from app.brokers.base import BrokerAdapter
from app.brokers.mock import MockAdapter
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_instance: BrokerAdapter | None = None


def _build(settings: Settings) -> BrokerAdapter:
    if settings.broker_provider == "oanda":
        if not settings.oanda_api_token or not settings.oanda_account_id:
            logger.warning(
                "BROKER_PROVIDER=oanda but OANDA_API_TOKEN/OANDA_ACCOUNT_ID are not set; "
                "falling back to MockAdapter so the app remains usable."
            )
            return MockAdapter(poll_interval_ms=settings.poll_interval_ms)
        from app.brokers.oanda import OandaAdapter

        return OandaAdapter(
            api_token=settings.oanda_api_token,
            account_id=settings.oanda_account_id,
            environment=settings.oanda_environment,
        )
    if settings.broker_provider == "gmo_coin":
        if not settings.gmo_coin_api_key or not settings.gmo_coin_api_secret:
            logger.warning(
                "BROKER_PROVIDER=gmo_coin but credentials are not set; falling back to MockAdapter."
            )
            return MockAdapter(poll_interval_ms=settings.poll_interval_ms)
        from app.brokers.gmo_coin import GmoCoinAdapter

        return GmoCoinAdapter(api_key=settings.gmo_coin_api_key, api_secret=settings.gmo_coin_api_secret)
    return MockAdapter(poll_interval_ms=settings.poll_interval_ms)


def get_broker_adapter() -> BrokerAdapter:
    """Runtime broker selection (docs/06_BROKER_API_DESIGN.md). Cached as a
    process-wide singleton; call `reset_broker_adapter()` in tests that need a
    fresh instance."""
    global _instance
    if _instance is None:
        _instance = _build(get_settings())
    return _instance


def reset_broker_adapter() -> None:
    global _instance
    _instance = None
