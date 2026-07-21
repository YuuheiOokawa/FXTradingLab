"""LIVE order dry-run + broker preflight (docs/15_PRODUCTION_READINESS_REVIEW.md
"LIVE Trading Dry Run", "Broker Credential Validation") — both must be usable
without ever touching BrokerAdapter.create_order, and both must actually
reflect real Risk Engine / broker state, not a canned response."""
import uuid

import httpx
import pytest

from app.brokers.errors import BrokerConnectionError
from app.brokers.mock import MockAdapter
from app.brokers.schemas import OrderRequest, PriceQuote
from app.main import app
from app.services.order_orchestrator import OrderOrchestrator


class _NeverCalledCreateOrder(MockAdapter):
    """Fails the test immediately if anything calls create_order — the
    strongest possible assertion that preview_live_order structurally
    cannot place a real order, not just that it happened not to this run."""

    async def create_order(self, order):  # noqa: D102
        raise AssertionError("preview_live_order must NEVER call create_order")


def _order(**overrides) -> OrderRequest:
    defaults = dict(instrument="USD_JPY", direction="BUY", size=1000, idempotency_key=str(uuid.uuid4()))
    defaults.update(overrides)
    return OrderRequest(**defaults)


async def test_preview_never_calls_create_order(db_session):
    broker = _NeverCalledCreateOrder()
    orchestrator = OrderOrchestrator(broker)
    quote = await broker.get_current_price("USD_JPY")
    order = _order(stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3))
    await orchestrator.preview_live_order(db_session, order)  # would raise AssertionError if it ever called create_order


async def test_preview_reports_would_be_approved_for_a_compliant_order(db_session):
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)
    quote = await broker.get_current_price("USD_JPY")
    order = _order(stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3), size=1000)

    preview = await orchestrator.preview_live_order(db_session, order)
    assert preview["would_be_approved"] is True
    assert preview["reject_code"] is None
    assert preview["estimated_entry_price"] is not None
    assert preview["account_equity"] > 0


async def test_preview_reports_rejection_reason_for_an_oversized_order(db_session):
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)
    quote = await broker.get_current_price("USD_JPY")
    # A stop_loss far enough away combined with a huge size blows the
    # max-risk-per-trade-pct check for MockAdapter's default 1,000,000 balance.
    order = _order(stop_loss=round(quote.mid - 5.0, 3), size=10_000_000)

    preview = await orchestrator.preview_live_order(db_session, order)
    assert preview["would_be_approved"] is False
    assert preview["reject_code"] == "PER_TRADE_RISK_EXCEEDED"


async def test_preview_available_even_though_no_live_gate_is_satisfied(db_session):
    """The whole point: an operator can preview without LIVE_TRADING_ENABLED,
    without the admin toggle, and without confirm_live — this must not raise
    LiveTradingDisabled the way submit_live_order does."""
    from app.core.config import get_settings

    settings = get_settings()
    assert settings.live_trading_enabled is False  # sanity: gate 1 genuinely unsatisfied

    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)
    quote = await broker.get_current_price("USD_JPY")
    order = _order(stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3))

    preview = await orchestrator.preview_live_order(db_session, order)  # must not raise
    assert preview["live_gates_satisfied"] is False


async def test_preview_reports_broker_disconnected_without_raising(db_session, monkeypatch):
    broker = MockAdapter()

    async def _boom(*a, **kw):
        raise BrokerConnectionError("simulated outage")

    monkeypatch.setattr(broker, "get_account", _boom)
    orchestrator = OrderOrchestrator(broker)
    order = _order(stop_loss=150.0, take_profit=160.0)

    preview = await orchestrator.preview_live_order(db_session, order)
    assert preview["broker_connected"] is False
    assert preview["would_be_approved"] is False
    assert preview["reject_code"] == "BROKER_DISCONNECTED"
    assert preview["broker_error"] is not None


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_preview_route_never_reaches_a_real_order(client):
    resp = await client.post(
        "/api/v1/live/orders/preview",
        json={"instrument": "USD_JPY", "direction": "BUY", "size": 1000, "stop_loss": 150.0, "take_profit": 160.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "would_be_approved" in body
    assert "reject_code" in body


async def test_preflight_route_reports_account_and_instrument_checks(client):
    resp = await client.get("/api/v1/live/preflight")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["checks"]["authentication_and_account"]["ok"] is True
    assert body["all_ok"] is True
    assert "USD_JPY" in body["checks"]["instruments"]
    assert body["checks"]["instruments"]["USD_JPY"]["ok"] is True


async def test_preflight_reports_per_check_failure_independently(monkeypatch):
    """A broken instrument feed must not hide behind an unrelated account
    failure or vice versa — each check's result is independent."""
    from app.api import deps

    class _PartiallyBrokenBroker(MockAdapter):
        async def get_current_price(self, instrument: str) -> PriceQuote:
            if instrument == "EUR_JPY":
                raise BrokerConnectionError("EUR_JPY feed down")
            return await super().get_current_price(instrument)

    broken = _PartiallyBrokenBroker()
    app.dependency_overrides[deps.get_live_trading_broker] = lambda: broken
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/live/preflight")
        body = resp.json()
        assert body["checks"]["authentication_and_account"]["ok"] is True
        assert body["checks"]["instruments"]["USD_JPY"]["ok"] is True
        assert body["checks"]["instruments"]["EUR_JPY"]["ok"] is False
        assert body["all_ok"] is False
    finally:
        app.dependency_overrides.pop(deps.get_live_trading_broker, None)
