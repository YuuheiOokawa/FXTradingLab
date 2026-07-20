"""Qualitative Replay judgment (docs/01_REQUIREMENTS.md FR-9): grades a
Replay decision as 良い判断 (good) / 普通 (neutral) / 危険な判断 (risky) —
deliberately NOT "profitable = correct, loss = wrong". Two decisions with
identical P&L can have very different judgments here if one was well-reasoned
and the other wasn't; that's the point.

Evaluated only from information available at (or before) the decision — the
regime/score the Signal Engine already computed for that exact moment, plus
whatever stop-loss/take-profit the user specified — never from what actually
happened afterward. A good process can have a bad outcome due to market
randomness and vice versa; this grades the process, not the outcome, per the
explicit requirement that this not become "did it make money" in disguise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.signal_engine import SignalResult

Judgment = Literal["good", "neutral", "risky"]
Verdict = Literal["favorable", "unfavorable", "neutral", "not_specified"]

MIN_SCORE_THRESHOLD = 55  # matches app/services/backtest/engine.py's floor
WEAK_SIGNAL_THRESHOLD = 40
STRONG_SIGNAL_THRESHOLD = 70
STRONG_SIGNAL_GAP = 20


@dataclass
class JudgmentCriterion:
    criterion: str
    verdict: Verdict
    note: str

    def to_dict(self) -> dict:
        return {"criterion": self.criterion, "verdict": self.verdict, "note": self.note}


@dataclass
class JudgmentResult:
    judgment: Judgment
    criteria: list[JudgmentCriterion]

    def criteria_dicts(self) -> list[dict]:
        return [c.to_dict() for c in self.criteria]


def _direction_alignment(action: str, signal: SignalResult) -> JudgmentCriterion:
    trend = signal.regime.trend
    favorable_trend = "UPTREND" if action == "BUY" else "DOWNTREND"
    opposing_trend = "DOWNTREND" if action == "BUY" else "UPTREND"
    if trend == favorable_trend:
        return JudgmentCriterion("相場方向との整合性", "favorable", f"上位トレンドが{trend}で{action}と一致")
    if trend == opposing_trend:
        return JudgmentCriterion("相場方向との整合性", "unfavorable", f"上位トレンドが{trend}で{action}と逆行")
    return JudgmentCriterion("相場方向との整合性", "neutral", f"トレンド判定は{trend}（明確な方向感なし）")


def _score_alignment(action: str, signal: SignalResult) -> JudgmentCriterion:
    own_score = signal.buy_score if action == "BUY" else signal.sell_score
    other_score = signal.sell_score if action == "BUY" else signal.buy_score
    if own_score < other_score:
        return JudgmentCriterion(
            "シグナルスコアとの整合性", "unfavorable", f"{action}方向のスコア({own_score})が逆方向({other_score})より低い"
        )
    if own_score < WEAK_SIGNAL_THRESHOLD:
        return JudgmentCriterion("シグナルスコアとの整合性", "unfavorable", f"{action}方向のスコアが{own_score}と弱い")
    if own_score >= MIN_SCORE_THRESHOLD:
        return JudgmentCriterion("シグナルスコアとの整合性", "favorable", f"{action}方向のスコアが{own_score}でエンジンの推奨水準以上")
    return JudgmentCriterion("シグナルスコアとの整合性", "neutral", f"{action}方向のスコアは{own_score}（推奨水準未満だが弱くはない）")


def _risk_reward(stop_loss_pips: float | None, take_profit_pips: float | None) -> JudgmentCriterion:
    if stop_loss_pips is None or take_profit_pips is None or stop_loss_pips <= 0:
        return JudgmentCriterion("リスクリワード", "not_specified", "損切り・利確幅が指定されていません")
    rr = take_profit_pips / stop_loss_pips
    if rr < 1.0:
        return JudgmentCriterion("リスクリワード", "unfavorable", f"RR比 {rr:.2f}（リスクが期待利益を上回る）")
    if rr >= 1.5:
        return JudgmentCriterion("リスクリワード", "favorable", f"RR比 {rr:.2f}")
    return JudgmentCriterion("リスクリワード", "neutral", f"RR比 {rr:.2f}（許容範囲だが理想的ではない）")


def _volatility_guard(signal: SignalResult, stop_loss_pips: float | None) -> JudgmentCriterion:
    if signal.regime.volatility == "HIGH_VOLATILITY" and stop_loss_pips is None:
        return JudgmentCriterion("ボラティリティ環境", "unfavorable", "高ボラティリティ環境で損切り幅が未指定")
    return JudgmentCriterion("ボラティリティ環境", "neutral", f"ボラティリティ: {signal.regime.volatility}")


def _skip_rationale(signal: SignalResult) -> JudgmentCriterion:
    strongest = max(signal.buy_score, signal.sell_score)
    gap = abs(signal.buy_score - signal.sell_score)
    if strongest < MIN_SCORE_THRESHOLD or gap < 10:
        return JudgmentCriterion("見送り判断の妥当性", "favorable", "シグナルが弱い、または方向感が拮抗しており見送りは妥当")
    if strongest >= STRONG_SIGNAL_THRESHOLD and gap >= STRONG_SIGNAL_GAP:
        return JudgmentCriterion(
            "見送り判断の妥当性", "neutral", f"比較的明確なシグナル(score={strongest})があった中での見送り — 機会損失の可能性"
        )
    return JudgmentCriterion("見送り判断の妥当性", "neutral", "シグナルはやや不明瞭 — 見送りも一つの判断")


def judge_decision(
    action: str,
    signal: SignalResult | None,
    stop_loss_pips: float | None = None,
    take_profit_pips: float | None = None,
) -> JudgmentResult:
    if signal is None:
        return JudgmentResult(
            judgment="neutral",
            criteria=[JudgmentCriterion("シグナル情報", "not_specified", "この時点のシグナル情報がありません")],
        )

    if action == "SKIP":
        skip = _skip_rationale(signal)
        judgment: Judgment = "good" if skip.verdict == "favorable" else "neutral"
        return JudgmentResult(judgment=judgment, criteria=[skip])

    criteria = [
        _direction_alignment(action, signal),
        _score_alignment(action, signal),
        _risk_reward(stop_loss_pips, take_profit_pips),
        _volatility_guard(signal, stop_loss_pips),
    ]

    direction_bad = criteria[0].verdict == "unfavorable"
    score_bad = criteria[1].verdict == "unfavorable"
    rr_bad = criteria[2].verdict == "unfavorable"

    # Compounding misalignment (went against both the trend AND the engine's
    # own score lean) or an explicitly bad risk/reward ratio are the clearest
    # process red flags — either alone is enough to call this risky,
    # regardless of how the other criteria came out.
    if (direction_bad and score_bad) or rr_bad:
        judgment = "risky"
    else:
        favorable_count = sum(1 for c in criteria if c.verdict == "favorable")
        unfavorable_count = sum(1 for c in criteria if c.verdict == "unfavorable")
        if favorable_count > unfavorable_count and favorable_count > 0:
            judgment = "good"
        elif unfavorable_count > favorable_count:
            judgment = "risky"
        else:
            judgment = "neutral"

    return JudgmentResult(judgment=judgment, criteria=criteria)
