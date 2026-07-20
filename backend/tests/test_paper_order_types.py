"""Paper Trading precision (docs/15_PRODUCTION_READINESS_REVIEW.md "Paper
Trading"): market-order slippage and limit/stop order-type groundwork. Real
Postgres, not mocks — the pending-order fill path spans OrderOrchestrator +
a worker job querying the DB directly."""
import uuid

import pytest

from app.brokers.mock import MockAdapter
from app.brokers.schemas import OrderRequest, PriceQuote
from app.core.config import get_settings
from app.services.market_data import ensure_instruments
from app.services.order_orchestrator import OrderOrchestrator
from app.services.repo import get_or_create_paper_account, get_or_create_risk_settings
from app.worker.jobs import paper_pending_orders

PIP = 0.01  # USD_JPY


class FixedPriceBroker(MockAdapter):
    """A controllable quote for precise trigger-boundary testing — real
    market data is deterministic-but-moving, which makes asserting an exact
    "did the trigger fire at this price" boundary unreliable."""

    def __init__(self, bid: float, ask: float) -> None:
        super().__init__()
        self.bid = bid
        self.ask = ask

    async def get_current_price(self, instrument: str) -> PriceQuote:
        from datetime import UTC, datetime

        return PriceQuote(instrument=instrument, bid=self.bid, ask=self.ask, ts=datetime.now(UTC))


def _order(**overrides) -> OrderRequest:
    defaults = dict(
        instrument="USD_JPY",
        direction="BUY",
        size=1000,
        idempotency_key=str(uuid.uuid4()),
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)


async def test_market_buy_fill_price_includes_adverse_slippage(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = FixedPriceBroker(bid=150.00, ask=150.02)
    orchestrator = OrderOrchestrator(broker)
    settings = get_settings()

    order = _order(direction="BUY", stop_loss=149.0, take_profit=152.0)
    outcome = await orchestrator.submit_paper_order(db_session, order)

    expected = 150.02 + settings.paper_slippage_pips * PIP
    assert outcome.position.entry_price == pytest.approx(expected)


async def test_market_sell_fill_price_includes_adverse_slippage(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = FixedPriceBroker(bid=150.00, ask=150.02)
    orchestrator = OrderOrchestrator(broker)
    settings = get_settings()

    order = _order(direction="SELL", stop_loss=151.0, take_profit=148.0)
    outcome = await orchestrator.submit_paper_order(db_session, order)

    expected = 150.00 - settings.paper_slippage_pips * PIP
    assert outcome.position.entry_price == pytest.approx(expected)


async def test_limit_order_without_limit_price_is_rejected(db_session):
    await ensure_instruments(["USD_JPY"])
    orchestrator = OrderOrchestrator(FixedPriceBroker(bid=150.00, ask=150.02))
    order = _order(order_type="limit", limit_price=None)
    with pytest.raises(ValueError):
        await orchestrator.submit_paper_order(db_session, order)


async def test_limit_order_creates_a_pending_order_with_no_position(db_session):
    await ensure_instruments(["USD_JPY"])
    orchestrator = OrderOrchestrator(FixedPriceBroker(bid=150.00, ask=150.02))
    order = _order(order_type="limit", limit_price=149.50, stop_loss=149.0, take_profit=151.0)

    outcome = await orchestrator.submit_paper_order(db_session, order)

    assert outcome.position is None
    assert outcome.order.status == "pending"
    assert outcome.order.order_type == "limit"
    assert outcome.order.limit_price == 149.50


async def test_pending_limit_buy_fills_once_ask_drops_to_the_limit(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = FixedPriceBroker(bid=150.00, ask=150.02)
    orchestrator = OrderOrchestrator(broker)
    order = _order(order_type="limit", limit_price=149.50, direction="BUY")
    outcome = await orchestrator.submit_paper_order(db_session, order)
    pending_order = outcome.order

    # Not yet triggered - ask is still above the limit price.
    result = await orchestrator.try_fill_pending_order(db_session, pending_order)
    assert result is None

    # Price drops to/through the limit.
    broker.bid, broker.ask = 149.48, 149.50
    result = await orchestrator.try_fill_pending_order(db_session, pending_order)
    assert result is not None
    assert result.entry_price == 149.50  # fills exactly at the limit price, no slippage
    assert pending_order.status == "filled"


async def test_pending_stop_buy_fills_with_slippage_once_triggered(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = FixedPriceBroker(bid=150.00, ask=150.02)
    orchestrator = OrderOrchestrator(broker)
    settings = get_settings()
    order = _order(order_type="stop", limit_price=150.50, direction="BUY")
    outcome = await orchestrator.submit_paper_order(db_session, order)
    pending_order = outcome.order

    broker.bid, broker.ask = 150.52, 150.54
    result = await orchestrator.try_fill_pending_order(db_session, pending_order)
    assert result is not None
    expected = 150.54 + settings.paper_slippage_pips * PIP
    assert result.entry_price == pytest.approx(expected)


async def test_pending_order_never_fills_while_kill_switch_is_active(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = FixedPriceBroker(bid=150.00, ask=150.02)
    orchestrator = OrderOrchestrator(broker)
    order = _order(order_type="limit", limit_price=149.50, direction="BUY")
    outcome = await orchestrator.submit_paper_order(db_session, order)
    pending_order = outcome.order

    risk_settings = await get_or_create_risk_settings(db_session)
    risk_settings.kill_switch_active = True
    await db_session.commit()

    broker.bid, broker.ask = 149.48, 149.50  # trigger condition is met...
    result = await orchestrator.try_fill_pending_order(db_session, pending_order)
    assert result is None  # ...but the kill switch blocks the fill anyway
    assert pending_order.status == "pending"


async def test_worker_job_fills_across_all_pending_orders(db_session):
    await ensure_instruments(["USD_JPY", "EUR_JPY"])
    broker = FixedPriceBroker(bid=150.00, ask=150.02)
    orchestrator = OrderOrchestrator(broker)

    order1 = _order(instrument="USD_JPY", order_type="limit", limit_price=150.02)  # already satisfied
    outcome1 = await orchestrator.submit_paper_order(db_session, order1)
    order2 = _order(instrument="USD_JPY", order_type="limit", limit_price=100.0, idempotency_key=str(uuid.uuid4()))
    outcome2 = await orchestrator.submit_paper_order(db_session, order2)  # far away, won't trigger

    import app.worker.jobs.paper_pending_orders as job_module

    job_module.get_market_data_provider = lambda: broker
    result = await paper_pending_orders.run()

    assert result["pending"] == 2
    assert result["filled"] == 1

    await db_session.refresh(outcome1.order)
    await db_session.refresh(outcome2.order)
    assert outcome1.order.status == "filled"
    assert outcome2.order.status == "pending"


async def test_cancel_pending_order(db_session):
    await ensure_instruments(["USD_JPY"])
    orchestrator = OrderOrchestrator(FixedPriceBroker(bid=150.00, ask=150.02))
    order = _order(order_type="limit", limit_price=149.50)
    outcome = await orchestrator.submit_paper_order(db_session, order)

    cancelled = await orchestrator.cancel_pending_order(db_session, outcome.order.id)
    assert cancelled.status == "cancelled"

    with pytest.raises(ValueError):
        await orchestrator.cancel_pending_order(db_session, outcome.order.id)  # already cancelled


async def test_oanda_and_mock_adapters_reject_non_market_create_order():
    from app.brokers.errors import BrokerOrderRejected
    from app.brokers.oanda import OandaAdapter

    order = _order(order_type="limit", limit_price=149.50, idempotency_key=str(uuid.uuid4()))

    mock_broker = MockAdapter()
    with pytest.raises(BrokerOrderRejected):
        await mock_broker.create_order(order)

    oanda = OandaAdapter(api_token="fake", account_id="fake", environment="practice")
    with pytest.raises(BrokerOrderRejected):
        await oanda.create_order(order)
