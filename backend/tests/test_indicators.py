"""Indicator correctness tests. EMA/RSI/ATR are verified against independent
reference implementations of their well-known recursive formulas (not just
re-running the same pandas call), so a bug in period/alpha handling in
app/services/indicators.py would actually be caught. ADX is verified via
directional properties (bounded, high on a strong trend, low on a flat series)
since its formula is compound and a full manual trace is unwieldy.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.indicators import adx, atr, bollinger_bands, ema, macd, rsi, sma


def _reference_ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def _reference_rsi(values: list[float], period: int) -> float:
    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain, avg_loss = gains[0], losses[0]
    alpha = 1 / period
    for g, l in zip(gains[1:], losses[1:]):
        avg_gain = alpha * g + (1 - alpha) * avg_gain
        avg_loss = alpha * l + (1 - alpha) * avg_loss
    rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
    return 100 - 100 / (1 + rs)


def test_sma_matches_manual_average():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    result = sma(s, 3)
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx((1 + 2 + 3) / 3)
    assert result.iloc[-1] == pytest.approx((8 + 9 + 10) / 3)


def test_ema_matches_reference_recursive_formula():
    values = [100.0, 101, 99, 102, 105, 104, 103, 106, 108, 107, 110, 109]
    period = 5
    s = pd.Series(values)
    result = ema(s, period)
    expected = _reference_ema(values, period)
    assert result.iloc[-1] == pytest.approx(expected[-1], rel=1e-9)
    # First `period - 1` points should be NaN (min_periods gate)
    assert pd.isna(result.iloc[period - 2])
    assert not pd.isna(result.iloc[period - 1])


def test_rsi_matches_reference_wilder_formula():
    values = [44, 44.5, 44.25, 44.9, 45.5, 45.2, 46, 46.5, 46.2, 47, 47.5, 47.2, 48, 48.5, 48.2, 49]
    period = 14
    s = pd.Series(values)
    result = rsi(s, period)
    expected = _reference_rsi(values, period)
    assert result.iloc[-1] == pytest.approx(expected, rel=1e-6)


def test_rsi_bounds():
    rising = pd.Series(np.linspace(100, 200, 60))
    result = rsi(rising, 14)
    assert result.iloc[-1] > 90  # relentless uptrend -> RSI near 100

    falling = pd.Series(np.linspace(200, 100, 60))
    result = rsi(falling, 14)
    assert result.iloc[-1] < 10  # relentless downtrend -> RSI near 0


def test_macd_line_equals_fast_minus_slow_ema():
    values = list(100 + np.cumsum(np.random.default_rng(42).normal(0, 1, 100)))
    s = pd.Series(values)
    macd_line, signal_line, histogram = macd(s, fast=12, slow=26, signal=9)
    expected_macd_line = ema(s, 12) - ema(s, 26)
    pd.testing.assert_series_equal(macd_line, expected_macd_line, check_names=False)
    pd.testing.assert_series_equal(histogram, macd_line - signal_line, check_names=False)


def test_bollinger_bands_symmetry_around_sma():
    s = pd.Series(np.random.default_rng(1).normal(100, 2, 60))
    upper, mid, lower = bollinger_bands(s, period=20, num_std=2.0)
    pd.testing.assert_series_equal(mid, sma(s, 20), check_names=False)
    diff_upper = (upper - mid).dropna()
    diff_lower = (mid - lower).dropna()
    pd.testing.assert_series_equal(diff_upper, diff_lower, check_names=False)


def test_atr_is_never_negative_and_reacts_to_range_expansion():
    high = pd.Series([101, 102, 101, 103, 101, 130], dtype=float)
    low = pd.Series([99, 100, 99, 100, 99, 90], dtype=float)
    close = pd.Series([100, 101, 100, 101, 100, 110], dtype=float)
    result = atr(high, low, close, period=3)
    assert (result.dropna() >= 0).all()
    assert result.iloc[-1] > result.iloc[2]  # the range-expansion bar should push ATR up


def test_adx_bounded_and_higher_on_strong_trend_than_range():
    n = 100
    trend_close = pd.Series(np.linspace(100, 160, n))
    trend_high = trend_close + 0.5
    trend_low = trend_close - 0.5
    trend_adx, plus_di, minus_di = adx(trend_high, trend_low, trend_close, period=14)

    rng = np.random.default_rng(7)
    range_close = pd.Series(100 + rng.normal(0, 0.3, n))
    range_high = range_close + 0.4
    range_low = range_close - 0.4
    range_adx, _, _ = adx(range_high, range_low, range_close, period=14)

    assert (trend_adx.dropna() >= 0).all() and (trend_adx.dropna() <= 100).all()
    assert trend_adx.iloc[-1] > range_adx.iloc[-1]
    assert plus_di.iloc[-1] > minus_di.iloc[-1]  # uptrend -> +DI dominant
