"""WebSocket auth (docs/11_SECURITY.md "BFF migration"): `/ws/prices` and
`/ws/system` require a short-lived, single-use ticket minted by
`POST /api/v1/system/ws-ticket` (itself behind the normal REST bearer auth),
passed as a `?ticket=` query param since browsers can't set a WS handshake
header. Outside development, the handshake's Origin header is also checked
against ALLOWED_ORIGINS."""
from unittest.mock import MagicMock

from app.core.config import get_settings
from app.ws.auth import check_ws_auth
from app.ws.tickets import consume_ticket, mint_ticket


def _fake_ws(ticket: str | None = None, origin: str | None = None) -> MagicMock:
    ws = MagicMock()
    ws.query_params = {"ticket": ticket} if ticket is not None else {}
    ws.headers = {"origin": origin} if origin is not None else {}
    return ws


async def test_dev_environment_never_requires_a_ticket():
    assert get_settings().app_env == "development"
    assert await check_ws_auth(_fake_ws()) is True


async def test_non_dev_rejects_missing_or_wrong_ticket(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    try:
        assert await check_ws_auth(_fake_ws(None)) is False
        assert await check_ws_auth(_fake_ws("not-a-real-ticket")) is False
    finally:
        monkeypatch.setattr(settings, "app_env", "development")


async def test_non_dev_accepts_a_freshly_minted_ticket(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    try:
        ticket = await mint_ticket()
        assert await check_ws_auth(_fake_ws(ticket)) is True
    finally:
        monkeypatch.setattr(settings, "app_env", "development")


async def test_a_ticket_can_only_be_used_once(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    try:
        ticket = await mint_ticket()
        assert await check_ws_auth(_fake_ws(ticket)) is True
        assert await check_ws_auth(_fake_ws(ticket)) is False
    finally:
        monkeypatch.setattr(settings, "app_env", "development")


async def test_non_dev_rejects_a_disallowed_origin_even_with_a_valid_ticket(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "allowed_origins", "https://fxlab.example.com")
    try:
        ticket = await mint_ticket()
        assert await check_ws_auth(_fake_ws(ticket, origin="https://evil.example.com")) is False
    finally:
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "allowed_origins", "")


async def test_non_dev_accepts_an_allowed_origin_with_a_valid_ticket(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "allowed_origins", "https://fxlab.example.com")
    try:
        ticket = await mint_ticket()
        assert await check_ws_auth(_fake_ws(ticket, origin="https://fxlab.example.com")) is True
    finally:
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "allowed_origins", "")


async def test_consume_ticket_rejects_none_and_empty_string():
    assert await consume_ticket(None) is False
    assert await consume_ticket("") is False
