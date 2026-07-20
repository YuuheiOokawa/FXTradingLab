"""BrokerAdapter split (docs/15_PRODUCTION_READINESS_REVIEW.md): market data and
trading can be configured to independent providers. Default (no override) must
keep behaving exactly as a single-provider setup."""
from app.brokers.factory import get_market_data_provider, get_trading_broker, reset_broker_adapter
from app.brokers.mock import MockAdapter
from app.core.config import get_settings


def _reset():
    reset_broker_adapter()


async def test_defaults_to_same_provider_for_both_roles():
    _reset()
    settings = get_settings()
    assert settings.market_data_provider is None
    market_data = get_market_data_provider()
    trading = get_trading_broker()
    assert isinstance(market_data, MockAdapter)
    assert isinstance(trading, MockAdapter)
    _reset()


async def test_market_data_provider_override_takes_effect(monkeypatch):
    _reset()
    settings = get_settings()
    monkeypatch.setattr(settings, "market_data_provider", "mock")
    monkeypatch.setattr(settings, "broker_provider", "mock")
    try:
        market_data = get_market_data_provider()
        trading = get_trading_broker()
        assert market_data.provider == "mock"
        assert trading.provider == "mock"
    finally:
        monkeypatch.setattr(settings, "market_data_provider", None)
        _reset()


async def test_oanda_without_credentials_falls_back_to_mock_for_both_roles(monkeypatch):
    _reset()
    settings = get_settings()
    monkeypatch.setattr(settings, "broker_provider", "oanda")
    monkeypatch.setattr(settings, "oanda_api_token", None)
    try:
        assert get_trading_broker().provider == "mock"
        assert get_market_data_provider().provider == "mock"
    finally:
        monkeypatch.setattr(settings, "broker_provider", "mock")
        _reset()
