"""LIVE order execution: implemented, gated, and deliberately NOT automated.

Two separate things are pinned here:

1. **Execution correctness** — the three gates, idempotent replay, Risk Engine
   veto, and what happens when the broker rejects or the connection dies
   mid-flight.
2. **Disconnection** — that no automatic code path can reach `submit_live_order`.
   The auto-trader trades paper only, by design; this is asserted structurally
   (by inspecting the source and by driving the loop with a broker that fails
   loudly if a real order is attempted) rather than trusted to a comment,
   because "the bot cannot place real orders" is the single claim in this
   codebase that must never quietly stop being true.
"""
import ast
import inspect
import pathlib
import uuid
from datetime import UTC, datetime

import pytest

from app.brokers.errors import BrokerConnectionError, BrokerOrderRejected
from app.brokers.schemas import AccountSummary, OrderRequest, OrderResult, PriceQuote
from app.core.config import Settings
from app.db.models.trading import LiveOrder
from app.services import auto_trader
from app.services.market_data import ensure_instruments
from app.services.order_orchestrator import LiveTradingDisabled, OrderOrchestrator
from app.services.repo import get_or_create_risk_settings
from app.services.risk_engine import RiskRejected
from sqlalchemy import select


class _Broker:
    """Trading broker stub that records whether a real order was attempted."""

    provider = "stub"

    def __init__(self, *, order_result=None, raises=None) -> None:
        self.created: list[OrderRequest] = []
        self._order_result = order_result
        self._raises = raises

    async def get_current_price(self, instrument: str) -> PriceQuote:
        return PriceQuote(instrument=instrument, bid=149.99, ask=150.01, ts=datetime.now(UTC))

    async def get_account(self) -> AccountSummary:
        return AccountSummary(
            account_id="X", balance=1_000_000, equity=1_000_000,
            unrealized_pnl=0.0, margin_used=0.0, margin_available=1_000_000, currency="JPY",
        )

    async def get_positions(self):
        return []

    async def get_candles(self, instrument, granularity, count, from_time=None):
        return []

    async def create_order(self, order: OrderRequest) -> OrderResult:
        self.created.append(order)
        if self._raises is not None:
            raise self._raises
        return self._order_result or OrderResult(
            success=True, broker_order_id="B-1", trade_id="T-1", filled_price=150.01, status="filled"
        )

    async def close_position(self, instrument: str) -> OrderResult:
        return OrderResult(success=True, status="filled")

    async def stream_prices(self, instruments):
        raise NotImplementedError


def _order(**kw) -> OrderRequest:
    return OrderRequest(
        instrument=kw.get("instrument", "USD_JPY"),
        direction=kw.get("direction", "BUY"),
        size=kw.get("size", 1000),
        stop_loss=kw.get("stop_loss", 149.0),
        take_profit=kw.get("take_profit", 152.0),
        idempotency_key=kw.get("key", f"live-{uuid.uuid4()}"),
    )


def _settings(**kw) -> Settings:
    return Settings(
        app_env="development",
        live_trading_enabled=kw.get("live_enabled", True),
        broker_provider="mock",
        broker_environment="practice",
    )


async def _enable_admin_gate(session, enabled: bool = True):
    rs = await get_or_create_risk_settings(session)
    rs.kill_switch_active = False
    rs.live_trading_admin_enabled = enabled
    await session.commit()
    return rs


class TestGates:
    async def test_blocked_when_env_flag_is_off(self, db_session):
        await _enable_admin_gate(db_session)
        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(live_enabled=False), trading_broker=broker)
        with pytest.raises(LiveTradingDisabled) as exc:
            await orch.submit_live_order(db_session, _order(), confirm_live=True)
        assert any("LIVE_TRADING_ENABLED" in g for g in exc.value.missing_gates)
        assert broker.created == [], "no broker call may happen when a gate is unmet"

    async def test_blocked_when_admin_setting_is_off(self, db_session):
        await _enable_admin_gate(db_session, enabled=False)
        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)
        with pytest.raises(LiveTradingDisabled):
            await orch.submit_live_order(db_session, _order(), confirm_live=True)
        assert broker.created == []

    async def test_blocked_without_per_request_confirmation(self, db_session):
        await _enable_admin_gate(db_session)
        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)
        with pytest.raises(LiveTradingDisabled):
            await orch.submit_live_order(db_session, _order(), confirm_live=False)
        assert broker.created == []


class TestExecution:
    async def test_all_gates_open_places_the_order(self, db_session):
        await ensure_instruments(["USD_JPY"])
        await _enable_admin_gate(db_session)
        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)

        outcome = await orch.submit_live_order(db_session, _order(), confirm_live=True)
        assert outcome.approved is True
        assert len(broker.created) == 1
        assert outcome.order.broker_order_id == "B-1"
        assert outcome.order.status == "filled"

    async def test_order_goes_to_the_trading_broker_not_the_data_broker(self, db_session):
        """With a split configuration the order must reach the TRADING broker."""
        await ensure_instruments(["USD_JPY"])
        await _enable_admin_gate(db_session)
        data_broker, trading_broker = _Broker(), _Broker()
        orch = OrderOrchestrator(data_broker, settings=_settings(), trading_broker=trading_broker)

        await orch.submit_live_order(db_session, _order(), confirm_live=True)
        assert len(trading_broker.created) == 1
        assert data_broker.created == []

    async def test_replaying_the_same_key_does_not_place_a_second_order(self, db_session):
        await ensure_instruments(["USD_JPY"])
        await _enable_admin_gate(db_session)
        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)
        order = _order(key="live-fixed-key")

        first = await orch.submit_live_order(db_session, order, confirm_live=True)
        second = await orch.submit_live_order(db_session, order, confirm_live=True)
        assert len(broker.created) == 1, "an idempotent replay must not duplicate a real order"
        assert second.order.id == first.order.id

    async def test_risk_rejection_never_reaches_the_broker(self, db_session):
        await ensure_instruments(["USD_JPY"])
        rs = await _enable_admin_gate(db_session)
        rs.kill_switch_active = True  # Risk Engine must veto
        await db_session.commit()
        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)

        with pytest.raises(RiskRejected):
            await orch.submit_live_order(db_session, _order(), confirm_live=True)
        assert broker.created == [], "a risk-rejected order must never be sent"

        rows = (await db_session.execute(select(LiveOrder).where(LiveOrder.status == "rejected"))).scalars().all()
        assert rows, "the rejection must be recorded for the audit trail"

    async def test_limit_orders_are_refused_rather_than_sent_as_market(self, db_session):
        await ensure_instruments(["USD_JPY"])
        await _enable_admin_gate(db_session)
        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)
        order = OrderRequest(
            instrument="USD_JPY", direction="BUY", size=1000, order_type="limit",
            limit_price=148.0, idempotency_key=f"live-{uuid.uuid4()}",
        )
        with pytest.raises(ValueError, match="market"):
            await orch.submit_live_order(db_session, order, confirm_live=True)
        assert broker.created == []


class TestBrokerFailures:
    async def test_broker_rejection_is_recorded_and_reraised(self, db_session):
        await ensure_instruments(["USD_JPY"])
        await _enable_admin_gate(db_session)
        broker = _Broker(raises=BrokerOrderRejected("insufficient margin"))
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)

        with pytest.raises(BrokerOrderRejected):
            await orch.submit_live_order(db_session, _order(key="live-rej"), confirm_live=True)

        row = (await db_session.execute(
            select(LiveOrder).where(LiveOrder.idempotency_key == "live-rej")
        )).scalar_one()
        assert row.status == "rejected"
        assert "margin" in (row.reject_reason or "")

    async def test_connection_error_is_marked_unknown_not_failed(self, db_session):
        """A dropped connection means the order MIGHT have been placed. Marking
        it 'rejected' would invite a retry that opens a duplicate position."""
        await ensure_instruments(["USD_JPY"])
        await _enable_admin_gate(db_session)
        broker = _Broker(raises=BrokerConnectionError("timeout"))
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)

        with pytest.raises(BrokerConnectionError):
            await orch.submit_live_order(db_session, _order(key="live-unknown"), confirm_live=True)

        row = (await db_session.execute(
            select(LiveOrder).where(LiveOrder.idempotency_key == "live-unknown")
        )).scalar_one()
        assert row.status == "unknown"


class TestNotAutomated:
    """LIVE execution exists but nothing automatic may call it."""

    def test_auto_trader_source_never_references_live_submission(self):
        src = inspect.getsource(auto_trader)
        tree = ast.parse(src)
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "submit_live_order" not in called
        assert "create_order" not in called
        assert "submit_paper_order" in called, "the auto-trader should still trade paper"

    def test_no_worker_job_calls_live_submission(self):
        jobs = pathlib.Path(auto_trader.__file__).parent.parent / "worker" / "jobs"
        offenders = [
            f.name for f in jobs.glob("*.py") if "submit_live_order" in f.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"worker jobs must not submit LIVE orders: {offenders}"

    async def test_auto_trader_loop_places_only_paper_orders(self, db_session):
        """Drive one evaluation with every LIVE gate wide open: it must still
        never call create_order on the broker."""
        await ensure_instruments(["USD_JPY"])
        rs = await _enable_admin_gate(db_session)
        rs.auto_mode = "full_auto"
        await db_session.commit()

        broker = _Broker()
        orch = OrderOrchestrator(broker, settings=_settings(), trading_broker=broker)
        await auto_trader._evaluate_and_maybe_trade(orch, "USD_JPY")

        assert broker.created == [], "the auto-trader must never place a real broker order"
