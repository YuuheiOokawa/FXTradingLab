# 09. Backtest Design

## Engine shape

Event-driven, bar-by-bar (not vectorized-only), so exit logic (SL/TP/trailing) can
depend on intrabar high/low rather than only close — vectorized indicator computation
(pandas) feeds a simple bar loop for order simulation. This is slower than a pure
vectorized backtest but materially more correct for SL/TP behavior, and v1 data
volumes (single pair, up to a few years of M15+ candles) make performance a non-issue.

`app/services/backtest/engine.py::BacktestEngine.run(config) -> BacktestResult`

## Config

`pair, timeframe, date_from, date_to, initial_capital, position_size, risk_pct,
spread_pips, slippage_pips, commission_per_lot, strategy_config_id, stop_loss_pips,
take_profit_pips, trailing_stop_pips | null, in_sample_ratio (default 0.7)`.

## Simulation loop

For each closed candle in order:
1. Update indicator state (incremental, not recomputed from scratch).
2. If a position is open: check SL/TP/trailing against this bar's high/low
   (worst-case ordering: if both SL and TP would be hit intrabar, SL is assumed to
   trigger first — conservative default, documented in code).
3. If flat: evaluate `SignalEngine` for this bar; if score crosses the strategy's
   entry threshold, open a simulated position sized by `risk_pct` of current equity
   against the SL distance, applying `spread_pips` to the fill price and
   `slippage_pips` as an additional adverse offset.
4. Record equity after each bar (equity curve).

## In-sample / out-of-sample

`date_from..date_to` is split at `in_sample_ratio` into IS/OOS sub-ranges *before* the
loop runs; the engine runs both sub-ranges independently and returns two
`BacktestResult` summaries plus the combined equity curve, so a user can compare
IS vs OOS performance side by side rather than only seeing a single blended number
that hides overfitting. Walk-Forward Analysis is not implemented in v1; the engine's
`run_range()` primitive (single-range in/out) is the building block a future
`WalkForwardRunner` would call repeatedly over rolling windows — documented as the
extension point rather than built now.

## Metrics computed

Total P/L, return %, trade count, win rate, average win, average loss, profit factor
(`gross profit / abs(gross loss)`), Sharpe ratio (using per-trade or daily returns,
annualized with `sqrt(252)`), max drawdown (peak-to-trough on the equity curve), max
consecutive wins, max consecutive losses. All implemented in
`app/services/backtest/metrics.py` with unit tests against hand-computed fixtures.

## Trade rationale

Each `backtest_trades` row stores the `SignalResult.reasons` snapshot at entry (why it
entered) and a short structured exit reason (`"SL hit"`, `"TP hit"`, `"Trailing stop"`,
`"End of backtest — force closed"`). The frontend backtest trade list surfaces both
verbatim when a trade row is clicked — no re-derivation needed at render time.
