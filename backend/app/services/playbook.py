"""Per-instrument strategy playbook.

Every instrument gets the logic that fits ITS OWN measured character, because a
single strategy applied to all pairs loses: over ~23 years of real daily data
(2003-2026) one shared EMA trend-follower returned -12,926 pips (PF 0.81) on
these four pairs, while the per-pair book below returned +12,939 pips (PF 1.34)
and was profitable in every nested 5/10/15/20/23-year window.

The choice per pair is not arbitrary — it follows each pair's variance ratio
VR(60) (Var of 60-day returns / 60x Var of 1-day returns), which says whether
returns persist (>1, trend) or revert (<1, fade):

    USD/JPY  VR .76   but clean 20-day breakouts     -> breakout + ATR trail
    EUR/JPY  VR .77   strongest sustained trends     -> EMA cross w/ EMA200 filter + trail
    GBP/JPY  VR 1.10  highest vol (ATR ~164 pips)    -> Bollinger 2.5σ fade, LONG only
    EUR/USD  VR .82   most efficient, weakest edge   -> RSI fade, disabled by default

**Parameters are set by multi-era survival, not by best total return.** USD/JPY
history now reaches back to 1996, which supplied a stretch (1996-2003) that was
never used to choose anything. The original parameters, picked by optimising the
2003-2026 window, scored PF 1.29 there and PF 0.76 — an outright loss — on the
unused years. That is what selection bias looks like when you finally test it.

Every configuration below is therefore required to be profitable in EVERY era
tested, never merely to post the largest total:

    USD/JPY  1996-2003 PF 1.39 | 2003-2015 PF 1.61 | 2015-2026 PF 1.17
    EUR/JPY  2003-2010 PF 1.00 | 2010-2018 PF 2.58 | 2018-2026 PF 2.07
    GBP/JPY  2003-2010 PF 2.09 | 2010-2018 PF 1.20 | 2018-2026 PF 2.74

Caveat worth stating plainly: once 1996-2003 was used to pick USD/JPY's
parameters it stopped being an independent test. The multi-era bar is a much
stronger filter than a single window, but only live forward testing produces
evidence that was never fitted to.

Everything here is a pure function over an OHLC DataFrame so it can be unit
tested against fixtures without a broker, a database, or a network call
(tests/test_playbook.py). Order submission and position management live in
app/services/auto_trader.py and app/worker/jobs/playbook_manage.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from app.services.indicators import adx, atr, bollinger_bands, ema, rsi, sma

StyleName = Literal["breakout_trail", "trend_filtered_trail", "bollinger_fade", "rsi_fade"]
ExitStyle = Literal["trail", "mean"]


@dataclass(frozen=True)
class PlaybookConfig:
    """One instrument's rulebook. `enabled=False` keeps a pair configured but
    untraded — used for EUR/USD, whose 23-year edge (+318 pips total) is inside
    the noise and dilutes the book's profit factor rather than adding to it."""

    style: StyleName
    exit_style: ExitStyle
    initial_stop_atr: float
    trail_atr: float | None = None      # trail exits only
    max_hold_bars: int | None = None    # mean-reversion exits only
    long_only: bool = False
    enabled: bool = True
    # Regime gate (ADX 14). A trend style needs a trend to exist; a fade style
    # needs the market NOT to be trending, because fading a strong trend is how
    # mean-reversion books blow up. Measured over the same 23 years: adding
    # these gates took the book from +12,621 pips / PF 1.38 to +14,859 pips /
    # PF 1.64 and halved the worst drawdown (-4,064 -> -2,073 pips). Thresholds
    # are round numbers; every variant tested beat "no gate" at 20y and 23y, so
    # the gain comes from having a gate, not from the exact level.
    adx_min: float | None = None   # trend styles: require ADX >= this
    adx_max: float | None = None   # fade styles: require ADX <= this
    # style parameters
    donchian_period: int = 20
    ema_fast: int = 10
    ema_slow: int = 30
    ema_trend: int = 200
    bb_period: int = 20
    bb_std: float = 2.5
    rsi_period: int = 14
    rsi_low: float = 25.0
    rsi_high: float = 75.0
    mean_period: int = 20


# Parameters below are the ones validated across all five nested windows; they
# are deliberately round numbers, not decimals tuned to the last basis point.
PLAYBOOK: dict[str, PlaybookConfig] = {
    # Re-tuned after extending USD/JPY history back to 1996 (Yahoo `JPY=X`),
    # which exposed 1996-2003 as a period never used to choose anything. The
    # previous settings (ADX>=20, 2/3 ATR) earned PF 1.29 on the years they were
    # selected on and PF 0.76 — a real loss — on the years they were not. A
    # wider stop and a stricter trend gate is profitable in all three eras:
    # 1996-2003 PF 1.39, 2003-2015 PF 1.61, 2015-2026 PF 1.17.
    "USD_JPY": PlaybookConfig(
        style="breakout_trail", exit_style="trail",
        initial_stop_atr=3.0, trail_atr=4.0, donchian_period=20,
        adx_min=25.0,
    ),
    # Narrower stop than the original 3/4 ATR. The wider version scored a higher
    # headline total but lost money in 2003-2010 (PF 0.79); this one is flat
    # there (PF 1.00) and still strong afterwards (PF 2.58, 2.07). Given what
    # the USD/JPY out-of-sample failure showed, "no losing era" is worth more
    # than a bigger number driven by one favourable stretch.
    "EUR_JPY": PlaybookConfig(
        style="trend_filtered_trail", exit_style="trail",
        initial_stop_atr=2.0, trail_atr=3.0, ema_fast=10, ema_slow=30, ema_trend=200,
        adx_min=15.0,
    ),
    "GBP_JPY": PlaybookConfig(
        style="bollinger_fade", exit_style="mean",
        initial_stop_atr=3.0, max_hold_bars=30, long_only=True, bb_period=20, bb_std=2.5,
        adx_max=30.0,
    ),
    "EUR_USD": PlaybookConfig(
        style="rsi_fade", exit_style="mean",
        initial_stop_atr=3.0, max_hold_bars=30,
        rsi_period=14, rsi_low=25.0, rsi_high=75.0,
        enabled=False,
    ),
}

# Longest lookback any style needs (EMA200) plus headroom for it to stabilise.
MIN_BARS = 260


@dataclass(frozen=True)
class PlaybookSignal:
    instrument: str
    direction: Literal["BUY", "SELL"]
    style: StyleName
    exit_style: ExitStyle
    price: float
    atr: float
    stop_loss: float
    take_profit: float | None   # set for mean-reversion; None while a trail manages the exit
    mean_target: float | None   # the 20-period mean a fade trade is aiming at
    max_hold_bars: int | None
    trail_atr: float | None
    adx: float
    reason: str


def config_for(instrument: str) -> PlaybookConfig | None:
    return PLAYBOOK.get(instrument)


def _crossed_up(series: pd.Series, level: pd.Series) -> bool:
    return bool(series.iloc[-1] > level.iloc[-1] and series.iloc[-2] <= level.iloc[-2])


def _crossed_down(series: pd.Series, level: pd.Series) -> bool:
    return bool(series.iloc[-1] < level.iloc[-1] and series.iloc[-2] >= level.iloc[-2])


def evaluate(instrument: str, df: pd.DataFrame) -> PlaybookSignal | None:
    """Evaluate `instrument`'s own rules on closed daily candles.

    `df` must be ordered oldest-first with open/high/low/close columns, and the
    LAST row must be a CLOSED candle — the caller is responsible for dropping a
    still-forming one, otherwise every rule here would be reading a price that
    can still change (a look-ahead bug that flatters backtests).
    """
    cfg = PLAYBOOK.get(instrument)
    if cfg is None or not cfg.enabled or len(df) < MIN_BARS:
        return None

    close, high, low = df["close"], df["high"], df["low"]
    atr_value = float(atr(high, low, close, 14).iloc[-1])
    price = float(close.iloc[-1])
    if not (atr_value > 0) or not (price > 0):
        return None

    # Regime gate first: if the market is in the wrong state for this style,
    # no entry rule below can rescue the trade, so don't even evaluate them.
    adx_value = float(adx(high, low, close, 14)[0].iloc[-1])
    if adx_value != adx_value:  # NaN — not enough history for a verdict
        return None
    if cfg.adx_min is not None and adx_value < cfg.adx_min:
        return None
    if cfg.adx_max is not None and adx_value > cfg.adx_max:
        return None

    direction: str | None = None
    reason = ""
    mean_target: float | None = None

    if cfg.style == "breakout_trail":
        prior_high = high.rolling(cfg.donchian_period).max().shift(1)
        prior_low = low.rolling(cfg.donchian_period).min().shift(1)
        if price > float(prior_high.iloc[-1]):
            direction, reason = "BUY", f"{cfg.donchian_period}日高値{prior_high.iloc[-1]:.3f}を上抜け"
        elif price < float(prior_low.iloc[-1]):
            direction, reason = "SELL", f"{cfg.donchian_period}日安値{prior_low.iloc[-1]:.3f}を下抜け"

    elif cfg.style == "trend_filtered_trail":
        fast, slow = ema(close, cfg.ema_fast), ema(close, cfg.ema_slow)
        trend = ema(close, cfg.ema_trend)
        above_trend = price > float(trend.iloc[-1])
        if _crossed_up(fast, slow) and above_trend:
            direction = "BUY"
            reason = f"EMA{cfg.ema_fast}がEMA{cfg.ema_slow}を上抜け・EMA{cfg.ema_trend}上（上昇トレンド）"
        elif _crossed_down(fast, slow) and not above_trend:
            direction = "SELL"
            reason = f"EMA{cfg.ema_fast}がEMA{cfg.ema_slow}を下抜け・EMA{cfg.ema_trend}下（下降トレンド）"

    elif cfg.style == "bollinger_fade":
        upper, mid, lower = bollinger_bands(close, cfg.bb_period, cfg.bb_std)
        mean_target = float(mid.iloc[-1])
        if _crossed_down(close, lower):
            direction = "BUY"
            reason = f"ボリンジャー-{cfg.bb_std}σ({lower.iloc[-1]:.3f})を下抜け → 平均{mean_target:.3f}へ回帰狙い"
        elif not cfg.long_only and _crossed_up(close, upper):
            direction = "SELL"
            reason = f"ボリンジャー+{cfg.bb_std}σ({upper.iloc[-1]:.3f})を上抜け → 平均{mean_target:.3f}へ回帰狙い"

    elif cfg.style == "rsi_fade":
        r = rsi(close, cfg.rsi_period)
        mean_target = float(sma(close, cfg.mean_period).iloc[-1])
        low_level = pd.Series(cfg.rsi_low, index=r.index)
        high_level = pd.Series(cfg.rsi_high, index=r.index)
        if _crossed_down(r, low_level):
            direction, reason = "BUY", f"RSI{r.iloc[-1]:.0f}（{cfg.rsi_low}以下）→ 売られすぎ"
        elif not cfg.long_only and _crossed_up(r, high_level):
            direction, reason = "SELL", f"RSI{r.iloc[-1]:.0f}（{cfg.rsi_high}以上）→ 買われすぎ"

    if direction is None:
        return None
    if cfg.long_only and direction != "BUY":
        return None

    stop_distance = cfg.initial_stop_atr * atr_value
    stop_loss = price - stop_distance if direction == "BUY" else price + stop_distance

    # A fade trade's profit target IS the mean it is reverting to. A trend trade
    # has no fixed target on purpose — the trailing stop decides when to leave,
    # which is what let the winners run in the 23-year test.
    take_profit = mean_target if cfg.exit_style == "mean" else None
    if take_profit is not None:
        # Never submit a target on the wrong side of entry (can happen when the
        # band is pierced so hard the close overshoots the mean).
        if (direction == "BUY" and take_profit <= price) or (direction == "SELL" and take_profit >= price):
            take_profit = None

    return PlaybookSignal(
        instrument=instrument,
        direction=direction,  # type: ignore[arg-type]
        style=cfg.style,
        exit_style=cfg.exit_style,
        price=price,
        atr=atr_value,
        stop_loss=stop_loss,
        take_profit=take_profit,
        mean_target=mean_target,
        max_hold_bars=cfg.max_hold_bars,
        trail_atr=cfg.trail_atr,
        adx=adx_value,
        reason=f"{reason}（ADX {adx_value:.0f}）",
    )
