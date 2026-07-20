"""Market regime classification (docs/08_SIGNAL_ENGINE.md).

Trend and volatility are tracked as two independent axes — a market can be
UPTREND + HIGH_VOLATILITY simultaneously — rather than collapsed into one enum.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from app.services.indicators import adx, atr, ema

TrendRegime = Literal["UPTREND", "DOWNTREND", "RANGE", "UNKNOWN"]
VolatilityRegime = Literal["HIGH_VOLATILITY", "LOW_VOLATILITY", "NORMAL"]


@dataclass
class RegimeResult:
    trend: TrendRegime
    volatility: VolatilityRegime
    adx_value: float
    atr_value: float
    atr_avg: float


def classify_regime(df: pd.DataFrame, adx_period: int = 14, atr_period: int = 14) -> RegimeResult:
    """`df` must have `open`, `high`, `low`, `close` columns, oldest-first."""
    if len(df) < max(adx_period, atr_period) * 3:
        return RegimeResult("UNKNOWN", "NORMAL", float("nan"), float("nan"), float("nan"))

    adx_series, _plus_di, _minus_di = adx(df["high"], df["low"], df["close"], adx_period)
    atr_series = atr(df["high"], df["low"], df["close"], atr_period)
    ema50 = ema(df["close"], 50)

    adx_value = float(adx_series.iloc[-1])
    atr_value = float(atr_series.iloc[-1])
    atr_avg = float(atr_series.rolling(50, min_periods=10).mean().iloc[-1])

    if pd.isna(ema50.iloc[-1]) or pd.isna(ema50.iloc[-6]):
        ema_slope = 0.0
    else:
        ema_slope = float(ema50.iloc[-1] - ema50.iloc[-6])

    if pd.isna(adx_value):
        trend: TrendRegime = "UNKNOWN"
    elif adx_value >= 25 and ema_slope > 0:
        trend = "UPTREND"
    elif adx_value >= 25 and ema_slope < 0:
        trend = "DOWNTREND"
    elif adx_value < 20:
        trend = "RANGE"
    else:
        trend = "UNKNOWN"

    if pd.isna(atr_avg) or atr_avg == 0:
        volatility: VolatilityRegime = "NORMAL"
    elif atr_value > 1.5 * atr_avg:
        volatility = "HIGH_VOLATILITY"
    elif atr_value < 0.5 * atr_avg:
        volatility = "LOW_VOLATILITY"
    else:
        volatility = "NORMAL"

    return RegimeResult(trend=trend, volatility=volatility, adx_value=adx_value, atr_value=atr_value, atr_avg=atr_avg)
