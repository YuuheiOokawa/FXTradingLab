"""Walk-Forward Analysis (docs/09_BACKTEST_DESIGN.md, docs/14_IMPLEMENTATION_PLAN.md).

Structural/property tests over generated data, same approach as
test_backtest.py's full-engine test — a literal expected window-by-window
trade list would be too brittle to maintain.
"""
from datetime import UTC, datetime

from app.brokers.mock import generate_candles
from app.brokers.schemas import Granularity
from app.services.backtest.walk_forward import ParamGrid, WalkForwardConfig, run_walk_forward

SMALL_GRID = ParamGrid(stop_loss_pips=[20.0, 30.0], take_profit_pips=[40.0, 60.0], min_score_threshold=[60])


def _config(**overrides) -> WalkForwardConfig:
    defaults = dict(
        pair="USD_JPY",
        timeframe=Granularity.M15,
        train_bars=300,
        test_bars=100,
        param_grid=SMALL_GRID,
    )
    defaults.update(overrides)
    return WalkForwardConfig(**defaults)


def test_produces_at_least_two_rolled_windows_given_enough_candles():
    end = datetime.now(UTC)
    # WARMUP(260) + train(300) + test(100) = 660/window, step=test_bars=100 ->
    # window 0 needs candles[0:660], window 1 needs candles[100:760]; give enough
    # for exactly 2 windows plus a partial third that must NOT appear.
    candles = generate_candles("USD_JPY", Granularity.M15, 900, end)

    result = run_walk_forward(_config(), candles)

    assert len(result.windows) == 3  # cursors 0, 100, 200 all fit within 900 candles (200+660=860<=900)
    for i, w in enumerate(result.windows):
        assert w.window_index == i
        assert w.train_start < w.train_end < w.test_start < w.test_end
        assert w.chosen_params["stop_loss_pips"] in SMALL_GRID.stop_loss_pips
        assert w.chosen_params["take_profit_pips"] in SMALL_GRID.take_profit_pips
        assert len(w.candidates_evaluated) == 4  # 2 x 2 x 1 grid


def test_windows_roll_forward_by_step_bars_not_overlapping_by_default():
    end = datetime.now(UTC)
    candles = generate_candles("USD_JPY", Granularity.M15, 900, end)
    result = run_walk_forward(_config(), candles)

    # Window k's test period should start after window k-1's test period starts —
    # confirms the cursor actually advances rather than re-running the same slice.
    for prev, cur in zip(result.windows, result.windows[1:]):
        assert cur.test_start > prev.test_start


def test_no_window_produced_when_not_enough_candles():
    end = datetime.now(UTC)
    candles = generate_candles("USD_JPY", Granularity.M15, 500, end)  # < 660 needed for one window

    result = run_walk_forward(_config(), candles)

    assert result.windows == []
    assert result.combined_test_metrics["trade_count"] == 0
    assert result.overfitting_warning is not None  # explains why: no window fit


def test_combined_test_metrics_only_reflect_out_of_sample_segments():
    end = datetime.now(UTC)
    candles = generate_candles("USD_JPY", Granularity.M15, 900, end)
    result = run_walk_forward(_config(), candles)

    total_test_trades_from_windows = sum(w.test_metrics["trade_count"] for w in result.windows)
    assert result.combined_test_metrics["trade_count"] == total_test_trades_from_windows


def test_parameter_stability_flags_the_majority_chosen_value():
    end = datetime.now(UTC)
    candles = generate_candles("USD_JPY", Granularity.M15, 900, end)
    result = run_walk_forward(_config(), candles)

    param_names = {s.param for s in result.parameter_stability}
    assert param_names == {"stop_loss_pips", "take_profit_pips", "min_score_threshold"}
    for s in result.parameter_stability:
        assert len(s.values_by_window) == len(result.windows)
        assert 0.0 < s.agreement_ratio <= 1.0
        # min_score_threshold has only one candidate value in SMALL_GRID, so every
        # window must agree on it by construction — a solid sanity check.
        if s.param == "min_score_threshold":
            assert s.agreement_ratio == 1.0
            assert s.is_stable is True


def test_never_exposes_a_single_recommended_production_config():
    """Hard requirement from the spec this implements: the result object must
    not contain any field that reads as 'apply this'. Walk-forward reports
    per-window choices and their untouched-test-window performance only."""
    end = datetime.now(UTC)
    candles = generate_candles("USD_JPY", Granularity.M15, 900, end)
    result = run_walk_forward(_config(), candles)

    result_field_names = {f for f in result.__dataclass_fields__}
    forbidden = {"recommended_params", "best_params", "suggested_config", "adopt"}
    assert not (result_field_names & forbidden)
    assert "disclaimer" in result_field_names
    assert "never applies" in result.disclaimer.lower()
