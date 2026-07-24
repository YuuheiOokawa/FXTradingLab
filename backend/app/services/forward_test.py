"""Forward-test scoring for the playbook.

A backtest says what a strategy *would* have done. This says what it actually
IS doing, on the same metrics, so the two can be compared directly — which is
the only way to catch a strategy that looked good on history and does not
survive contact with live prices.

Metrics deliberately mirror the 23-year study (win rate, expectancy, profit
factor, max drawdown) rather than a prettier subset, because a forward test
that reports only the flattering half is worse than none. Each pair's
backtested expectation is included alongside its live result so a divergence is
visible without the operator holding two numbers in their head.

Pure functions over already-fetched rows: no DB or network access here, so the
scoring rules are unit-testable in isolation (tests/test_forward_test.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# What each pair's shipped configuration produced over its full available daily
# history, using the multi-era-validated parameters in app/services/playbook.py.
# USD/JPY spans ~29.7 years (back to 1996); the other two ~23 years, the limit
# of available daily data for them.
BACKTEST_BASELINE: dict[str, dict[str, float]] = {
    "USD_JPY": {"win_rate_pct": 49.4, "profit_factor": 1.33, "trades_per_year": 2.8},
    "EUR_JPY": {"win_rate_pct": 43.0, "profit_factor": 1.69, "trades_per_year": 3.4},
    "GBP_JPY": {"win_rate_pct": 72.9, "profit_factor": 1.95, "trades_per_year": 2.1},
}

# Below this many closed trades, per-pair rates are noise. Reported anyway (so
# the operator sees activity) but flagged, because acting on a 3-trade win rate
# is how a working strategy gets switched off after normal variance.
MIN_TRADES_FOR_CONFIDENCE = 20


@dataclass(frozen=True)
class ForwardStats:
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    total_pnl: float
    expectancy: float          # mean P&L per trade, account currency
    profit_factor: float | None  # None when there are no losses yet to divide by
    gross_profit: float
    gross_loss: float
    max_drawdown: float        # most negative peak-to-trough of cumulative P&L
    avg_hold_hours: float | None
    best: float
    worst: float


def _drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def summarize(trades: list) -> ForwardStats:
    """Score a list of closed TradeJournal-like rows (need .pnl, and optionally
    .entry_time/.exit_time for holding period)."""
    if not trades:
        return ForwardStats(0, 0, 0, 0.0, 0.0, 0.0, None, 0.0, 0.0, 0.0, None, 0.0, 0.0)

    pnls = [float(t.pnl) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)

    holds: list[float] = []
    for t in trades:
        entry, exit_ = getattr(t, "entry_time", None), getattr(t, "exit_time", None)
        if entry is not None and exit_ is not None:
            holds.append((exit_ - entry).total_seconds() / 3600.0)

    return ForwardStats(
        trades=len(pnls),
        wins=len(wins),
        losses=len(losses),
        win_rate_pct=round(len(wins) / len(pnls) * 100, 2),
        total_pnl=round(sum(pnls), 2),
        expectancy=round(sum(pnls) / len(pnls), 2),
        # No losses yet is not "infinitely good" — it is too early to divide.
        profit_factor=round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        gross_profit=round(gross_profit, 2),
        gross_loss=round(gross_loss, 2),
        max_drawdown=round(_drawdown(pnls), 2),
        avg_hold_hours=round(sum(holds) / len(holds), 1) if holds else None,
        best=round(max(pnls), 2),
        worst=round(min(pnls), 2),
    )


def compare_to_backtest(pair: str, stats: ForwardStats) -> dict | None:
    """Live-vs-backtest deltas for one pair, or None if that pair has no baseline."""
    base = BACKTEST_BASELINE.get(pair)
    if base is None:
        return None
    out = {
        "backtest_win_rate_pct": base["win_rate_pct"],
        "backtest_profit_factor": base["profit_factor"],
        "win_rate_delta": round(stats.win_rate_pct - base["win_rate_pct"], 2),
        "profit_factor_delta": (
            round(stats.profit_factor - base["profit_factor"], 3) if stats.profit_factor is not None else None
        ),
        "enough_trades": stats.trades >= MIN_TRADES_FOR_CONFIDENCE,
    }
    return out


def verdict(stats: ForwardStats) -> str:
    """A short, deliberately conservative read of the live results."""
    if stats.trades == 0:
        return "no_trades"
    if stats.trades < MIN_TRADES_FOR_CONFIDENCE:
        return "too_early"
    if stats.profit_factor is None:
        return "too_early"
    if stats.profit_factor >= 1.2:
        return "tracking"
    if stats.profit_factor >= 1.0:
        return "marginal"
    return "underperforming"


def build_report(rows_by_pair: dict[str, list], overall_rows: list) -> dict:
    per_pair = []
    for pair, rows in sorted(rows_by_pair.items()):
        stats = summarize(rows)
        per_pair.append(
            {
                "pair": pair,
                **asdict(stats),
                "verdict": verdict(stats),
                "vs_backtest": compare_to_backtest(pair, stats),
            }
        )
    overall = summarize(overall_rows)
    return {
        "overall": {**asdict(overall), "verdict": verdict(overall)},
        "per_pair": per_pair,
        "min_trades_for_confidence": MIN_TRADES_FOR_CONFIDENCE,
    }
