"""Signal Engine — the app's core "why is this a BUY/SELL" component
(docs/08_SIGNAL_ENGINE.md).

Produces a 0-100 score per direction with an itemized, human-readable reason list.
Never predicts the future — every output is framed as "what the configured
rule-based strategy currently says," per docs/01_REQUIREMENTS.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from app.services.indicators import bollinger_bands, ema, macd, rsi
from app.services.regime import RegimeResult, TrendRegime, classify_regime

Direction = Literal["BUY", "SELL"]
ReasonStatus = Literal["met", "partial", "failed"]
Label = Literal["強い買い", "買い", "様子見", "売り", "強い売り"]

HigherTFBias = Literal["UP", "DOWN", "NEUTRAL"]


@dataclass
class Reason:
    status: ReasonStatus
    text: str
    points: int


@dataclass
class SignalResult:
    direction: Direction
    score: int
    label: Label
    regime: RegimeResult
    reasons: list[Reason]
    buy_score: int
    sell_score: int


def _clip(points: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, round(points))))


def _trend_component(price: float, ema20: float, ema50: float, ema200: float, direction: Direction) -> Reason:
    if any(pd.isna(x) for x in (price, ema20, ema50, ema200)):
        return Reason("failed", "EMAデータ不足", 0)
    if direction == "BUY":
        conditions = [ema20 > ema50, ema50 > ema200, price > ema20]
        if all(conditions):
            return Reason("met", "EMA20 > EMA50 > EMA200 かつ価格 > EMA20", 30)
        met_count = sum(conditions)
        if met_count > 0:
            return Reason("partial", f"EMA配列は部分的に上昇型 ({met_count}/3条件成立)", min(10 * met_count, 25))
        return Reason("failed", "EMA配列は上昇シグナルなし", 0)
    else:
        conditions = [ema20 < ema50, ema50 < ema200, price < ema20]
        if all(conditions):
            return Reason("met", "EMA20 < EMA50 < EMA200 かつ価格 < EMA20", 30)
        met_count = sum(conditions)
        if met_count > 0:
            return Reason("partial", f"EMA配列は部分的に下降型 ({met_count}/3条件成立)", min(10 * met_count, 25))
        return Reason("failed", "EMA配列は下降シグナルなし", 0)


def _mtf_component(higher_tf_bias: dict[str, HigherTFBias], direction: Direction) -> Reason:
    if not higher_tf_bias:
        return Reason("partial", "上位足データなし", 10)
    want: HigherTFBias = "UP" if direction == "BUY" else "DOWN"
    opp: HigherTFBias = "DOWN" if direction == "BUY" else "UP"
    agree = sum(1 for b in higher_tf_bias.values() if b == want)
    disagree = any(b == opp for b in higher_tf_bias.values())
    total = len(higher_tf_bias)
    detail = ", ".join(f"{tf}:{b}" for tf, b in higher_tf_bias.items())
    if disagree:
        return Reason("failed", f"上位足との方向が不一致 ({detail})", 0)
    if agree == total:
        return Reason("met", f"上位足はすべて{'上昇' if direction == 'BUY' else '下降'}トレンドと一致 ({detail})", 20)
    if agree > 0:
        return Reason("partial", f"上位足の一部が一致 ({detail})", 10)
    return Reason("partial", f"上位足は明確なトレンドなし ({detail})", 5)


def _rsi_component(rsi_series: pd.Series, direction: Direction) -> Reason:
    if len(rsi_series) < 7 or pd.isna(rsi_series.iloc[-1]):
        return Reason("failed", "RSIデータ不足", 0)
    latest = float(rsi_series.iloc[-1])
    prev = float(rsi_series.iloc[-2])
    window = rsi_series.iloc[-6:-1]
    if direction == "BUY":
        crossed = bool((window <= 30).any()) and latest > 30 and latest > prev
        if crossed:
            return Reason("met", f"RSIが30以下から上向きへ転換 (RSI {latest:.1f})", 15)
        if latest < 70:
            return Reason("partial", f"RSIは過熱していない (RSI {latest:.1f})", 7)
        return Reason("failed", f"RSI過熱気味 (RSI {latest:.1f})", 0)
    else:
        crossed = bool((window >= 70).any()) and latest < 70 and latest < prev
        if crossed:
            return Reason("met", f"RSIが70以上から下向きへ転換 (RSI {latest:.1f})", 15)
        if latest > 30:
            return Reason("partial", f"RSIは売られ過ぎていない (RSI {latest:.1f})", 7)
        return Reason("failed", f"RSI売られ過ぎ (RSI {latest:.1f})", 0)


def _macd_component(
    macd_line: pd.Series, signal_line: pd.Series, histogram: pd.Series, direction: Direction
) -> Reason:
    if len(macd_line) < 2 or pd.isna(macd_line.iloc[-1]) or pd.isna(signal_line.iloc[-1]):
        return Reason("failed", "MACDデータ不足", 0)
    m, s = float(macd_line.iloc[-1]), float(signal_line.iloc[-1])
    pm, ps = float(macd_line.iloc[-2]), float(signal_line.iloc[-2])
    hist_rising = bool(histogram.iloc[-1] > histogram.iloc[-2]) if len(histogram) >= 2 else False
    if direction == "BUY":
        golden_cross = pm <= ps and m > s
        if golden_cross and hist_rising:
            return Reason("met", "MACDゴールデンクロス", 15)
        if m > s:
            return Reason("partial", "MACDは買い方向 (シグナル線より上)", 8)
        return Reason("failed", "MACDは売り方向", 0)
    else:
        dead_cross = pm >= ps and m < s
        if dead_cross and not hist_rising:
            return Reason("met", "MACDデッドクロス", 15)
        if m < s:
            return Reason("partial", "MACDは売り方向 (シグナル線より下)", 8)
        return Reason("failed", "MACDは買い方向", 0)


def _bollinger_component(
    price: float, upper: float, mid: float, lower: float, trend_regime: TrendRegime, direction: Direction
) -> Reason:
    if any(pd.isna(x) for x in (price, upper, mid, lower)):
        return Reason("partial", "ボリンジャーバンドデータ不足", 5)
    if trend_regime == "RANGE":
        if direction == "BUY":
            if price <= lower:
                return Reason("met", "レンジ相場でバンド下限にタッチ (逆張り買い)", 10)
            return Reason("failed", "レンジ相場だがバンド下限に未到達", 0)
        else:
            if price >= upper:
                return Reason("met", "レンジ相場でバンド上限にタッチ (逆張り売り)", 10)
            return Reason("failed", "レンジ相場だがバンド上限に未到達", 0)
    if trend_regime in ("UPTREND", "DOWNTREND"):
        if direction == "BUY" and trend_regime == "UPTREND":
            if price >= mid:
                return Reason("met", "上昇トレンドでバンド中心より上を推移", 8)
            return Reason("partial", "上昇トレンドだがバンド中心より下", 3)
        if direction == "SELL" and trend_regime == "DOWNTREND":
            if price <= mid:
                return Reason("met", "下降トレンドでバンド中心より下を推移", 8)
            return Reason("partial", "下降トレンドだがバンド中心より上", 3)
        return Reason("partial", "トレンド方向とバンド判定が不一致のため参考程度", 2)
    return Reason("partial", "レンジ/トレンド判定不明のため中立評価", 5)


def _volatility_component(vol_regime: str) -> Reason:
    if vol_regime == "NORMAL":
        return Reason("met", "ボラティリティは標準的", 10)
    if vol_regime == "HIGH_VOLATILITY":
        return Reason("partial", "ATR上昇 (ボラティリティ高)", 5)
    return Reason("partial", "ボラティリティ低下、値動き乏しい", 3)


def compute_higher_tf_bias(higher_tf: dict[str, pd.DataFrame]) -> dict[str, HigherTFBias]:
    result: dict[str, HigherTFBias] = {}
    for tf, df in higher_tf.items():
        if len(df) < 200:
            result[tf] = "NEUTRAL"
            continue
        e50 = ema(df["close"], 50).iloc[-1]
        e200 = ema(df["close"], 200).iloc[-1]
        if pd.isna(e50) or pd.isna(e200):
            result[tf] = "NEUTRAL"
        elif e50 > e200:
            result[tf] = "UP"
        elif e50 < e200:
            result[tf] = "DOWN"
        else:
            result[tf] = "NEUTRAL"
    return result


def _label_for(buy_score: int, sell_score: int) -> tuple[Direction, Label, int]:
    if buy_score >= 75:
        return "BUY", "強い買い", buy_score
    if sell_score >= 75:
        return "SELL", "強い売り", sell_score
    if buy_score >= 55:
        return "BUY", "買い", buy_score
    if sell_score >= 55:
        return "SELL", "売り", sell_score
    if buy_score >= sell_score:
        return "BUY", "様子見", buy_score
    return "SELL", "様子見", sell_score


def evaluate(df: pd.DataFrame, higher_tf: dict[str, pd.DataFrame] | None = None) -> SignalResult:
    """`df` is the entry-timeframe OHLC series (oldest-first, columns
    open/high/low/close), `higher_tf` maps e.g. {"H4": df_h4, "H1": df_h1} for
    multi-timeframe confirmation (docs/08_SIGNAL_ENGINE.md)."""
    higher_tf = higher_tf or {}
    close = df["close"]
    price = float(close.iloc[-1])

    ema20_s, ema50_s, ema200_s = ema(close, 20), ema(close, 50), ema(close, 200)
    ema20, ema50, ema200 = float(ema20_s.iloc[-1]), float(ema50_s.iloc[-1]), float(ema200_s.iloc[-1])
    rsi_series = rsi(close, 14)
    macd_line, signal_line, histogram = macd(close)
    upper, mid, lower = bollinger_bands(close, 20, 2.0)
    regime = classify_regime(df)
    higher_tf_bias = compute_higher_tf_bias(higher_tf)

    scores: dict[Direction, int] = {}
    reasons_by_dir: dict[Direction, list[Reason]] = {}
    for direction in ("BUY", "SELL"):
        components = [
            _trend_component(price, ema20, ema50, ema200, direction),
            _mtf_component(higher_tf_bias, direction),
            _rsi_component(rsi_series, direction),
            _macd_component(macd_line, signal_line, histogram, direction),
            _bollinger_component(
                price, float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1]), regime.trend, direction
            ),
            _volatility_component(regime.volatility),
        ]
        total = _clip(sum(r.points for r in components), 0, 100)
        scores[direction] = total
        reasons_by_dir[direction] = components

    direction, label, score = _label_for(scores["BUY"], scores["SELL"])
    return SignalResult(
        direction=direction,
        score=score,
        label=label,
        regime=regime,
        reasons=reasons_by_dir[direction],
        buy_score=scores["BUY"],
        sell_score=scores["SELL"],
    )
