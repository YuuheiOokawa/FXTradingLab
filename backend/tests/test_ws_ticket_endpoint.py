"""POST /api/v1/system/ws-ticket (docs/11_SECURITY.md "BFF migration") —
gated by the same require_auth bearer dependency as every other /api/v1/*
route; mints a ticket app/ws/auth.py's check_ws_auth will accept exactly
once."""
import httpx
import pytest

from app.main import app
from app.ws.auth import check_ws_auth
from unittest.mock import MagicMock


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _fake_ws(ticket: str) -> MagicMock:
    ws = MagicMock()
    ws.query_params = {"ticket": ticket}
    ws.headers = {}
    return ws


async def test_issues_a_ticket_with_expiry(client):
    resp = await client.post("/api/v1/system/ws-ticket")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["ticket"], str) and len(body["ticket"]) > 20
    assert body["expires_in"] > 0


async def test_issued_ticket_is_actually_usable_for_ws_auth(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "app_api_token", "test-token-123")
    try:
        resp = await client.post(
            "/api/v1/system/ws-ticket", headers={"Authorization": "Bearer test-token-123"}
        )
        assert resp.status_code == 200
        ticket = resp.json()["ticket"]
        assert await check_ws_auth(_fake_ws(ticket)) is True
        # And, being single-use, a second attempt with the same ticket fails.
        assert await check_ws_auth(_fake_ws(ticket)) is False
    finally:
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "app_api_token", None)


async def test_each_call_mints_a_distinct_ticket(client):
    resp1 = await client.post("/api/v1/system/ws-ticket")
    resp2 = await client.post("/api/v1/system/ws-ticket")
    assert resp1.json()["ticket"] != resp2.json()["ticket"]
