"""Walk-Forward Analysis (docs/09_BACKTEST_DESIGN.md, docs/14_IMPLEMENTATION_PLAN.md).

Rolls a training/testing window forward across the candle series: for each
window, a small parameter grid is searched using ONLY the training slice
(`BacktestEngine`'s existing `in_sample` segment), the single best-on-training
candidate's already-computed `out_of_sample` segment becomes that window's
test-period result — untouched by the search — and the process repeats on
the next window. Reuses `BacktestEngine.run()` end-to-end per window rather
than adding a second execution path: docs/09 already documents that each
`run()` call gets its own in-sample/out-of-sample split "for free", so a
window's `in_sample_ratio` is simply set so the split lands exactly at the
train/test boundary.

Hard requirement from the spec this implements: this module NEVER selects
"the best overall parameters" for the caller to adopt in production — it
only ever reports what was chosen per training window and how those choices
performed on the immediately-following, never-optimized-against test window.
Turning any of this into a suggested live/paper trading config is a decision
a human makes after reading the parameter-stability and overfitting-warning
output below, not something this module does automatically.
"""
from __future__ import annotations

import itertools
import statistics
from dataclasses import dataclass, field
from datetime import datetime

from app.brokers.schemas import Candle
from app.services.backtest.engine import BacktestConfig, BacktestEngine, INDICATOR_WINDOW
from app.services.backtest.metrics import compute_metrics

WARMUP_BARS = INDICATOR_WINDOW  # leading context each window needs for indicator warmup, not counted as train/test


@dataclass
class ParamGrid:
    """Candidate values for each tunable parameter — a full cartesian product
    is searched per window. Keep this small: cost is
    `len(windows) * product(len(values) for each param)` full backtest runs."""

    stop_loss_pips: list[float] = field(default_factory=lambda: [20.0, 30.0, 40.0])
    take_profit_pips: list[float] = field(default_factory=lambda: [40.0, 60.0, 80.0])
    min_score_threshold: list[int] = field(default_factory=lambda: [55, 60, 65])

    def candidates(self) -> list[dict]:
        keys = ["stop_loss_pips", "take_profit_pips", "min_score_threshold"]
        value_lists = [getattr(self, k) for k in keys]
        return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]


@dataclass
class WalkForwardConfig:
    pair: str
    timeframe: str
    train_bars: int = 500
    test_bars: int = 150
    step_bars: int | None = None  # defaults to test_bars (non-overlapping windows)
    initial_capital: float = 1_000_000.0
    risk_pct: float = 1.0
    spread_pips: float = 1.5
    slippage_pips: float = 0.3
    commission_per_lot: float = 0.0
    param_grid: ParamGrid = field(default_factory=ParamGrid)

    def __post_init__(self) -> None:
        if self.step_bars is None:
            self.step_bars = self.test_bars


@dataclass
class WalkForwardWindowResult:
    window_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    chosen_params: dict
    train_metrics: dict
    test_metrics: dict
    candidates_evaluated: list[dict]  # every grid candidate's train total_pnl, for transparency


@dataclass
class ParameterStability:
    param: str
    values_by_window: list
    most_common_value: object
    agreement_ratio: float  # fraction of windows that chose the most common value
    is_stable: bool


@dataclass
class WalkForwardResult:
    windows: list[WalkForwardWindowResult]
    combined_test_metrics: dict
    combined_test_equity_curve: list[dict]
    parameter_stability: list[ParameterStability]
    overfitting_warning: str | None
    disclaimer: str = (
        "Walk-forward results describe how repeatedly re-optimizing on a "
        "training window and testing on the untouched period right after it "
        "would have performed historically. They are not a prediction and "
        "this tool never applies any of these parameters to paper or live "
        "trading automatically — that decision, if made at all, is yours."
    )


def _run_candidate(
    config: WalkForwardConfig,
    params: dict,
    window_candles: list[Candle],
    higher_tf_window: dict[str, list[Candle]],
    in_sample_ratio: float,
):
    bt_config = BacktestConfig(
        pair=config.pair,
        timeframe=config.timeframe,
        initial_capital=config.initial_capital,
        risk_pct=config.risk_pct,
        spread_pips=config.spread_pips,
        slippage_pips=config.slippage_pips,
        commission_per_lot=config.commission_per_lot,
        stop_loss_pips=params["stop_loss_pips"],
        take_profit_pips=params["take_profit_pips"],
        min_score_threshold=params["min_score_threshold"],
        in_sample_ratio=in_sample_ratio,
    )
    return BacktestEngine(bt_config).run(window_candles, higher_tf_window)


def run_walk_forward(
    config: WalkForwardConfig,
    candles: list[Candle],
    higher_tf_candles: dict[str, list[Candle]] | None = None,
) -> WalkForwardResult:
    higher_tf_candles = higher_tf_candles or {}
    total_window_bars = WARMUP_BARS + config.train_bars + config.test_bars
    # BacktestEngine computes its split index as int(len(df) * in_sample_ratio);
    # a bare (WARMUP_BARS+train_bars)/total ratio can round-trip through float
    # division/multiplication to one bar below the intended boundary. The +0.5
    # keeps the product comfortably inside [boundary, boundary+1) so int()
    # truncates to exactly WARMUP_BARS+train_bars regardless of float noise.
    in_sample_ratio = (WARMUP_BARS + config.train_bars + 0.5) / total_window_bars
    candidates = config.param_grid.candidates()

    windows: list[WalkForwardWindowResult] = []
    combined_trades = []
    combined_curve: list[dict] = []
    running_balance = config.initial_capital

    window_index = 0
    cursor = 0
    while cursor + total_window_bars <= len(candles):
        window_slice = candles[cursor : cursor + total_window_bars]
        window_times = [c.open_time for c in window_slice]
        train_start, train_end = window_times[WARMUP_BARS], window_times[WARMUP_BARS + config.train_bars - 1]
        test_start, test_end = window_times[WARMUP_BARS + config.train_bars], window_times[-1]

        higher_tf_window = {
            tf: [c for c in hc if window_times[0] <= c.open_time <= window_times[-1]]
            for tf, hc in higher_tf_candles.items()
        }

        best_result = None
        best_params = None
        best_train_pnl = float("-inf")
        candidates_evaluated = []
        for params in candidates:
            result = _run_candidate(config, params, window_slice, higher_tf_window, in_sample_ratio)
            train_pnl = result.summary["in_sample"]["total_pnl"]
            candidates_evaluated.append({**params, "train_total_pnl": train_pnl})
            if train_pnl > best_train_pnl:
                best_train_pnl = train_pnl
                best_result = result
                best_params = params

        assert best_result is not None and best_params is not None

        test_trades = [t for t in best_result.trades if t.segment == "out_of_sample"]
        test_curve = best_result.equity_curve[WARMUP_BARS + config.train_bars :] or best_result.equity_curve
        windows.append(
            WalkForwardWindowResult(
                window_index=window_index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                chosen_params=best_params,
                train_metrics=best_result.summary["in_sample"],
                test_metrics=best_result.summary["out_of_sample"],
                candidates_evaluated=candidates_evaluated,
            )
        )

        # Stitch this window's test-segment trades/equity onto the combined
        # walk-forward curve — this is the closest thing to "what would have
        # actually happened", since every point on it comes from a period the
        # parameter search never saw.
        combined_trades.extend(test_trades)
        for point in test_curve:
            running_balance = point["equity"]
            combined_curve.append(point)

        window_index += 1
        cursor += config.step_bars

    combined_test_metrics = compute_metrics(combined_trades, config.initial_capital, combined_curve or [{"equity": config.initial_capital}])
    stability = _compute_parameter_stability(windows)
    warning = _overfitting_warning(windows, combined_test_metrics, stability)

    return WalkForwardResult(
        windows=windows,
        combined_test_metrics=combined_test_metrics,
        combined_test_equity_curve=combined_curve,
        parameter_stability=stability,
        overfitting_warning=warning,
    )


def _compute_parameter_stability(windows: list[WalkForwardWindowResult]) -> list[ParameterStability]:
    if not windows:
        return []
    param_names = list(windows[0].chosen_params.keys())
    stability: list[ParameterStability] = []
    for name in param_names:
        values = [w.chosen_params[name] for w in windows]
        counts: dict = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        most_common_value, most_common_count = max(counts.items(), key=lambda kv: kv[1])
        agreement_ratio = most_common_count / len(values)
        stability.append(
            ParameterStability(
                param=name,
                values_by_window=values,
                most_common_value=most_common_value,
                agreement_ratio=round(agreement_ratio, 3),
                # Majority of windows agreeing on the same value is the bar for
                # "stable" — a different winner nearly every window is a classic
                # overfitting signature (the search is chasing training noise).
                is_stable=agreement_ratio >= 0.5,
            )
        )
    return stability


def _overfitting_warning(
    windows: list[WalkForwardWindowResult],
    combined_test_metrics: dict,
    stability: list[ParameterStability],
) -> str | None:
    if not windows:
        return "No complete window fit in the requested candle range — widen candle_count or shrink train/test bars."

    avg_train_pnl = statistics.mean(w.train_metrics["total_pnl"] for w in windows)
    combined_test_pnl = combined_test_metrics["total_pnl"]
    unstable_params = [s.param for s in stability if not s.is_stable]

    reasons = []
    # Training-period profit consistently far outstrips what the same chosen
    # parameters achieved on the untouched period right after — the textbook
    # walk-forward overfitting signature.
    if avg_train_pnl > 0 and combined_test_pnl < avg_train_pnl * 0.3:
        reasons.append(
            f"combined out-of-sample P/L ({combined_test_pnl:,.0f}) is far below the average "
            f"per-window in-sample P/L ({avg_train_pnl:,.0f}) the same chosen parameters achieved "
            "on their own training window"
        )
    if combined_test_metrics.get("profit_factor") is not None and combined_test_metrics["profit_factor"] < 1.0:
        reasons.append("combined out-of-sample profit factor is below 1.0 (net losing across all test windows)")
    if unstable_params:
        reasons.append(f"parameter selection is unstable across windows for: {', '.join(unstable_params)}")

    if not reasons:
        return None
    return (
        "Possible over-optimization detected: " + "; ".join(reasons) + ". "
        "Do not treat the per-window 'best' parameters as validated for live "
        "or paper trading without further scrutiny — see `parameter_stability` "
        "and each window's train vs. test metrics above."
    )
