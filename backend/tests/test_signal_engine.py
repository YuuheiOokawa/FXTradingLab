"""Signal Engine tests: synthetic OHLC series engineered to hit each scoring
branch (docs/13_TEST_STRATEGY.md), asserting expected score ranges and that the
reason list always explains the winning direction.
"""
import numpy as np
import pandas as pd

from app.services.signal_engine import compute_higher_tf_bias, evaluate


def _uptrend_df(n=260, noise=0.05, seed=1):
    rng = np.random.default_rng(seed)
    close = np.linspace(100, 140, n) + rng.normal(0, noise, n)
    high = close + 0.3
    low = close - 0.3
    open_ = close - 0.05
    return pd.DataFrame(
        {"open_time": pd.date_range("2025-01-01", periods=n, freq="h"), "open": open_, "high": high, "low": low, "close": close}
    )


def _downtrend_df(n=260, noise=0.05, seed=2):
    rng = np.random.default_rng(seed)
    close = np.linspace(140, 100, n) + rng.normal(0, noise, n)
    high = close + 0.3
    low = close - 0.3
    open_ = close + 0.05
    return pd.DataFrame(
        {"open_time": pd.date_range("2025-01-01", periods=n, freq="h"), "open": open_, "high": high, "low": low, "close": close}
    )


def _flat_df(n=260, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 + rng.normal(0, 0.05, n)
    high = close + 0.1
    low = close - 0.1
    return pd.DataFrame(
        {"open_time": pd.date_range("2025-01-01", periods=n, freq="h"), "open": close, "high": high, "low": low, "close": close}
    )


def test_clean_uptrend_scores_high_for_buy():
    df = _uptrend_df()
    result = evaluate(df, {"H4": _uptrend_df(seed=10), "H1": _uptrend_df(seed=11)})
    assert result.direction == "BUY"
    assert result.buy_score >= 55
    assert result.label in ("買い", "強い買い")
    assert result.buy_score > result.sell_score


def test_clean_downtrend_scores_high_for_sell():
    df = _downtrend_df()
    result = evaluate(df, {"H4": _downtrend_df(seed=20), "H1": _downtrend_df(seed=21)})
    assert result.direction == "SELL"
    assert result.sell_score >= 55
    assert result.label in ("売り", "強い売り")


def test_higher_timeframe_disagreement_penalizes_score():
    df = _uptrend_df()
    agreeing = evaluate(df, {"H4": _uptrend_df(seed=30), "H1": _uptrend_df(seed=31)})
    disagreeing = evaluate(df, {"H4": _downtrend_df(seed=32), "H1": _uptrend_df(seed=33)})
    assert disagreeing.buy_score < agreeing.buy_score


def test_flat_market_does_not_produce_a_strong_signal():
    df = _flat_df()
    result = evaluate(df, {})
    assert result.label not in ("強い買い", "強い売り")


def test_reasons_always_present_and_labeled():
    df = _uptrend_df()
    result = evaluate(df, {"H4": _uptrend_df(seed=40)})
    assert len(result.reasons) == 6  # trend, mtf, rsi, macd, bollinger, volatility
    for reason in result.reasons:
        assert reason.status in ("met", "partial", "failed")
        assert reason.text
        assert 0 <= reason.points <= 30


def test_compute_higher_tf_bias_insufficient_data_is_neutral():
    short_df = _uptrend_df(n=50)
    bias = compute_higher_tf_bias({"H4": short_df})
    assert bias["H4"] == "NEUTRAL"


def test_compute_higher_tf_bias_detects_up_and_down():
    up_bias = compute_higher_tf_bias({"H4": _uptrend_df(n=260)})
    down_bias = compute_higher_tf_bias({"H4": _downtrend_df(n=260)})
    assert up_bias["H4"] == "UP"
    assert down_bias["H4"] == "DOWN"
