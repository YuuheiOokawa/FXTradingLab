"""Backtest engine tests. `test_sl_hit_before_tp_when_both_touched_intrabar` and
the P&L arithmetic tests are "golden" fixed-number tests (exact expected values);
the full-engine tests are structural/property tests over generated data, since a
literal expected trade list for a multi-hundred-bar run would be too brittle to
maintain (docs/09_BACKTEST_DESIGN.md, docs/13_TEST_STRATEGY.md).
"""
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.brokers.mock import generate_candles
from app.brokers.schemas import Granularity
from app.services.backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    TradeRecord,
    closed_higher_tf_window,
    pip_size_for,
)
from app.services.backtest.metrics import compute_metrics


def test_pip_size_jpy_vs_other():
    assert pip_size_for("USD_JPY") == 0.01
    assert pip_size_for("EUR_USD") == 0.0001


def test_sl_hit_before_tp_when_both_touched_intrabar():
    """Conservative assumption documented in 09_BACKTEST_DESIGN.md: if a single
    bar's range covers both SL and TP, SL is assumed to trigger first."""
    config = BacktestConfig(pair="USD_JPY", timeframe=Granularity.M15, spread_pips=0, slippage_pips=0)
    engine = BacktestEngine(config)
    position = TradeRecord(
        segment="in_sample",
        direction="BUY",
        entry_time=datetime.now(UTC),
        entry_price=150.0,
        size=1000,
        stop_loss=149.5,
        take_profit=151.0,
    )
    # A bar whose range spans both the SL and the TP.
    row = pd.Series({"open_time": datetime.now(UTC), "open": 150.0, "high": 151.5, "low": 149.0, "close": 150.2})
    updated, balance, trail, closed = engine._update_open_position(position, row, balance=0.0, trail_extreme=None)
    assert closed is True
    assert updated.exit_reason == "SL hit"
    assert updated.exit_price == 149.5


def test_pnl_arithmetic_buy_and_sell():
    config = BacktestConfig(pair="USD_JPY", timeframe=Granularity.M15, commission_per_lot=0)
    engine = BacktestEngine(config)
    buy = TradeRecord(
        segment="in_sample", direction="BUY", entry_time=datetime.now(UTC), entry_price=150.0, size=1000,
        stop_loss=None, take_profit=None,
    )
    assert engine._pnl(buy, 151.0) == pytest.approx(1000.0)  # +1.0 * 1000 units
    sell = TradeRecord(
        segment="in_sample", direction="SELL", entry_time=datetime.now(UTC), entry_price=150.0, size=1000,
        stop_loss=None, take_profit=None,
    )
    assert engine._pnl(sell, 149.0) == pytest.approx(1000.0)  # price fell -> SELL profits
    assert engine._pnl(sell, 151.0) == pytest.approx(-1000.0)


def test_metrics_on_known_trade_list():
    trades = [
        TradeRecord(segment="in_sample", direction="BUY", entry_time=datetime.now(UTC), entry_price=100,
                    size=1, stop_loss=None, take_profit=None, exit_price=110, pnl=1000.0),
        TradeRecord(segment="in_sample", direction="BUY", entry_time=datetime.now(UTC), entry_price=100,
                    size=1, stop_loss=None, take_profit=None, exit_price=90, pnl=-500.0),
        TradeRecord(segment="in_sample", direction="BUY", entry_time=datetime.now(UTC), entry_price=100,
                    size=1, stop_loss=None, take_profit=None, exit_price=105, pnl=500.0),
    ]
    equity_curve = [{"time": "t0", "equity": 100_000}, {"time": "t1", "equity": 99_500}, {"time": "t2", "equity": 101_000}]
    metrics = compute_metrics(trades, initial_capital=100_000, equity_curve=equity_curve)
    assert metrics["trade_count"] == 3
    assert metrics["total_pnl"] == pytest.approx(1000.0)
    assert metrics["win_rate_pct"] == pytest.approx(2 / 3 * 100, abs=0.01)
    assert metrics["profit_factor"] == pytest.approx(1500 / 500)
    assert metrics["max_consecutive_wins"] == 1
    assert metrics["max_consecutive_losses"] == 1


def test_metrics_empty_trade_list_does_not_crash():
    metrics = compute_metrics([], initial_capital=100_000, equity_curve=[])
    assert metrics["trade_count"] == 0
    assert metrics["win_rate_pct"] == 0.0
    assert metrics["profit_factor"] == 0.0


def test_full_engine_run_produces_consistent_structure():
    end = datetime.now(UTC)
    candles = generate_candles("USD_JPY", Granularity.M15, 900, end)
    h1 = generate_candles("USD_JPY", Granularity.H1, 900, end)
    h4 = generate_candles("USD_JPY", Granularity.H4, 900, end)

    config = BacktestConfig(pair="USD_JPY", timeframe=Granularity.M15, in_sample_ratio=0.7)
    result = BacktestEngine(config).run(candles, {"H1": h1, "H4": h4})

    assert len(result.equity_curve) == len(candles)
    is_count = sum(1 for t in result.trades if t.segment == "in_sample")
    oos_count = sum(1 for t in result.trades if t.segment == "out_of_sample")
    assert is_count + oos_count == len(result.trades)
    for t in result.trades:
        assert t.exit_price is not None
        assert t.entry_reasons  # every trade records why it entered
    for key in ("overall", "in_sample", "out_of_sample"):
        assert key in result.summary
        assert "max_drawdown_pct" in result.summary[key]
        assert result.summary[key]["max_drawdown_pct"] >= 0


def test_trailing_stop_moves_only_in_favorable_direction():
    # trailing_stop_pips=10 on USD_JPY (pip=0.01) means a 0.10 trail distance; each
    # bar's own high-low range is kept below that so the trail update computed from
    # this bar's high can't be immediately violated by this same bar's low — mixing
    # those would test intrabar path ambiguity (see the SL-vs-TP test above), not
    # the "never loosens" property this test is actually checking.
    config = BacktestConfig(pair="USD_JPY", timeframe=Granularity.M15, trailing_stop_pips=10, spread_pips=0, slippage_pips=0)
    engine = BacktestEngine(config)
    position = TradeRecord(
        segment="in_sample", direction="BUY", entry_time=datetime.now(UTC), entry_price=150.0,
        size=1000, stop_loss=149.5, take_profit=155.0,
    )
    row_up = pd.Series({"open_time": datetime.now(UTC), "open": 150.0, "high": 150.12, "low": 150.05, "close": 150.10})
    position, _, trail, closed = engine._update_open_position(position, row_up, balance=0.0, trail_extreme=150.0)
    assert closed is False
    assert position.stop_loss == pytest.approx(150.12 - 0.10)  # trail = high - 10 pips

    tighter_stop = position.stop_loss
    row_down = pd.Series({"open_time": datetime.now(UTC), "open": 150.10, "high": 150.08, "low": 150.05, "close": 150.06})
    position, _, trail, closed = engine._update_open_position(position, row_down, balance=0.0, trail_extreme=trail)
    assert closed is False
    assert position.stop_loss == tighter_stop  # must not loosen when price pulls back


def test_closed_higher_tf_window_excludes_the_still_forming_bar():
    """Regression test for a real look-ahead bug (docs/15_PRODUCTION_READINESS_REVIEW.md):
    a higher-timeframe bar's OHLC always represents its true final close (no
    partial-bar simulation), so a bar that has not yet closed relative to the
    entry-bar time must never be included in the window handed to the signal
    engine — doing so would leak that bar's eventual close into a decision made
    before it actually happened."""
    h1_df = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2026-01-01T13:00:00Z", "2026-01-01T14:00:00Z", "2026-01-01T15:00:00Z"]),
            "close": [150.0, 151.0, 999.0],  # the 15:00 bar's close must never leak into a 14:15 decision
        }
    )
    h1_times = h1_df["open_time"].to_numpy()
    duration = pd.Timedelta(hours=1)

    # Entry bar at 14:15 — the 14:00 H1 bar is still forming (closes at 15:00),
    # so only the 13:00 bar has actually closed by then.
    entry_time = pd.Timestamp("2026-01-01T14:15:00Z")
    window = closed_higher_tf_window(h1_df, h1_times, duration, entry_time)
    assert window is not None
    assert list(window["close"]) == [150.0]

    # Entry bar at 15:00 exactly — now the 14:00 bar has fully closed (its
    # close time 15:00 <= entry time 15:00) and becomes usable; the 15:00 bar
    # itself has just opened and is excluded.
    entry_time_2 = pd.Timestamp("2026-01-01T15:00:00Z")
    window_2 = closed_higher_tf_window(h1_df, h1_times, duration, entry_time_2)
    assert list(window_2["close"]) == [150.0, 151.0]

    # Before any H1 bar has closed at all.
    entry_time_3 = pd.Timestamp("2026-01-01T13:30:00Z")
    window_3 = closed_higher_tf_window(h1_df, h1_times, duration, entry_time_3)
    assert window_3 is None
