"""Startup guards in app.main's lifespan (docs/15_PRODUCTION_READINESS_REVIEW.md
"Staging environment"): the app must refuse to boot rather than come up in an
unsafe configuration — no auth in a real environment, or LIVE trading enabled
in staging (which exists specifically to test against real market data using
Paper/Practice execution only, never a real order)."""
import pytest

from app.core.config import get_settings
from app.main import app, lifespan


@pytest.fixture(autouse=True)
def _restore_settings():
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "app_api_token": settings.app_api_token,
        "live_trading_enabled": settings.live_trading_enabled,
        "allowed_origins": settings.allowed_origins,
    }
    yield
    for key, value in original.items():
        object.__setattr__(settings, key, value)


async def test_staging_without_app_api_token_refuses_to_boot(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "app_api_token", None)
    with pytest.raises(RuntimeError, match="APP_API_TOKEN must be set"):
        async with lifespan(app):
            pass


async def test_production_without_app_api_token_refuses_to_boot(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "app_api_token", None)
    with pytest.raises(RuntimeError, match="APP_API_TOKEN must be set"):
        async with lifespan(app):
            pass


async def test_staging_with_live_trading_enabled_refuses_to_boot(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "app_api_token", "some-token")
    monkeypatch.setattr(settings, "live_trading_enabled", True)
    monkeypatch.setattr(settings, "allowed_origins", "https://staging.example.com")
    with pytest.raises(RuntimeError, match="LIVE_TRADING_ENABLED must never be true in a staging"):
        async with lifespan(app):
            pass


async def test_production_with_live_trading_enabled_is_allowed_to_boot(monkeypatch):
    """LIVE trading in production is gated by three separate conditions
    (docs/10_RISK_MANAGEMENT.md) — this env var alone is not supposed to be
    sufficient, so booting with it true must not be blocked the way staging
    is (staging has no legitimate reason for it ever to be true; production
    does, once an operator deliberately clears every gate)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "app_api_token", "some-token")
    monkeypatch.setattr(settings, "live_trading_enabled", True)
    monkeypatch.setattr(settings, "allowed_origins", "https://fxlab.example.com")
    async with lifespan(app):
        pass


async def test_staging_with_valid_config_boots_cleanly(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "app_api_token", "some-token")
    monkeypatch.setattr(settings, "live_trading_enabled", False)
    monkeypatch.setattr(settings, "allowed_origins", "https://staging.example.com")
    async with lifespan(app):
        pass
