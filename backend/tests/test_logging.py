"""Structured logging fields (docs/15_PRODUCTION_READINESS_REVIEW.md
"Observability"): timestamp/level/service/event/symbol/request_id/order_id,
and secret redaction. `order_id` was previously always None in practice —
`set_order_id()` existed but nothing ever called it — found and fixed via
`app.core.request_context.order_context`, used at every order-processing
call site (paper.py, live.py, auto_trader.py)."""
import json
import logging

from app.core.logging import JSONFormatter, RedactSecretsFilter
from app.core.request_context import get_order_id, order_context, set_request_id


def _make_record(msg: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.services.order_orchestrator",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


def test_json_formatter_includes_every_requested_field():
    record = _make_record(
        "paper order filled",
        symbol="USD_JPY",
        request_id="req-123",
        order_id="order-456",
    )
    payload = json.loads(JSONFormatter().format(record))

    assert "timestamp" in payload
    assert payload["level"] == "INFO"
    assert "service" in payload
    assert payload["event"] == "app.services.order_orchestrator"
    assert payload["symbol"] == "USD_JPY"
    assert payload["request_id"] == "req-123"
    assert payload["order_id"] == "order-456"


def test_json_formatter_defaults_missing_correlation_fields_to_null():
    record = _make_record("no correlation ids set")
    payload = json.loads(JSONFormatter().format(record))
    assert payload["symbol"] is None
    assert payload["request_id"] is None
    assert payload["order_id"] is None


def test_order_context_sets_and_restores_order_id():
    assert get_order_id() is None
    with order_context("order-abc"):
        assert get_order_id() == "order-abc"
    assert get_order_id() is None


def test_order_context_restores_outer_value_not_just_none():
    set_request_id(None)  # unrelated, just resetting state defensively
    with order_context("outer-order"):
        assert get_order_id() == "outer-order"
        with order_context("inner-order"):
            assert get_order_id() == "inner-order"
        assert get_order_id() == "outer-order"
    assert get_order_id() is None


def test_secret_redaction_still_applies_alongside_correlation_fields():
    record = _make_record("Authorization: Bearer supersecrettoken123", symbol="USD_JPY")
    RedactSecretsFilter().filter(record)
    assert "supersecrettoken123" not in record.getMessage()
    assert "REDACTED" in record.getMessage()


async def test_submit_paper_order_route_actually_populates_order_id(db_session, monkeypatch):
    """Not just that order_context works in isolation - that POST
    /paper/orders actually wraps the call with it, so every log line
    app/services/order_orchestrator.py emits mid-request carries the real
    idempotency key."""
    import httpx

    from app.main import app
    from app.services import order_orchestrator as orch_module
    from app.services.market_data import ensure_instruments

    await ensure_instruments(["USD_JPY"])
    seen_order_id = None
    real_submit = orch_module.OrderOrchestrator.submit_paper_order

    async def spying_submit(self, session, order):
        nonlocal seen_order_id
        seen_order_id = get_order_id()
        return await real_submit(self, session, order)

    monkeypatch.setattr(orch_module.OrderOrchestrator, "submit_paper_order", spying_submit)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/paper/orders",
            json={
                "instrument": "USD_JPY",
                "direction": "BUY",
                "size": 1000,
                "stop_loss": 149.0,
                "take_profit": 152.0,
                "idempotency_key": "test-order-id-wiring-key",
            },
        )
    assert resp.status_code == 200
    assert seen_order_id == "test-order-id-wiring-key"
    assert get_order_id() is None  # restored after the request completes
