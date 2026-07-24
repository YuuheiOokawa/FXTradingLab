"""Risk-based position sizing.

The Risk Engine (app/services/risk_engine.py) *rejects* an order that risks too
much, but nothing was *choosing* a size — the auto-trader submitted a fixed
1,000 units regardless of how far away its stop sat. That makes risk per trade
swing with volatility: the same 1,000 units on a GBP/JPY signal (ATR ~164 pips)
risks roughly twice what it does on a USD/JPY one (ATR ~94 pips), which is
exactly backwards from how the strategies were measured.

This module sizes each trade so that **being stopped out costs the same
fraction of equity every time**, which is what `max_risk_per_trade_pct` was
always meant to express. Volatile instruments therefore get proportionally
smaller positions, not larger risk.

Currency note: `size_for_risk` computes risk in the QUOTE currency of the pair.
For the JPY-quoted pairs this app trades (USD/JPY, EUR/JPY, GBP/JPY) against a
JPY paper account those coincide, so the default conversion of 1.0 is correct.
A non-JPY-quoted pair (EUR/USD) needs `quote_to_account_rate` supplied; it is
required rather than guessed so a wrong-currency size can't pass silently.
"""
from __future__ import annotations

from dataclasses import dataclass

# Broker/paper minimums. Sizes are rounded DOWN to a whole step so rounding can
# only ever reduce risk, never push a trade over its budget.
MIN_SIZE = 1000.0
SIZE_STEP = 1000.0

# When volatility spikes far above normal, the market is usually reacting to an
# event and slippage/gap risk is well above what the stop implies. Halving size
# there follows the standard practice of cutting exposure around events; this
# app has no economic-calendar feed, so realised volatility is used as the
# available proxy rather than a hardcoded list of dates.
VOL_SPIKE_RATIO = 2.0
VOL_SPIKE_MULTIPLIER = 0.5


@dataclass(frozen=True)
class SizingResult:
    size: float
    risk_amount: float        # what a stop-out costs, in account currency
    risk_pct_of_equity: float
    multiplier: float         # 1.0 normally, 0.5 when de-risked
    note: str


def volatility_multiplier(current_atr: float, baseline_atr: float) -> float:
    """1.0 normally, 0.5 when current volatility is a multiple of its baseline."""
    if baseline_atr <= 0 or current_atr <= 0:
        return 1.0
    return VOL_SPIKE_MULTIPLIER if current_atr / baseline_atr >= VOL_SPIKE_RATIO else 1.0


def size_for_risk(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    *,
    quote_to_account_rate: float = 1.0,
    multiplier: float = 1.0,
    min_size: float = MIN_SIZE,
    size_step: float = SIZE_STEP,
    max_size: float | None = None,
) -> SizingResult | None:
    """Units to trade so a stop-out costs `risk_pct` of `equity`.

    Returns None when no valid size exists — bad inputs, or an account too small
    to take even the minimum position within its risk budget. Refusing to trade
    is the correct outcome there; scaling the risk limit up to fit the minimum
    lot would silently break the limit the operator set.
    """
    stop_distance = abs(entry_price - stop_loss)
    if equity <= 0 or risk_pct <= 0 or stop_distance <= 0 or quote_to_account_rate <= 0:
        return None

    budget = equity * (risk_pct / 100.0) * multiplier
    raw_size = budget / (stop_distance * quote_to_account_rate)

    steps = int(raw_size // size_step)
    size = steps * size_step
    if max_size is not None:
        size = min(size, max_size)
    if size < min_size:
        # Even one minimum position would exceed the budget.
        return None

    risk_amount = size * stop_distance * quote_to_account_rate
    return SizingResult(
        size=size,
        risk_amount=risk_amount,
        risk_pct_of_equity=risk_amount / equity * 100.0,
        multiplier=multiplier,
        note="volatility spike: size halved" if multiplier < 1.0 else "normal",
    )
