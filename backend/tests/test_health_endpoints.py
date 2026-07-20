"""docs/15_PRODUCTION_READINESS_REVIEW.md "Observability": /health, /ready,
/metrics, and request-id correlation."""
import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
    # No lifespan manager needed: /health, /ready, /metrics only touch
    # module-level singletons (get_settings/get_redis/AsyncSessionLocal) that
    # don't depend on FastAPI startup/shutdown events having fired.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_is_always_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_reports_per_dependency_status(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["checks"]["database"] is True
    assert body["checks"]["redis"] is True
    assert "market_data_broker" in body["checks"]


async def test_metrics_reports_uptime_and_watchlist(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["uptime_seconds"] >= 0
    assert "USD_JPY" in body["instruments"]


async def test_request_id_header_is_always_present_and_unique(client):
    resp1 = await client.get("/health")
    resp2 = await client.get("/health")
    id1 = resp1.headers.get("x-request-id")
    id2 = resp2.headers.get("x-request-id")
    assert id1 and id2
    assert id1 != id2


async def test_inbound_request_id_is_echoed_back(client):
    resp = await client.get("/health", headers={"X-Request-ID": "test-fixed-id-123"})
    assert resp.headers.get("x-request-id") == "test-fixed-id-123"
