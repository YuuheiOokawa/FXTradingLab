"""Forward-test scoring and paper bracket enforcement.

The bracket tests matter most: stop-loss/take-profit on paper positions were
stored but never acted on, which made every risk number the app reported
unenforceable. These pin the enforcement rules, especially the pessimistic
tie-break.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.services.forward_test import (
    BACKTEST_BASELINE,
    MIN_TRADES_FOR_CONFIDENCE,
    build_report,
    compare_to_backtest,
    summarize,
    verdict,
)
from app.worker.jobs.paper_brackets import breach


@dataclass
class FakeTrade:
    pnl: float
    entry_time: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    exit_time: datetime = datetime(2026, 1, 2, tzinfo=UTC)
    pair: str = "USD_JPY"
    reason: str = "stop loss"
    strategy_code: str = "breakout_trail"


def trades(*pnls: float) -> list[FakeTrade]:
    return [FakeTrade(pnl=p) for p in pnls]


class TestSummarize:
    def test_empty_input_is_all_zero_not_an_error(self):
        s = summarize([])
        assert s.trades == 0
        assert s.profit_factor is None

    def test_basic_metrics(self):
        s = summarize(trades(100, -50, 200, -50))
        assert s.trades == 4
        assert s.wins == 2 and s.losses == 2
        assert s.win_rate_pct == 50.0
        assert s.total_pnl == 200.0
        assert s.expectancy == 50.0
        assert s.gross_profit == 300.0 and s.gross_loss == 100.0
        assert s.profit_factor == 3.0
        assert s.best == 200.0 and s.worst == -50.0

    def test_breakeven_trade_counts_as_a_loss_not_a_win(self):
        # pnl == 0 is not a win; counting it as one inflates the win rate.
        s = summarize(trades(0.0))
        assert s.wins == 0
        assert s.losses == 1

    def test_profit_factor_is_none_when_no_losses_yet(self):
        """A perfect early run is 'too early to divide', not infinitely good."""
        s = summarize(trades(10, 20, 30))
        assert s.profit_factor is None

    def test_max_drawdown_is_peak_to_trough_of_cumulative_pnl(self):
        # equity path: 100, 40, -10, 90 -> peak 100, trough -10 => -110
        s = summarize(trades(100, -60, -50, 100))
        assert s.max_drawdown == pytest.approx(-110.0)

    def test_drawdown_zero_when_only_gains(self):
        assert summarize(trades(10, 20)).max_drawdown == 0.0

    def test_average_hold_uses_entry_and_exit_times(self):
        t = FakeTrade(pnl=5, entry_time=datetime(2026, 1, 1, tzinfo=UTC),
                      exit_time=datetime(2026, 1, 1, 12, tzinfo=UTC))
        assert summarize([t]).avg_hold_hours == pytest.approx(12.0)


class TestVerdict:
    def test_no_trades(self):
        assert verdict(summarize([])) == "no_trades"

    def test_small_sample_is_too_early_even_if_profitable(self):
        s = summarize(trades(*([100] * 5 + [-10] * 2)))
        assert s.trades < MIN_TRADES_FOR_CONFIDENCE
        assert verdict(s) == "too_early"

    def test_tracking_when_profit_factor_healthy_with_enough_trades(self):
        s = summarize(trades(*([100] * 15 + [-50] * 15)))  # PF = 2.0
        assert verdict(s) == "tracking"

    def test_underperforming_when_losing(self):
        s = summarize(trades(*([50] * 10 + [-100] * 15)))
        assert verdict(s) == "underperforming"

    def test_marginal_band(self):
        s = summarize(trades(*([110] * 15 + [-100] * 15)))  # PF = 1.1
        assert verdict(s) == "marginal"


class TestCompareToBacktest:
    def test_reports_delta_against_the_pair_baseline(self):
        s = summarize(trades(*([100] * 10 + [-50] * 10)))  # 50% win, PF 2.0
        cmp = compare_to_backtest("USD_JPY", s)
        baseline = BACKTEST_BASELINE["USD_JPY"]
        assert cmp["backtest_win_rate_pct"] == baseline["win_rate_pct"]
        # Derived from the constant, not hardcoded: re-validating a strategy is
        # supposed to move the baseline, and that must not break this test.
        assert cmp["win_rate_delta"] == pytest.approx(50.0 - baseline["win_rate_pct"])
        assert cmp["profit_factor_delta"] == pytest.approx(2.0 - baseline["profit_factor"])
        assert cmp["enough_trades"] is True

    def test_unknown_pair_has_no_baseline(self):
        assert compare_to_backtest("XAU_USD", summarize(trades(1))) is None

    def test_flags_insufficient_sample(self):
        assert compare_to_backtest("USD_JPY", summarize(trades(1, -1)))["enough_trades"] is False


class TestBuildReport:
    def test_splits_per_pair_and_overall(self):
        by_pair = {
            "USD_JPY": trades(100, -50),
            "GBP_JPY": trades(30, 40),
        }
        overall = by_pair["USD_JPY"] + by_pair["GBP_JPY"]
        r = build_report(by_pair, overall)
        assert r["overall"]["trades"] == 4
        assert [p["pair"] for p in r["per_pair"]] == ["GBP_JPY", "USD_JPY"]  # sorted
        assert r["min_trades_for_confidence"] == MIN_TRADES_FOR_CONFIDENCE

    def test_empty_report_does_not_crash(self):
        r = build_report({}, [])
        assert r["overall"]["trades"] == 0
        assert r["per_pair"] == []


class TestPaperBrackets:
    def test_long_stops_out_on_bid_touching_stop(self):
        assert breach("BUY", bid=148.0, ask=148.02, stop_loss=149.0, take_profit=155.0) == ("stop loss", 149.0)

    def test_long_takes_profit_on_bid_reaching_target(self):
        assert breach("BUY", bid=155.5, ask=155.52, stop_loss=149.0, take_profit=155.0) == ("take profit", 155.0)

    def test_long_untouched_returns_none(self):
        assert breach("BUY", bid=151.0, ask=151.02, stop_loss=149.0, take_profit=155.0) is None

    def test_short_stops_out_on_ask_touching_stop(self):
        assert breach("SELL", bid=155.9, ask=156.0, stop_loss=155.0, take_profit=148.0) == ("stop loss", 155.0)

    def test_short_takes_profit_on_ask_reaching_target(self):
        assert breach("SELL", bid=147.5, ask=147.52, stop_loss=155.0, take_profit=148.0) == ("take profit", 148.0)

    def test_stop_wins_when_both_levels_are_breached(self):
        """Intra-poll ordering is unknowable; assuming the stop filled first is
        the only assumption that cannot flatter results."""
        assert breach("BUY", bid=140.0, ask=140.02, stop_loss=149.0, take_profit=141.0)[0] == "stop loss"
        assert breach("SELL", bid=160.0, ask=160.02, stop_loss=155.0, take_profit=159.0)[0] == "stop loss"

    def test_missing_levels_are_skipped_not_treated_as_zero(self):
        assert breach("BUY", 100.0, 100.02, None, None) is None
        assert breach("BUY", 100.0, 100.02, None, 99.0) == ("take profit", 99.0)
        assert breach("BUY", 100.0, 100.02, 101.0, None) == ("stop loss", 101.0)

    def test_long_exits_on_bid_and_short_on_ask(self):
        """The spread must be paid on exit, matching the backtest's cost model:
        a long at a 149.5 bid / 150.5 ask is stopped at 150, a short is not."""
        assert breach("BUY", bid=149.5, ask=150.5, stop_loss=150.0, take_profit=None) == ("stop loss", 150.0)
        assert breach("SELL", bid=149.5, ask=150.5, stop_loss=151.0, take_profit=None) is None
