"""One test per Risk Engine rejection rule (docs/10_RISK_MANAGEMENT.md,
docs/13_TEST_STRATEGY.md). `_ok_ctx` is an otherwise-fully-compliant context; each
test flips exactly one field to isolate what's being checked.
"""
from dataclasses import replace

from app.services.risk_engine import RiskContext, RiskEngine

engine = RiskEngine()


def _ok_ctx(**overrides) -> RiskContext:
    base = RiskContext(
        kill_switch_active=False,
        broker_connected=True,
        price_stale=False,
        current_spread_pips=1.0,
        max_spread_pips=3.0,
        equity=1_000_000,
        risk_amount=5_000,  # 0.5% of equity
        max_risk_per_trade_pct=1.0,
        daily_loss_pct=0.5,
        max_daily_loss_pct=3.0,
        current_drawdown_pct=1.0,
        max_drawdown_pct=10.0,
        open_position_count=0,
        max_concurrent_positions=3,
        same_symbol_open_count=0,
        max_same_symbol_positions=1,
        consecutive_losses=0,
        consecutive_loss_stop_count=4,
        is_duplicate_idempotency_key=False,
    )
    return replace(base, **overrides)


def test_approves_a_fully_compliant_order():
    result = engine.validate(_ok_ctx())
    assert result.approved is True


def test_rejects_when_kill_switch_active():
    result = engine.validate(_ok_ctx(kill_switch_active=True))
    assert result.approved is False
    assert result.code == "KILL_SWITCH_ACTIVE"


def test_rejects_when_broker_disconnected():
    result = engine.validate(_ok_ctx(broker_connected=False))
    assert result.approved is False
    assert result.code == "BROKER_DISCONNECTED"


def test_rejects_when_price_feed_stale():
    result = engine.validate(_ok_ctx(price_stale=True))
    assert result.approved is False
    assert result.code == "PRICE_FEED_STALE"


def test_rejects_on_spread_anomaly():
    result = engine.validate(_ok_ctx(current_spread_pips=10.0, max_spread_pips=3.0))
    assert result.approved is False
    assert result.code == "SPREAD_ANOMALY"


def test_rejects_duplicate_idempotency_key():
    result = engine.validate(_ok_ctx(is_duplicate_idempotency_key=True))
    assert result.approved is False
    assert result.code == "DUPLICATE_ORDER"


def test_rejects_when_per_trade_risk_exceeded():
    result = engine.validate(_ok_ctx(risk_amount=50_000, max_risk_per_trade_pct=1.0, equity=1_000_000))
    assert result.approved is False
    assert result.code == "PER_TRADE_RISK_EXCEEDED"


def test_rejects_when_daily_loss_limit_reached():
    result = engine.validate(_ok_ctx(daily_loss_pct=3.5, max_daily_loss_pct=3.0))
    assert result.approved is False
    assert result.code == "DAILY_LOSS_LIMIT"


def test_rejects_when_max_drawdown_exceeded():
    result = engine.validate(_ok_ctx(current_drawdown_pct=12.0, max_drawdown_pct=10.0))
    assert result.approved is False
    assert result.code == "MAX_DRAWDOWN_EXCEEDED"


def test_rejects_when_max_concurrent_positions_reached():
    result = engine.validate(_ok_ctx(open_position_count=3, max_concurrent_positions=3))
    assert result.approved is False
    assert result.code == "MAX_CONCURRENT_POSITIONS"


def test_rejects_duplicate_symbol_exposure():
    result = engine.validate(_ok_ctx(same_symbol_open_count=1, max_same_symbol_positions=1))
    assert result.approved is False
    assert result.code == "DUPLICATE_SYMBOL_EXPOSURE"


def test_rejects_after_consecutive_loss_stop_reached():
    result = engine.validate(_ok_ctx(consecutive_losses=4, consecutive_loss_stop_count=4))
    assert result.approved is False
    assert result.code == "CONSECUTIVE_LOSS_STOP"


def test_closing_orders_skip_entry_risk_checks_but_not_safety_checks():
    # A closing order should not be blocked by per-trade-risk / daily-loss / etc,
    # but must still be blocked by kill switch / disconnect / stale price / spread.
    result = engine.validate(_ok_ctx(is_closing_order=True, risk_amount=999_999_999))
    assert result.approved is True

    result = engine.validate(_ok_ctx(is_closing_order=True, kill_switch_active=True))
    assert result.approved is False
    assert result.code == "KILL_SWITCH_ACTIVE"


def test_kill_switch_takes_priority_over_every_other_violation():
    result = engine.validate(
        _ok_ctx(
            kill_switch_active=True,
            broker_connected=False,
            current_spread_pips=999,
            risk_amount=999_999_999,
        )
    )
    assert result.code == "KILL_SWITCH_ACTIVE"
