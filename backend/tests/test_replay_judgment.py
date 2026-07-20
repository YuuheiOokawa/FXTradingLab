"""Qualitative Replay judgment (docs/01_REQUIREMENTS.md FR-9) — must not
reduce to "profitable = good, loss = bad"; these tests only ever look at
decision-time information (regime/score/RR), never an outcome."""
from app.services.regime import RegimeResult
from app.services.replay_judgment import judge_decision
from app.services.signal_engine import SignalResult


def _signal(direction="BUY", buy_score=80, sell_score=20, trend="UPTREND", volatility="NORMAL") -> SignalResult:
    return SignalResult(
        direction=direction,
        score=max(buy_score, sell_score),
        label="強い買い" if buy_score > sell_score else "強い売り",
        regime=RegimeResult(trend=trend, volatility=volatility, adx_value=30.0, atr_value=0.1, atr_avg=0.1),
        reasons=[],
        buy_score=buy_score,
        sell_score=sell_score,
    )


def test_buy_with_trend_and_score_alignment_and_good_rr_is_good():
    signal = _signal(buy_score=80, sell_score=20, trend="UPTREND")
    result = judge_decision("BUY", signal, stop_loss_pips=20, take_profit_pips=40)
    assert result.judgment == "good"


def test_buy_against_trend_and_against_score_is_risky():
    # BUY chosen despite a downtrend AND despite the engine itself favoring SELL.
    signal = _signal(buy_score=20, sell_score=80, trend="DOWNTREND")
    result = judge_decision("BUY", signal)
    assert result.judgment == "risky"


def test_bad_risk_reward_alone_makes_it_risky_even_with_good_alignment():
    signal = _signal(buy_score=80, sell_score=20, trend="UPTREND")
    result = judge_decision("BUY", signal, stop_loss_pips=40, take_profit_pips=20)  # RR = 0.5
    assert result.judgment == "risky"


def test_profitable_outcome_does_not_make_a_bad_process_good():
    """The whole point of this feature: a trade that WOULD have profited is
    still graded on its reasoning, not on hindsight - judge_decision doesn't
    even accept an outcome/pnl argument, so this is structurally guaranteed,
    but assert the behavior explicitly for a clearly-reckless entry."""
    signal = _signal(buy_score=15, sell_score=85, trend="DOWNTREND")
    result = judge_decision("BUY", signal, stop_loss_pips=20, take_profit_pips=60)  # good RR, terrible entry
    assert result.judgment == "risky"


def test_high_volatility_without_stop_loss_is_a_flagged_criterion():
    signal = _signal(buy_score=80, sell_score=20, trend="UPTREND", volatility="HIGH_VOLATILITY")
    result = judge_decision("BUY", signal, stop_loss_pips=None, take_profit_pips=None)
    vol_criterion = next(c for c in result.criteria if c.criterion == "ボラティリティ環境")
    assert vol_criterion.verdict == "unfavorable"


def test_missing_rr_is_not_specified_not_penalized_alone():
    signal = _signal(buy_score=80, sell_score=20, trend="UPTREND", volatility="NORMAL")
    result = judge_decision("BUY", signal)  # no SL/TP given
    rr_criterion = next(c for c in result.criteria if c.criterion == "リスクリワード")
    assert rr_criterion.verdict == "not_specified"
    assert result.judgment == "good"  # trend+score alignment alone should still carry it


def test_skip_a_weak_signal_is_judged_good():
    signal = _signal(buy_score=30, sell_score=35, trend="RANGE")  # weak, conflicting
    result = judge_decision("SKIP", signal)
    assert result.judgment == "good"


def test_skip_a_strong_clear_signal_is_neutral_not_risky():
    signal = _signal(buy_score=85, sell_score=10, trend="UPTREND")
    result = judge_decision("SKIP", signal)
    # Skipping should never itself be graded "risky" - not entering can't
    # endanger capital the way a badly-reasoned entry can.
    assert result.judgment == "neutral"


def test_missing_signal_returns_neutral_with_explanation():
    result = judge_decision("BUY", None)
    assert result.judgment == "neutral"
    assert result.criteria[0].verdict == "not_specified"
