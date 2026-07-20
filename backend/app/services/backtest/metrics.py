"""Backtest performance metrics (docs/09_BACKTEST_DESIGN.md).

Pure functions over a trade list + equity curve so they're independently unit
testable against hand-computed fixtures (tests/test_backtest.py).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.backtest.engine import TradeRecord


def compute_metrics(
    trades: list["TradeRecord"], initial_capital: float, equity_curve: list[dict]
) -> dict:
    closed = [t for t in trades if t.exit_price is not None]
    total_pnl = sum(t.pnl for t in closed)
    return_pct = (total_pnl / initial_capital * 100) if initial_capital else 0.0

    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
    avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # Sharpe ratio on per-trade returns (% of capital at risk), annualized assuming
    # ~252 trading days and trade frequency implied by the sample itself.
    if len(closed) >= 2 and initial_capital:
        trade_returns = [t.pnl / initial_capital for t in closed]
        mean_r = sum(trade_returns) / len(trade_returns)
        variance = sum((r - mean_r) ** 2 for r in trade_returns) / (len(trade_returns) - 1)
        std_r = math.sqrt(variance)
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    max_drawdown_pct = _max_drawdown_pct(equity_curve)
    max_consec_wins, max_consec_losses = _max_streaks(closed)

    return {
        "total_pnl": round(float(total_pnl), 2),
        "return_pct": round(float(return_pct), 4),
        "trade_count": len(closed),
        "win_rate_pct": round(float(win_rate), 2),
        "avg_win": round(float(avg_win), 2),
        "avg_loss": round(float(avg_loss), 2),
        "profit_factor": round(float(profit_factor), 4) if math.isfinite(profit_factor) else None,
        "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown_pct": round(float(max_drawdown_pct), 4),
        "max_consecutive_wins": int(max_consec_wins),
        "max_consecutive_losses": int(max_consec_losses),
    }


def _max_drawdown_pct(equity_curve: list[dict]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]["equity"]
    max_dd = 0.0
    for point in equity_curve:
        equity = point["equity"]
        peak = max(peak, equity)
        if peak > 0:
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)
    return max_dd


def _max_streaks(closed: list["TradeRecord"]) -> tuple[int, int]:
    max_wins = cur_wins = 0
    max_losses = cur_losses = 0
    for t in closed:
        if t.pnl > 0:
            cur_wins += 1
            cur_losses = 0
        else:
            cur_losses += 1
            cur_wins = 0
        max_wins = max(max_wins, cur_wins)
        max_losses = max(max_losses, cur_losses)
    return max_wins, max_losses
