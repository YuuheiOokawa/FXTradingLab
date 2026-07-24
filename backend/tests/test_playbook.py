"""Playbook tests (app/services/playbook.py).

These pin the behaviour the 23-year study actually depends on: that each pair
gets ITS OWN style, that a fade trade aims at the mean while a trend trade
leaves its target open for the trail, that stops sit the configured ATR
multiple away on the correct side, and that the trailing stop can only ever
tighten. Series are constructed to force a specific rule to fire rather than
asserting on whatever a random walk happens to produce.
"""
import numpy as np
import pandas as pd
import pytest

from app.services import playbook
from app.worker.jobs.playbook_manage import compute_trailing_stop, mean_exit_reached


def _frame(closes: list[float], spread: float = 0.10) -> pd.DataFrame:
    """OHLC frame from a close path, with highs/lows a fixed distance away so
    ATR is well-defined and non-zero."""
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + spread,
            "low": close - spread,
            "close": close,
        }
    )


def _flat_then(n: int, base: float, tail: list[float]) -> list[float]:
    """A long flat run (so EMA200/Bollinger stabilise) followed by `tail`."""
    rng = np.random.default_rng(7)
    body = [base + float(rng.normal(0, 0.02)) for _ in range(n)]
    return body + tail


class TestConfiguration:
    def test_each_pair_has_a_distinct_style(self):
        styles = {sym: cfg.style for sym, cfg in playbook.PLAYBOOK.items()}
        assert styles["USD_JPY"] == "breakout_trail"
        assert styles["EUR_JPY"] == "trend_filtered_trail"
        assert styles["GBP_JPY"] == "bollinger_fade"
        # The whole point of the book: not one shared rule.
        assert len(set(styles.values())) > 1

    def test_eurusd_is_configured_but_disabled(self):
        # Its 23-year edge (+318 pips) is inside the noise; keeping it enabled
        # diluted the book's profit factor.
        assert playbook.PLAYBOOK["EUR_USD"].enabled is False
        assert playbook.config_for("EUR_USD").style == "rsi_fade"

    def test_unknown_instrument_has_no_config(self):
        assert playbook.config_for("XAU_USD") is None

    def test_gbpjpy_is_long_only(self):
        assert playbook.PLAYBOOK["GBP_JPY"].long_only is True

    def test_usdjpy_uses_the_multi_era_validated_parameters(self):
        """The original 2/3-ATR + ADX>=20 settings were fitted to 2003-2026 and
        lost money (PF 0.76) on 1996-2003, a period never used to select them.
        These wider, stricter values are profitable in all three eras. Pinning
        them means a future 'optimisation' that reverts to the fragile pair has
        to do so deliberately."""
        cfg = playbook.PLAYBOOK["USD_JPY"]
        assert cfg.adx_min == 25.0
        assert cfg.initial_stop_atr == 3.0
        assert cfg.trail_atr == 4.0

    def test_every_enabled_pair_has_a_regime_gate(self):
        """An ungated strategy trades in the regime it was never validated for."""
        for sym, cfg in playbook.PLAYBOOK.items():
            if not cfg.enabled:
                continue
            assert (cfg.adx_min is not None) or (cfg.adx_max is not None), sym

    def test_stops_are_never_tighter_than_two_atr(self):
        """Narrow stops were what got whipsawed out in the volatile 1990s."""
        for sym, cfg in playbook.PLAYBOOK.items():
            assert cfg.initial_stop_atr >= 2.0, sym

    def test_trailing_distance_exceeds_the_initial_stop(self):
        """A trail tighter than the entry stop would cut winners shorter than
        losers — the opposite of what a trend style is for."""
        for sym, cfg in playbook.PLAYBOOK.items():
            if cfg.trail_atr is None:
                continue
            assert cfg.trail_atr > cfg.initial_stop_atr, sym


class TestEvaluateGuards:
    def test_returns_none_for_unknown_instrument(self):
        assert playbook.evaluate("XAU_USD", _frame(_flat_then(300, 150.0, []))) is None

    def test_returns_none_for_disabled_instrument(self):
        closes = _flat_then(300, 1.10, [])
        assert playbook.evaluate("EUR_USD", _frame(closes, spread=0.001)) is None

    def test_returns_none_when_history_too_short(self):
        assert playbook.evaluate("USD_JPY", _frame([150.0] * 50)) is None

    def test_returns_none_when_nothing_triggers(self):
        # Dead-flat series: no breakout, no cross, no band pierce.
        assert playbook.evaluate("USD_JPY", _frame([150.0] * 300, spread=0.05)) is None


class TestBreakoutStyle:
    def test_upside_breakout_produces_buy_with_atr_stop(self):
        # A sustained uptrend: each close takes out the prior 20-day high AND
        # keeps ADX above the pair's regime floor.
        closes = [150.0 + i * 0.15 for i in range(300)]
        sig = playbook.evaluate("USD_JPY", _frame(closes))
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.style == "breakout_trail"
        # Trend styles ride a trail; they must not ship a fixed target.
        assert sig.take_profit is None
        assert sig.trail_atr == 4.0
        expected_stop = sig.price - 3.0 * sig.atr
        assert sig.stop_loss == pytest.approx(expected_stop)
        assert sig.stop_loss < sig.price

    def test_downside_breakout_produces_sell_with_stop_above(self):
        closes = [200.0 - i * 0.15 for i in range(300)]
        sig = playbook.evaluate("USD_JPY", _frame(closes))
        assert sig is not None
        assert sig.direction == "SELL"
        assert sig.stop_loss > sig.price
        assert sig.stop_loss == pytest.approx(sig.price + 3.0 * sig.atr)


class TestRegimeGate:
    def test_breakout_blocked_when_market_is_not_trending(self):
        """A one-off spike out of a flat range clears the 20-day high but has no
        trend behind it — exactly the false break the ADX floor exists to skip."""
        closes = _flat_then(300, 150.0, [156.0])
        assert playbook.evaluate("USD_JPY", _frame(closes)) is None

    def test_fade_blocked_when_market_is_strongly_trending(self):
        """GBP/JPY fades only in a range. In a hard downtrend the lower band is
        pierced constantly, and fading it is how a mean-reversion book blows up."""
        closes = [260.0 - i * 0.35 for i in range(300)]
        sig = playbook.evaluate("GBP_JPY", _frame(closes))
        assert sig is None

    def test_configured_thresholds_match_their_style(self):
        # Trend styles gate on a floor, fade styles on a ceiling — never both.
        for sym in ("USD_JPY", "EUR_JPY"):
            cfg = playbook.PLAYBOOK[sym]
            assert cfg.adx_min is not None and cfg.adx_max is None
        gbp = playbook.PLAYBOOK["GBP_JPY"]
        assert gbp.adx_max is not None and gbp.adx_min is None

    def test_signal_reports_the_adx_it_passed(self):
        closes = [150.0 + i * 0.15 for i in range(300)]
        sig = playbook.evaluate("USD_JPY", _frame(closes))
        assert sig is not None
        assert sig.adx >= playbook.PLAYBOOK["USD_JPY"].adx_min
        assert "ADX" in sig.reason


class TestTrendFilteredStyle:
    def test_cross_up_below_long_trend_is_rejected(self):
        """A fast/slow cross that happens while price is under EMA200 must not
        fire — that filter is what turned this pair profitable over 23 years."""
        down = [180.0 - i * 0.12 for i in range(300)]      # sustained downtrend
        bounce = [down[-1] + i * 0.30 for i in range(1, 12)]  # short bounce -> cross up
        sig = playbook.evaluate("EUR_JPY", _frame(down + bounce))
        if sig is not None:  # a cross may not occur at all; either way, never a BUY here
            assert sig.direction != "BUY"

    def test_buy_requires_price_above_trend_ema(self):
        up = [120.0 + i * 0.12 for i in range(300)]
        sig = playbook.evaluate("EUR_JPY", _frame(up))
        if sig is not None:
            assert sig.direction == "BUY"
            assert sig.take_profit is None  # trailing style
            assert sig.stop_loss == pytest.approx(sig.price - 2.0 * sig.atr)


class TestBollingerFadeStyle:
    def test_lower_band_pierce_produces_long_targeting_the_mean(self):
        closes = _flat_then(300, 200.0, [193.0])  # sharp drop through -2.5σ
        sig = playbook.evaluate("GBP_JPY", _frame(closes))
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.style == "bollinger_fade"
        assert sig.exit_style == "mean"
        # A fade's target IS the mean, and it must sit above a long's entry.
        assert sig.take_profit is not None
        assert sig.take_profit > sig.price
        assert sig.take_profit == pytest.approx(sig.mean_target)
        assert sig.max_hold_bars == 30
        assert sig.stop_loss == pytest.approx(sig.price - 3.0 * sig.atr)

    def test_upper_band_pierce_is_ignored_because_long_only(self):
        closes = _flat_then(300, 200.0, [207.0])
        assert playbook.evaluate("GBP_JPY", _frame(closes)) is None


class TestTrailingStop:
    def test_trail_tightens_for_long_and_never_loosens(self):
        first = compute_trailing_stop("BUY", 100.0, 97.0, extreme_price=105.0, atr_value=1.0, trail_atr=3.0)
        assert first == pytest.approx(102.0)  # 105 - 3*1
        # Price pulls back: the extreme is lower, so the stop must NOT move down.
        assert compute_trailing_stop("BUY", 100.0, 102.0, 103.0, 1.0, 3.0) is None

    def test_trail_tightens_for_short_and_never_loosens(self):
        first = compute_trailing_stop("SELL", 100.0, 103.0, extreme_price=95.0, atr_value=1.0, trail_atr=3.0)
        assert first == pytest.approx(98.0)  # 95 + 3*1
        assert compute_trailing_stop("SELL", 100.0, 98.0, 97.0, 1.0, 3.0) is None

    def test_no_trail_without_valid_atr(self):
        assert compute_trailing_stop("BUY", 100.0, 97.0, 105.0, 0.0, 3.0) is None

    def test_first_trail_applies_with_no_existing_stop(self):
        assert compute_trailing_stop("BUY", 100.0, None, 110.0, 2.0, 3.0) == pytest.approx(104.0)


class TestMeanExit:
    @pytest.mark.parametrize(
        "direction,close,mean,expected",
        [
            ("BUY", 200.5, 200.0, True),    # long reverted up to the mean
            ("BUY", 199.5, 200.0, False),
            ("SELL", 199.5, 200.0, True),   # short reverted down to the mean
            ("SELL", 200.5, 200.0, False),
        ],
    )
    def test_mean_exit_direction_aware(self, direction, close, mean, expected):
        assert mean_exit_reached(direction, close, mean) is expected
