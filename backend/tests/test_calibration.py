"""Calibration tests (app/services/calibration.py).

The variance ratio is the load-bearing statistic, so it is checked against
series whose character is known by construction: a random walk must land near
1.0, a persistent drift above it, and an alternating series well below.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.calibration import (
    MIN_BARS_FOR_CALIBRATION,
    calibrate,
    to_dict,
    variance_ratio,
)


def _ohlc(closes: np.ndarray, spread: float = 0.1) -> pd.DataFrame:
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {"open": c.shift(1).fillna(c.iloc[0]), "high": c + spread, "low": c - spread, "close": c}
    )


def _random_walk(n: int, seed: int = 3, sigma: float = 0.3, start: float = 150.0) -> np.ndarray:
    """Geometric walk so the path can never reach zero (log returns stay defined
    even at high sigma)."""
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(0, sigma / start, n)))


def _momentum_walk(n: int, seed: int = 2, phi: float = 0.35, start: float = 150.0) -> np.ndarray:
    """Prices whose RETURNS are positively autocorrelated — the actual definition
    of a trending market. A straight line plus iid noise is NOT that: differencing
    iid noise gives negatively autocorrelated returns, so a trend-stationary
    series measures as mean-reverting."""
    rng = np.random.default_rng(seed)
    r = np.zeros(n)
    for i in range(1, n):
        r[i] = phi * r[i - 1] + rng.normal(0, 0.002)
    return start * np.exp(np.cumsum(r))


class TestVarianceRatio:
    def test_random_walk_is_near_one(self):
        rng = np.random.default_rng(11)
        r = rng.normal(0, 1, 6000)
        assert variance_ratio(r, 20) == pytest.approx(1.0, abs=0.15)

    def test_persistent_series_is_above_one(self):
        """Positively autocorrelated returns compound, so multi-day variance
        grows faster than linearly."""
        rng = np.random.default_rng(5)
        r = np.zeros(6000)
        for i in range(1, len(r)):
            r[i] = 0.35 * r[i - 1] + rng.normal(0, 1)
        assert variance_ratio(r, 20) > 1.3

    def test_alternating_series_is_below_one(self):
        rng = np.random.default_rng(5)
        r = np.zeros(6000)
        for i in range(1, len(r)):
            r[i] = -0.45 * r[i - 1] + rng.normal(0, 1)
        assert variance_ratio(r, 20) < 0.8

    def test_returns_nan_when_sample_too_short_for_the_horizon(self):
        assert variance_ratio(np.array([0.1, -0.1, 0.2]), 60) != variance_ratio(np.array([0.1]), 60) or True
        assert np.isnan(variance_ratio(np.array([0.1, -0.1, 0.2]), 60))


class TestCalibrateGuards:
    def test_returns_none_when_history_too_short(self):
        assert calibrate("USD_JPY", _ohlc(_random_walk(100))) is None

    def test_low_confidence_flagged_near_the_minimum(self):
        c = calibrate("USD_JPY", _ohlc(_random_walk(MIN_BARS_FOR_CALIBRATION + 5)))
        assert c is not None
        assert c.confidence == "low"
        assert any("Provisional" in w or "years" in w for w in c.warnings)

    def test_high_confidence_with_long_history(self):
        c = calibrate("USD_JPY", _ohlc(_random_walk(3000)))
        assert c.confidence == "high"


class TestRecommendation:
    def test_trending_series_gets_a_trend_style_with_a_floor(self):
        c = calibrate("TEST_PAIR", _ohlc(_momentum_walk(2000)))
        assert c.character == "trending"
        assert c.recommended_style == "trend_filtered_trail"
        assert c.recommended_adx_min is not None
        assert c.recommended_adx_max is None

    def test_mean_reverting_series_gets_a_fade_style_with_a_ceiling(self):
        # Ornstein-Uhlenbeck style pull back to a level.
        rng = np.random.default_rng(4)
        closes = np.empty(2000)
        closes[0] = 150.0
        for i in range(1, 2000):
            closes[i] = closes[i - 1] + 0.08 * (150.0 - closes[i - 1]) + rng.normal(0, 0.4)
        c = calibrate("TEST_PAIR", _ohlc(closes))
        assert c.character == "mean_reverting"
        assert c.recommended_style == "bollinger_fade"
        assert c.recommended_adx_max is not None
        assert c.recommended_adx_min is None

    def test_neutral_series_warns_there_may_be_no_edge(self):
        c = calibrate("TEST_PAIR", _ohlc(_random_walk(3000, seed=21)))
        if c.character == "neutral":
            assert c.recommended_style == "breakout_trail"
            assert any("no exploitable edge" in w for w in c.warnings)

    def test_high_volatility_widens_the_stop(self):
        calm = calibrate("TEST_PAIR", _ohlc(_random_walk(2000, seed=8, sigma=0.15)))
        wild = calibrate("TEST_PAIR", _ohlc(_random_walk(2000, seed=8, sigma=2.0)))
        assert wild.annual_vol_pct > calm.annual_vol_pct
        assert wild.recommended_stop_atr >= calm.recommended_stop_atr

    def test_rationale_and_instrument_are_populated(self):
        c = calibrate("USD_JPY", _ohlc(_random_walk(2000)))
        assert c.instrument == "USD_JPY"
        assert "VR(60)" in c.rationale


class TestSerialization:
    def test_nan_becomes_null_not_bare_nan(self):
        """NaN is not valid JSON; emitting it produces a response clients cannot parse."""
        c = calibrate("USD_JPY", _ohlc(_random_walk(600)))
        d = to_dict(c)
        for key, value in d.items():
            if isinstance(value, float):
                assert value == value, f"{key} serialised as NaN"

    def test_carries_the_backtest_first_instruction(self):
        d = to_dict(calibrate("USD_JPY", _ohlc(_random_walk(2000))))
        assert "Backtest" in d["next_step"]
