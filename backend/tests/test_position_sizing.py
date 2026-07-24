"""Position sizing tests (app/services/position_sizing.py).

The property that matters: a stop-out costs the same fraction of equity no
matter which pair fired or how volatile it is. These assert that directly,
plus the refusal cases — sizing must fail closed rather than quietly exceed the
operator's risk limit.
"""
import pytest

from app.services.position_sizing import (
    MIN_SIZE,
    SizingResult,
    size_for_risk,
    volatility_multiplier,
)


class TestRiskIsConstant:
    def test_risk_amount_matches_the_budget(self):
        r = size_for_risk(equity=1_000_000, risk_pct=1.0, entry_price=150.00, stop_loss=148.00)
        assert isinstance(r, SizingResult)
        # 1% of 1,000,000 = 10,000 JPY budget; stop is 2.00 away -> 5,000 units.
        assert r.size == pytest.approx(5000)
        assert r.risk_amount == pytest.approx(10_000)
        assert r.risk_pct_of_equity == pytest.approx(1.0)

    def test_wider_stop_gets_a_smaller_position(self):
        tight = size_for_risk(1_000_000, 1.0, 150.0, 149.0)
        wide = size_for_risk(1_000_000, 1.0, 150.0, 147.0)
        assert tight.size > wide.size
        # Same risk either way — that is the whole point.
        assert tight.risk_pct_of_equity == pytest.approx(wide.risk_pct_of_equity, abs=0.15)

    def test_volatile_pair_does_not_risk_more_than_calm_one(self):
        """A GBP/JPY-like 3.00 stop and a USD/JPY-like 1.50 stop must cost the
        same to be wrong — the fixed-lot bug this module replaced did not."""
        volatile = size_for_risk(1_000_000, 1.0, 200.0, 197.0)
        calm = size_for_risk(1_000_000, 1.0, 150.0, 148.5)
        assert volatile.risk_amount == pytest.approx(calm.risk_amount, rel=0.05)
        assert volatile.size < calm.size

    def test_short_side_sizes_identically(self):
        long_side = size_for_risk(1_000_000, 1.0, 150.0, 148.0)
        short_side = size_for_risk(1_000_000, 1.0, 150.0, 152.0)
        assert long_side.size == short_side.size


class TestRounding:
    def test_size_rounds_down_to_the_step(self):
        # Budget allows 5,900 units; only whole 1,000 steps are tradeable.
        r = size_for_risk(1_000_000, 1.0, 150.0, 148.3)
        assert r.size % 1000 == 0
        # Rounding down can only reduce risk, never exceed the limit.
        assert r.risk_pct_of_equity <= 1.0

    def test_max_size_caps_the_position(self):
        r = size_for_risk(100_000_000, 1.0, 150.0, 149.0, max_size=50_000)
        assert r.size == 50_000


class TestRefusals:
    def test_returns_none_when_account_too_small_for_min_size(self):
        # 1% of 50,000 = 500 JPY; a 2.00 stop on the 1,000-unit minimum risks
        # 2,000 JPY, so there is no size that respects the limit.
        assert size_for_risk(50_000, 1.0, 150.0, 148.0) is None

    @pytest.mark.parametrize(
        "equity,risk,entry,stop",
        [
            (0, 1.0, 150.0, 148.0),      # no equity
            (1_000_000, 0, 150.0, 148.0),  # no risk budget
            (1_000_000, 1.0, 150.0, 150.0),  # zero stop distance
            (-100, 1.0, 150.0, 148.0),   # negative equity
        ],
    )
    def test_returns_none_on_invalid_inputs(self, equity, risk, entry, stop):
        assert size_for_risk(equity, risk, entry, stop) is None

    def test_rejects_non_positive_conversion_rate(self):
        assert size_for_risk(1_000_000, 1.0, 150.0, 148.0, quote_to_account_rate=0) is None


class TestQuoteCurrencyConversion:
    def test_non_jpy_quote_scales_the_size(self):
        """EUR/USD risk is in USD; converting at ~157 JPY/USD must shrink the
        position versus treating USD as if it were JPY."""
        unconverted = size_for_risk(1_000_000, 1.0, 1.1000, 1.0900)
        converted = size_for_risk(1_000_000, 1.0, 1.1000, 1.0900, quote_to_account_rate=157.0)
        assert converted.size < unconverted.size
        assert converted.risk_pct_of_equity <= 1.0


class TestVolatilityDeRisking:
    def test_halves_size_on_a_volatility_spike(self):
        assert volatility_multiplier(current_atr=2.2, baseline_atr=1.0) == 0.5

    def test_normal_volatility_keeps_full_size(self):
        assert volatility_multiplier(current_atr=1.1, baseline_atr=1.0) == 1.0

    def test_multiplier_actually_halves_the_position(self):
        # 1.00 stop distance so both sizes land exactly on the 1,000 step and
        # the assertion tests the multiplier, not the rounding.
        full = size_for_risk(1_000_000, 1.0, 150.0, 149.0, multiplier=1.0)
        half = size_for_risk(1_000_000, 1.0, 150.0, 149.0, multiplier=0.5)
        assert full.size == pytest.approx(10_000)
        assert half.size == pytest.approx(full.size / 2)
        assert half.risk_pct_of_equity == pytest.approx(0.5)
        assert "halved" in half.note

    def test_rounding_never_increases_risk_when_halving(self):
        # Step rounding is downward, so a de-risked size is at most half.
        full = size_for_risk(1_000_000, 1.0, 150.0, 148.0, multiplier=1.0)
        half = size_for_risk(1_000_000, 1.0, 150.0, 148.0, multiplier=0.5)
        assert half.size <= full.size / 2
        assert half.risk_pct_of_equity <= 0.5

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_invalid_atr_falls_back_to_full_size(self, bad):
        assert volatility_multiplier(bad, 1.0) == 1.0
        assert volatility_multiplier(1.0, bad) == 1.0


def test_minimum_size_constant_is_respected():
    r = size_for_risk(1_000_000, 1.0, 150.0, 148.0)
    assert r.size >= MIN_SIZE
