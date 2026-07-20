"""Risk Engine — the single gate every order must pass before reaching a broker
(docs/10_RISK_MANAGEMENT.md). `OrderOrchestrator` is the only caller of
`BrokerAdapter.create_order`, and it calls `RiskEngine.validate()` unconditionally
as its first step — see tests/test_risk_engine.py and
tests/test_order_orchestrator.py for the invariant this file exists to guarantee.
"""
from __future__ import annotations

from dataclasses import dataclass


class RiskRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RiskContext:
    kill_switch_active: bool
    broker_connected: bool
    price_stale: bool
    current_spread_pips: float
    max_spread_pips: float
    equity: float
    risk_amount: float  # (entry - stop_loss) * size, in account currency
    max_risk_per_trade_pct: float
    daily_loss_pct: float  # today's realized + open unrealized loss, as % of equity (positive number = loss)
    max_daily_loss_pct: float
    current_drawdown_pct: float
    max_drawdown_pct: float
    open_position_count: int
    max_concurrent_positions: int
    same_symbol_open_count: int
    max_same_symbol_positions: int
    consecutive_losses: int
    consecutive_loss_stop_count: int
    is_duplicate_idempotency_key: bool
    is_closing_order: bool = False  # close orders skip entry-risk-increasing checks (still checked 1-3, 10)


@dataclass
class RiskCheckResult:
    approved: bool
    code: str | None = None
    message: str | None = None


class RiskEngine:
    """Stateless — every check reads only from the `RiskContext` passed in, so it
    has no hidden state to get out of sync with the DB."""

    def validate(self, ctx: RiskContext) -> RiskCheckResult:
        if ctx.kill_switch_active:
            return RiskCheckResult(False, "KILL_SWITCH_ACTIVE", "Kill switch is active — no new orders permitted.")

        if not ctx.broker_connected:
            return RiskCheckResult(False, "BROKER_DISCONNECTED", "Broker is not connected.")
        if ctx.price_stale:
            return RiskCheckResult(False, "PRICE_FEED_STALE", "Price feed is stale; refusing to trade on stale data.")

        if ctx.current_spread_pips > ctx.max_spread_pips:
            return RiskCheckResult(
                False,
                "SPREAD_ANOMALY",
                f"Spread {ctx.current_spread_pips:.1f}pips exceeds max {ctx.max_spread_pips:.1f}pips.",
            )

        if ctx.is_duplicate_idempotency_key:
            return RiskCheckResult(False, "DUPLICATE_ORDER", "An order with this idempotency key was already submitted.")

        if ctx.is_closing_order:
            return RiskCheckResult(True)

        if ctx.equity > 0 and (ctx.risk_amount / ctx.equity * 100) > ctx.max_risk_per_trade_pct:
            return RiskCheckResult(
                False,
                "PER_TRADE_RISK_EXCEEDED",
                f"Trade risks {ctx.risk_amount / ctx.equity * 100:.2f}% of equity, "
                f"exceeding the {ctx.max_risk_per_trade_pct:.2f}% limit.",
            )

        if ctx.daily_loss_pct >= ctx.max_daily_loss_pct:
            return RiskCheckResult(
                False,
                "DAILY_LOSS_LIMIT",
                f"Today's loss {ctx.daily_loss_pct:.2f}% already at/beyond the {ctx.max_daily_loss_pct:.2f}% limit.",
            )

        if ctx.current_drawdown_pct >= ctx.max_drawdown_pct:
            return RiskCheckResult(
                False,
                "MAX_DRAWDOWN_EXCEEDED",
                f"Drawdown {ctx.current_drawdown_pct:.2f}% at/beyond the {ctx.max_drawdown_pct:.2f}% limit.",
            )

        if ctx.open_position_count >= ctx.max_concurrent_positions:
            return RiskCheckResult(
                False,
                "MAX_CONCURRENT_POSITIONS",
                f"{ctx.open_position_count} positions open, limit is {ctx.max_concurrent_positions}.",
            )

        if ctx.same_symbol_open_count >= ctx.max_same_symbol_positions:
            return RiskCheckResult(
                False,
                "DUPLICATE_SYMBOL_EXPOSURE",
                f"Already {ctx.same_symbol_open_count} position(s) open on this instrument "
                f"(limit {ctx.max_same_symbol_positions}).",
            )

        if ctx.consecutive_losses >= ctx.consecutive_loss_stop_count:
            return RiskCheckResult(
                False,
                "CONSECUTIVE_LOSS_STOP",
                f"{ctx.consecutive_losses} consecutive losses reached the stop threshold "
                f"({ctx.consecutive_loss_stop_count}); manual reset required.",
            )

        return RiskCheckResult(True)
