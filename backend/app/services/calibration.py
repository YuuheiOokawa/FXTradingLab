"""Measure an instrument's character and recommend a playbook style for it.

Adding a pair to the watchlist used to mean guessing which strategy suits it.
This reproduces the measurement that produced the shipped playbook
(app/services/playbook.py) so the guess becomes a reading:

* **Variance ratio** VR(q) = Var(q-day returns) / (q x Var(1-day returns)).
  Above 1 the market keeps going (momentum pays); below 1 it snaps back (fading
  extremes pays). Over 23 years USD/JPY measured .76, EUR/JPY .77, EUR/USD .82,
  GBP/JPY 1.10 — which is exactly why one shared trend-following rule lost money
  on the book as a whole.
* **ADX** for how much of the time a trend is actually present, which sets the
  regime gate.
* **Realised volatility / ATR** for how wide stops have to be.

The recommendation is a starting point for a backtest, NOT a licence to trade.
Choosing a style from a statistic and skipping validation is how curve-fits get
deployed; `confidence` and `warnings` say so explicitly when the sample is thin.

**How much to trust it, concretely.** Run on the same 23 years the shipped book
was fitted to, this module recommends a Bollinger fade for USD/JPY and a trend
follower for GBP/JPY. The actual backtests found the opposite on both — USD/JPY
does best on breakouts and GBP/JPY on fades. The variance ratio narrowed the
search; it did not pick the winner. Treat the output as "test this family
first", never as a configuration to enable.

A pair's character is also not a constant. USD/JPY measured VR(20) = 1.12 over
1996-2003 and 0.75 over 2003-2026 — trending in one era, mean reverting in the
next. A style chosen from one window inherits that window's regime along with
its statistics, so validate across eras, not just across a longer single span.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.services.indicators import adx, atr
from app.services.playbook import StyleName

# Below this many daily bars a variance ratio is not a measurement, it is noise.
MIN_BARS_FOR_CALIBRATION = 500
# ~4 years of daily bars before the reading is worth acting on. The shipped book
# was fitted on ~5,900 bars per pair; anything near the minimum is provisional.
BARS_FOR_HIGH_CONFIDENCE = 1000

# VR is noisy; require a clear departure from 1.0 before calling a regime.
VR_TREND_THRESHOLD = 1.05
VR_REVERT_THRESHOLD = 0.95


@dataclass(frozen=True)
class Calibration:
    instrument: str
    bars: int
    annual_vol_pct: float
    median_atr: float
    variance_ratio_5: float
    variance_ratio_20: float
    variance_ratio_60: float
    median_adx: float
    trending_share_pct: float   # share of days with ADX >= 25
    drift_pct_per_year: float
    character: str              # "trending" | "mean_reverting" | "neutral"
    recommended_style: StyleName
    recommended_adx_min: float | None
    recommended_adx_max: float | None
    recommended_stop_atr: float
    confidence: str             # "low" | "medium" | "high"
    warnings: list[str]
    rationale: str


def variance_ratio(log_returns: np.ndarray, q: int) -> float:
    r = log_returns[~np.isnan(log_returns)]
    usable = len(r) // q * q
    if usable < q * 2:
        return float("nan")
    r = r[:usable]
    one = r.var(ddof=1)
    if one <= 0:
        return float("nan")
    return float(r.reshape(-1, q).sum(axis=1).var(ddof=1) / (q * one))


def _character(vr60: float) -> str:
    if vr60 != vr60:
        return "neutral"
    if vr60 >= VR_TREND_THRESHOLD:
        return "trending"
    if vr60 <= VR_REVERT_THRESHOLD:
        return "mean_reverting"
    return "neutral"


def calibrate(instrument: str, df: pd.DataFrame) -> Calibration | None:
    """Measure `instrument` from daily OHLC. Returns None if history is too short."""
    if len(df) < MIN_BARS_FOR_CALIBRATION:
        return None

    close, high, low = df["close"], df["high"], df["low"]
    logret = np.log(close.astype(float)).diff().to_numpy()

    vr5 = variance_ratio(logret, 5)
    vr20 = variance_ratio(logret, 20)
    vr60 = variance_ratio(logret, 60)

    adx_series = adx(high, low, close, 14)[0].dropna()
    median_adx = float(adx_series.median()) if len(adx_series) else float("nan")
    trending_share = float((adx_series >= 25).mean() * 100) if len(adx_series) else 0.0

    ann_vol = float(np.nanstd(logret) * np.sqrt(252) * 100)
    median_atr = float(atr(high, low, close, 14).median())
    years = max(len(df) / 252.0, 1e-9)
    drift = float(np.log(close.iloc[-1] / close.iloc[0]) / years * 100)

    character = _character(vr60)
    warnings: list[str] = []

    # Style follows character; the fade styles are gated by an ADX ceiling and
    # the trend styles by a floor, matching how the shipped book is configured.
    if character == "trending":
        style: StyleName = "trend_filtered_trail"
        adx_min: float | None = 15.0
        adx_max: float | None = None
        stop_atr = 3.0
        rationale = (
            f"VR(60)={vr60:.2f} > {VR_TREND_THRESHOLD}: moves persist, so ride them with a "
            "trailing stop and only trade with the longer-term trend."
        )
    elif character == "mean_reverting":
        style = "bollinger_fade"
        adx_min = None
        adx_max = 30.0
        stop_atr = 3.0
        rationale = (
            f"VR(60)={vr60:.2f} < {VR_REVERT_THRESHOLD}: moves snap back, so fade band "
            "extremes and take profit at the mean — but only while ADX says no strong trend."
        )
    else:
        style = "breakout_trail"
        adx_min = 20.0
        adx_max = None
        stop_atr = 2.0
        rationale = (
            f"VR(60)={vr60:.2f} is close to 1: no persistent edge either way, so take only "
            "clean breakouts and require a trend to already be underway."
        )
        warnings.append(
            "Character is neutral — this pair may simply have no exploitable edge. "
            "Treat a weak backtest as the expected outcome, not as a parameter to tune away."
        )

    # Volatility shapes the stop more than the style does.
    if ann_vol >= 13.0:
        stop_atr += 0.5
        warnings.append(f"High volatility ({ann_vol:.1f}%/yr): stop widened; size accordingly.")
    if trending_share < 20.0 and character == "trending":
        warnings.append(
            f"VR says trending but ADX>=25 only {trending_share:.0f}% of days — the trend "
            "signal is weak and the two measures disagree."
        )
    if abs(drift) > 5.0:
        warnings.append(
            f"Strong directional drift ({drift:+.1f}%/yr) over the sample. A long-only or "
            "short-only variant may test well purely because of it, and will fail if it reverses."
        )

    if len(df) >= BARS_FOR_HIGH_CONFIDENCE and vr60 == vr60:
        confidence = "high"
    elif len(df) >= MIN_BARS_FOR_CALIBRATION * 1.5:
        confidence = "medium"
    else:
        confidence = "low"
        warnings.append(
            f"Only {len(df)} bars (~{len(df)/252:.1f} years). Provisional — the shipped "
            "playbook was measured on ~23 years per pair."
        )

    return Calibration(
        instrument=instrument,
        bars=len(df),
        annual_vol_pct=round(ann_vol, 2),
        median_atr=round(median_atr, 5),
        variance_ratio_5=round(vr5, 3) if vr5 == vr5 else float("nan"),
        variance_ratio_20=round(vr20, 3) if vr20 == vr20 else float("nan"),
        variance_ratio_60=round(vr60, 3) if vr60 == vr60 else float("nan"),
        median_adx=round(median_adx, 1) if median_adx == median_adx else float("nan"),
        trending_share_pct=round(trending_share, 1),
        drift_pct_per_year=round(drift, 2),
        character=character,
        recommended_style=style,
        recommended_adx_min=adx_min,
        recommended_adx_max=adx_max,
        recommended_stop_atr=stop_atr,
        confidence=confidence,
        warnings=warnings,
        rationale=rationale,
    )


def to_dict(c: Calibration) -> dict:
    d = asdict(c)
    # NaN is not valid JSON; surface it as null rather than emitting bare NaN.
    for k, v in d.items():
        if isinstance(v, float) and v != v:
            d[k] = None
    d["next_step"] = (
        "Backtest this configuration on the pair's own history before enabling it. "
        "A recommendation derived from a statistic is a hypothesis, not a validated strategy."
    )
    return d
