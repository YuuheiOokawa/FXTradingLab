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
