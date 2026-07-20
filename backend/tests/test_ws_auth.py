"""WebSocket auth (docs/15_PRODUCTION_READINESS_REVIEW.md "Security"):
`/ws/prices` and `/ws/system` must require the same bearer token as REST does
outside development, passed as a `?token=` query param since browsers can't
set a WS handshake header."""
from unittest.mock import MagicMock

from app.core.config import get_settings
from app.ws.auth import check_ws_auth


def _fake_ws(token: str | None) -> MagicMock:
    ws = MagicMock()
    ws.query_params = {"token": token} if token is not None else {}
    return ws


async def test_dev_environment_never_requires_a_token():
    assert get_settings().app_env == "development"
    assert await check_ws_auth(_fake_ws(None)) is True


async def test_non_dev_without_configured_token_always_rejects(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "app_api_token", None)
    try:
        assert await check_ws_auth(_fake_ws("anything")) is False
    finally:
        monkeypatch.setattr(settings, "app_env", "development")


async def test_non_dev_rejects_missing_or_wrong_token(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "app_api_token", "secret-123")
    try:
        assert await check_ws_auth(_fake_ws(None)) is False
        assert await check_ws_auth(_fake_ws("wrong-token")) is False
        assert await check_ws_auth(_fake_ws("secret-123")) is True
    finally:
        monkeypatch.setattr(settings, "app_env", "development")
