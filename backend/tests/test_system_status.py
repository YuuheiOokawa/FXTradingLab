"""GET /api/v1/system/status observability fields
(docs/02_SYSTEM_ARCHITECTURE.md "Observability")."""
import httpx
import pytest

from app.core.redis_client import get_redis
from app.main import app
from app.worker.jobs import heartbeat
from app.ws import registry as ws_registry


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def _reset_ws_registry():
    yield
    while ws_registry.current_count() > 0:
        ws_registry.decrement()


async def test_reports_worker_dead_when_no_heartbeat(client):
    redis = get_redis()
    await redis.delete(heartbeat.HEARTBEAT_KEY)

    resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["worker_alive"] is False


async def test_reports_worker_alive_after_heartbeat_job_runs(client):
    await heartbeat.run()

    resp = await client.get("/api/v1/system/status")
    body = resp.json()
    assert body["worker_alive"] is True


async def test_reports_database_and_redis_connected(client):
    resp = await client.get("/api/v1/system/status")
    body = resp.json()
    assert body["database_connected"] is True
    assert body["redis_connected"] is True


async def test_reports_websocket_client_count(client):
    ws_registry.increment()
    ws_registry.increment()

    resp = await client.get("/api/v1/system/status")
    body = resp.json()
    assert body["websocket_client_count"] == 2

    ws_registry.decrement()
    resp2 = await client.get("/api/v1/system/status")
    assert resp2.json()["websocket_client_count"] == 1


async def test_last_signal_generated_reflects_the_most_recent_signal(client, db_session):
    resp_before = await client.get("/api/v1/system/status")
    assert resp_before.json()["last_signal_generated"] is None

    from datetime import UTC, datetime

    from app.db.models.strategy import Signal
    from app.services.market_data import ensure_instruments

    instruments = await ensure_instruments(["USD_JPY"])
    db_session.add(
        Signal(
            instrument_id=instruments["USD_JPY"].id,
            granularity="M15",
            ts=datetime.now(UTC),
            direction="BUY",
            score=85,
            label="強い買い",
            regime_trend="UPTREND",
            regime_volatility="NORMAL",
            reasons=[],
            entry_price=150.0,
        )
    )
    await db_session.commit()

    resp_after = await client.get("/api/v1/system/status")
    body = resp_after.json()
    assert body["last_signal_generated"] is not None
    assert body["last_signal_generated"]["score"] == 85
