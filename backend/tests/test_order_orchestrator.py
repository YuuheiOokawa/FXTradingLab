"""Order Orchestrator integration tests against a real Postgres test database
(docs/13_TEST_STRATEGY.md). These specifically assert the invariant the whole Risk
Engine design exists to guarantee: a rejected order never reaches
`BrokerAdapter.create_order`, the kill switch blocks mid-flow, and duplicate
idempotency keys never create a second position.
"""
import uuid
from unittest.mock import AsyncMock

import pytest

from app.brokers.mock import MockAdapter
from app.brokers.schemas import OrderRequest
from app.services.market_data import ensure_instruments
from app.services.order_orchestrator import OrderOrchestrator
from app.services.repo import get_or_create_paper_account, get_or_create_risk_settings
from app.services.risk_engine import RiskRejected


def _order(**overrides) -> OrderRequest:
    defaults = dict(
        instrument="USD_JPY",
        direction="BUY",
        size=1000,
        stop_loss=156.0,
        take_profit=158.0,
        idempotency_key=str(uuid.uuid4()),
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)


async def test_compliant_order_opens_a_paper_position(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)

    quote = await broker.get_current_price("USD_JPY")
    order = _order(stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3))
    outcome = await orchestrator.submit_paper_order(db_session, order)

    assert outcome.approved is True
    assert outcome.position is not None
    assert outcome.position.status == "open"


async def test_risk_rejected_order_never_reaches_broker_create_order(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = MockAdapter()
    broker.create_order = AsyncMock(side_effect=AssertionError("create_order must not be called for a rejected order"))
    orchestrator = OrderOrchestrator(broker)

    # SL far enough away that the risk-per-trade check (default 1%) rejects it.
    order = _order(size=10_000_000, stop_loss=100.0, take_profit=200.0)

    with pytest.raises(RiskRejected) as exc_info:
        await orchestrator.submit_paper_order(db_session, order)
    assert exc_info.value.code == "PER_TRADE_RISK_EXCEEDED"
    broker.create_order.assert_not_called()


async def test_kill_switch_blocks_new_orders(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)

    await orchestrator.activate_kill_switch(db_session, flatten_positions=False)

    order = _order()
    with pytest.raises(RiskRejected) as exc_info:
        await orchestrator.submit_paper_order(db_session, order)
    assert exc_info.value.code == "KILL_SWITCH_ACTIVE"


async def test_kill_switch_flattens_open_positions(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)

    quote = await broker.get_current_price("USD_JPY")
    order = _order(stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3))
    outcome = await orchestrator.submit_paper_order(db_session, order)
    assert outcome.position is not None

    result = await orchestrator.activate_kill_switch(db_session, flatten_positions=True)
    assert str(outcome.position.id) in result["flattened_positions"]

    account = await get_or_create_paper_account(db_session)
    from sqlalchemy import select

    from app.db.models.trading import PaperPosition

    rows = (
        await db_session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.status == "open")
        )
    ).scalars().all()
    assert len(rows) == 0


async def test_duplicate_idempotency_key_does_not_open_a_second_position(db_session):
    await ensure_instruments(["USD_JPY"])
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)

    quote = await broker.get_current_price("USD_JPY")
    order = _order(stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3))

    first = await orchestrator.submit_paper_order(db_session, order)
    second = await orchestrator.submit_paper_order(db_session, order)

    assert first.order.id == second.order.id
    assert first.position.id == second.position.id

    account = await get_or_create_paper_account(db_session)
    from sqlalchemy import select

    from app.db.models.trading import PaperPosition

    rows = (
        await db_session.execute(select(PaperPosition).where(PaperPosition.account_id == account.id))
    ).scalars().all()
    assert len(rows) == 1


async def test_concurrent_duplicate_submissions_result_in_exactly_one_open_position(db_session):
    """Idempotency under a race — two 'simultaneous' submissions of the same key
    must not both succeed in creating separate positions."""
    import asyncio

    from app.db.session import AsyncSessionLocal

    await ensure_instruments(["USD_JPY"])
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)
    quote = await broker.get_current_price("USD_JPY")
    key = str(uuid.uuid4())
    order = _order(idempotency_key=key, stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3))

    async def submit():
        async with AsyncSessionLocal() as session:
            return await orchestrator.submit_paper_order(session, order)

    results = await asyncio.gather(*(submit() for _ in range(5)), return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]
    assert all(s.order.idempotency_key == key for s in successes)

    account = await get_or_create_paper_account(db_session)
    from sqlalchemy import select

    from app.db.models.trading import PaperOrder, PaperPosition

    order_rows = (
        await db_session.execute(select(PaperOrder).where(PaperOrder.idempotency_key == key))
    ).scalars().all()
    assert len(order_rows) == 1  # unique constraint enforces this even under a race

    position_rows = (
        await db_session.execute(select(PaperPosition).where(PaperPosition.account_id == account.id))
    ).scalars().all()
    assert len(position_rows) == 1


# --------------------------------------------------------------------------
# Stress tests (docs/15_PRODUCTION_READINESS_REVIEW.md): the adverse scenarios
# explicitly called out for re-verification beyond the original 14 Risk Engine
# unit tests — broker disconnect (at entry and at close), daily loss limit,
# max concurrent positions, and consecutive-loss stop, all exercised through
# the real submit/close flow against the real test database.
# --------------------------------------------------------------------------
from app.brokers.errors import BrokerConnectionError as _BrokerConnectionError
from app.brokers.schemas import PriceQuote as _PriceQuote


class DisconnectedBroker(MockAdapter):
    """Wraps MockAdapter but simulates a broker/network outage for price
    reads — everything else (order book bookkeeping) still works so we can
    inspect state after the failure."""

    def __init__(self) -> None:
        super().__init__()

    async def get_current_price(self, instrument: str) -> _PriceQuote:
        raise _BrokerConnectionError("simulated broker outage")


async def test_broker_disconnected_rejects_new_paper_orders(db_session):
    await ensure_instruments(["USD_JPY"])
    orchestrator = OrderOrchestrator(DisconnectedBroker())
    order = _order()
    with pytest.raises(RiskRejected) as exc_info:
        await orchestrator.submit_paper_order(db_session, order)
    assert exc_info.value.code == "BROKER_DISCONNECTED"

    account = await get_or_create_paper_account(db_session)
    from sqlalchemy import select

    from app.db.models.trading import PaperPosition

    rows = (
        await db_session.execute(select(PaperPosition).where(PaperPosition.account_id == account.id))
    ).scalars().all()
    assert len(rows) == 0  # no position was opened despite the rejected order


async def test_broker_disconnect_during_close_leaves_position_open(db_session):
    """A broker outage mid-close must not corrupt state — the position must
    stay exactly 'open' (safe to retry), never half-closed."""
    await ensure_instruments(["USD_JPY"])
    live_broker = MockAdapter()
    orchestrator = OrderOrchestrator(live_broker)
    quote = await live_broker.get_current_price("USD_JPY")
    order = _order(stop_loss=round(quote.mid - 0.3, 3), take_profit=round(quote.mid + 0.6, 3))
    outcome = await orchestrator.submit_paper_order(db_session, order)
    position_id = outcome.position.id

    disconnected_orchestrator = OrderOrchestrator(DisconnectedBroker())
    with pytest.raises(_BrokerConnectionError):
        await disconnected_orchestrator.close_paper_position(db_session, position_id)

    from app.db.models.trading import PaperPosition

    refreshed = await db_session.get(PaperPosition, position_id)
    assert refreshed.status == "open"
    assert refreshed.closed_at is None


async def test_daily_loss_limit_blocks_new_orders_after_losses(db_session):
    """Integration-level check that RiskContext.daily_loss_pct, computed from
    real TradeJournal rows via _today_realized_pnl, actually blocks a new
    order end-to-end (not just the isolated RiskEngine unit test)."""
    await ensure_instruments(["USD_JPY"])
    from datetime import UTC, datetime

    from app.db.models.journal import TradeJournal

    account = await get_or_create_paper_account(db_session)
    # Simulate today's realized losses totaling ~4% of the ¥1,000,000 default
    # balance — above the default 3% max_daily_loss_pct.
    db_session.add(
        TradeJournal(
            source="paper",
            pair="USD_JPY",
            direction="BUY",
            entry_time=datetime.now(UTC),
            entry_price=157.0,
            exit_time=datetime.now(UTC),
            exit_price=156.0,
            size=40000,
            pnl=-40000.0,
            reason="test fixture",
            closed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    orchestrator = OrderOrchestrator(MockAdapter())
    order = _order()
    with pytest.raises(RiskRejected) as exc_info:
        await orchestrator.submit_paper_order(db_session, order)
    assert exc_info.value.code == "DAILY_LOSS_LIMIT"


async def test_max_concurrent_positions_blocks_the_nth_plus_one_order(db_session):
    await ensure_instruments(["USD_JPY", "EUR_JPY", "GBP_JPY", "EUR_USD"])
    broker = MockAdapter()
    orchestrator = OrderOrchestrator(broker)

    # Default max_concurrent_positions is 3 — open exactly that many across
    # distinct instruments (to avoid tripping the separate same-symbol check).
    for symbol in ["USD_JPY", "EUR_JPY", "GBP_JPY"]:
        quote = await broker.get_current_price(symbol)
        order = _order(
            instrument=symbol,
            stop_loss=round(quote.mid - 0.3, 3),
            take_profit=round(quote.mid + 0.6, 3),
            idempotency_key=str(uuid.uuid4()),
        )
        await orchestrator.submit_paper_order(db_session, order)

    quote = await broker.get_current_price("EUR_USD")
    fourth = _order(
        instrument="EUR_USD",
        stop_loss=round(quote.mid - 0.003, 5),
        take_profit=round(quote.mid + 0.006, 5),
        idempotency_key=str(uuid.uuid4()),
    )
    with pytest.raises(RiskRejected) as exc_info:
        await orchestrator.submit_paper_order(db_session, fourth)
    assert exc_info.value.code == "MAX_CONCURRENT_POSITIONS"


async def test_consecutive_loss_stop_blocks_new_orders(db_session):
    await ensure_instruments(["USD_JPY"])
    from datetime import UTC, datetime, timedelta

    from app.db.models.journal import TradeJournal

    # Default consecutive_loss_stop_count is 4 — four losing trades in a row
    # (most-recent-first when queried) should trip the stop.
    now = datetime.now(UTC)
    for i in range(4):
        db_session.add(
            TradeJournal(
                source="paper",
                pair="USD_JPY",
                direction="BUY",
                entry_time=now - timedelta(days=1, minutes=i),
                entry_price=157.0,
                exit_time=now - timedelta(days=1, minutes=i) + timedelta(minutes=5),
                exit_price=156.9,
                size=1000,
                pnl=-100.0,
                reason="test fixture",
                closed_at=now - timedelta(hours=i + 1),  # yesterday-ish, avoids the daily-loss check firing first
            )
        )
    await db_session.commit()

    orchestrator = OrderOrchestrator(MockAdapter())
    order = _order()
    with pytest.raises(RiskRejected) as exc_info:
        await orchestrator.submit_paper_order(db_session, order)
    assert exc_info.value.code == "CONSECUTIVE_LOSS_STOP"
