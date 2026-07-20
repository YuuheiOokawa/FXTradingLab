"""Rate limiting on /api/v1/* (docs/11_SECURITY.md "Rate limiting",
docs/15_PRODUCTION_READINESS_REVIEW.md "no rate limiting" gap)."""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.rate_limit import rate_limit
from app.core.config import get_settings
from app.core.redis_client import get_redis


def _fake_request(client_host: str = "127.0.0.1") -> MagicMock:
    request = MagicMock()
    request.client.host = client_host
    return request


@pytest.fixture(autouse=True)
async def _clear_rate_limit_keys():
    yield
    redis_client = get_redis()
    async for key in redis_client.scan_iter("ratelimit:*"):
        await redis_client.delete(key)


async def test_skipped_entirely_in_development():
    assert get_settings().app_env == "development"
    for _ in range(500):
        await rate_limit(_fake_request(), authorization="Bearer whatever", settings=get_settings())


async def test_allows_requests_under_the_limit(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 5)
    try:
        for _ in range(5):
            await rate_limit(_fake_request(), authorization="Bearer test-token-a", settings=get_settings())
    finally:
        monkeypatch.setattr(settings, "app_env", "development")


async def test_rejects_once_the_limit_is_exceeded(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 3)
    try:
        for _ in range(3):
            await rate_limit(_fake_request(), authorization="Bearer test-token-b", settings=get_settings())
        with pytest.raises(HTTPException) as exc_info:
            await rate_limit(_fake_request(), authorization="Bearer test-token-b", settings=get_settings())
        assert exc_info.value.status_code == 429
    finally:
        monkeypatch.setattr(settings, "app_env", "development")


async def test_buckets_are_isolated_per_token(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    try:
        for _ in range(2):
            await rate_limit(_fake_request(), authorization="Bearer token-c", settings=get_settings())
        # A different identity's bucket is unaffected by token-c's usage.
        for _ in range(2):
            await rate_limit(_fake_request(), authorization="Bearer token-d", settings=get_settings())
        with pytest.raises(HTTPException):
            await rate_limit(_fake_request(), authorization="Bearer token-c", settings=get_settings())
    finally:
        monkeypatch.setattr(settings, "app_env", "development")


async def test_falls_back_to_client_ip_when_no_token_present(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    try:
        for _ in range(2):
            await rate_limit(_fake_request("10.0.0.5"), authorization=None, settings=get_settings())
        with pytest.raises(HTTPException):
            await rate_limit(_fake_request("10.0.0.5"), authorization=None, settings=get_settings())
    finally:
        monkeypatch.setattr(settings, "app_env", "development")
