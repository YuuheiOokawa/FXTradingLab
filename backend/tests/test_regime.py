import numpy as np
import pandas as pd

from app.services.regime import classify_regime


def _df(close, high=None, low=None):
    close = pd.Series(close)
    high = pd.Series(high) if high is not None else close + 0.3
    low = pd.Series(low) if low is not None else close - 0.3
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close})


def test_strong_uptrend_classified_as_uptrend():
    close = np.linspace(100, 160, 250)
    result = classify_regime(_df(close))
    assert result.trend == "UPTREND"


def test_strong_downtrend_classified_as_downtrend():
    close = np.linspace(160, 100, 250)
    result = classify_regime(_df(close))
    assert result.trend == "DOWNTREND"


def test_flat_noisy_series_classified_as_range():
    rng = np.random.default_rng(3)
    close = 100 + rng.normal(0, 0.05, 250)
    result = classify_regime(_df(close))
    assert result.trend == "RANGE"


def test_insufficient_data_is_unknown():
    close = np.linspace(100, 101, 10)
    result = classify_regime(_df(close))
    assert result.trend == "UNKNOWN"


def test_high_volatility_detected_after_range_expansion():
    # A short volatility burst (well under the 50-bar trailing ATR-average window)
    # should read as HIGH_VOLATILITY; a burst spanning the whole averaging window
    # just becomes the new "normal" baseline, which is correct trailing-average
    # behavior, not what this test is checking.
    rng = np.random.default_rng(5)
    calm = 100 + rng.normal(0, 0.05, 200)
    volatile = 100 + rng.normal(0, 2.0, 10)
    close = np.concatenate([calm, volatile])
    high = close + np.concatenate([np.full(200, 0.1), np.full(10, 3.0)])
    low = close - np.concatenate([np.full(200, 0.1), np.full(10, 3.0)])
    result = classify_regime(_df(close, high, low))
    assert result.volatility == "HIGH_VOLATILITY"
