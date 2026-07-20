"""AI explanation layer (docs/08_SIGNAL_ENGINE.md "AI's role").

AI never computes a score or direction — every function here takes
already-computed structured data (a SignalResult, a trade, a backtest summary)
and produces a natural-language summary of it. If `AI_API_KEY` is not configured,
every function falls back to a templated (non-LLM) string built directly from the
same structured data, so the app's main features never depend on having an AI key
(docs/01_REQUIREMENTS.md NFR-6).
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-5"


async def _call_anthropic(system_prompt: str, user_prompt: str) -> str | None:
    settings = get_settings()
    if not settings.ai_api_key or settings.ai_provider != "anthropic":
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": settings.ai_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 400,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
        if resp.status_code != 200:
            logger.warning("AI explain call failed: %s %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        parts = data.get("content", [])
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return text.strip() or None
    except httpx.RequestError as exc:
        logger.warning("AI explain call errored: %s", exc)
        return None


_SIGNAL_SYSTEM_PROMPT = (
    "You explain FX trading signals from a rule-based system to a retail trader in "
    "plain, beginner-friendly Japanese. You NEVER predict future price movement or "
    "give investment advice — you only explain what the given rule-based score and "
    "reasons already say, in 2-4 short sentences."
)


async def explain_signal(instrument: str, label: str, score: int, reasons: list[dict]) -> str:
    reason_lines = "\n".join(f"- [{r['status']}] {r['text']} ({r['points']}pt)" for r in reasons)
    ai_text = await _call_anthropic(
        _SIGNAL_SYSTEM_PROMPT,
        f"通貨ペア: {instrument}\n判定: {label} (スコア {score}/100)\n根拠:\n{reason_lines}\n\n"
        "この判定について、初心者にも分かるように2〜4文で説明してください。",
    )
    if ai_text:
        return ai_text
    met = [r["text"] for r in reasons if r["status"] == "met"]
    failed = [r["text"] for r in reasons if r["status"] == "failed"]
    summary = f"{instrument}は現在ルール上「{label}」(スコア{score}/100)です。"
    if met:
        summary += f" 主な根拠: {'、'.join(met[:3])}。"
    if failed:
        summary += f" 一方で: {'、'.join(failed[:2])}。"
    return summary


_TRADE_SYSTEM_PROMPT = (
    "You analyze a single closed FX trade for a retail trader keeping a trading "
    "journal, in plain, non-judgmental Japanese. Explain likely reasons for the "
    "win/loss based only on the given data (signal score, market regime, direction, "
    "pnl). 2-4 short sentences. Never suggest a specific future trade."
)


async def explain_trade(trade: dict) -> str:
    ai_text = await _call_anthropic(
        _TRADE_SYSTEM_PROMPT,
        f"通貨ペア: {trade.get('pair')}\n方向: {trade.get('direction')}\n"
        f"損益: {trade.get('pnl')}\nシグナルスコア: {trade.get('signal_score')}\n"
        f"市場状態: {trade.get('market_regime')}\n決済理由: {trade.get('reason')}\n\n"
        "このトレードを振り返り、初心者にも分かるように2〜4文で説明してください。",
    )
    if ai_text:
        return ai_text
    outcome = "利益" if (trade.get("pnl") or 0) > 0 else "損失"
    return (
        f"{trade.get('pair')}の{trade.get('direction')}トレードは{outcome}({trade.get('pnl')})で終了しました。"
        f"シグナルスコアは{trade.get('signal_score')}、市場状態は{trade.get('market_regime')}でした。"
    )


_DAILY_SYSTEM_PROMPT = (
    "You summarize a retail FX trader's trading day in plain Japanese, 3-5 short "
    "sentences, based only on the given aggregate stats. Never give forward-looking "
    "investment advice."
)


async def daily_summary(trade_count: int, total_pnl: float, win_count: int) -> str:
    win_rate = (win_count / trade_count * 100) if trade_count else 0.0
    ai_text = await _call_anthropic(
        _DAILY_SYSTEM_PROMPT,
        f"本日のトレード回数: {trade_count}\n合計損益: {total_pnl}\n勝率: {win_rate:.1f}%\n\n"
        "本日のトレードを3〜5文で要約してください。",
    )
    if ai_text:
        return ai_text
    if trade_count == 0:
        return "本日はまだトレードがありません。"
    return f"本日は{trade_count}回のトレードを行い、合計損益は{total_pnl:,.0f}、勝率は{win_rate:.1f}%でした。"


_BACKTEST_SYSTEM_PROMPT = (
    "You explain a completed FX strategy backtest result to a retail trader in "
    "plain Japanese, 3-5 short sentences, based only on the given metrics. Point "
    "out any red flags like a large gap between in-sample and out-of-sample "
    "performance (possible overfitting). Never claim the strategy will be "
    "profitable in the future."
)


async def explain_backtest(summary: dict) -> str:
    overall = summary.get("overall", {})
    in_sample = summary.get("in_sample", {})
    out_of_sample = summary.get("out_of_sample", {})
    ai_text = await _call_anthropic(
        _BACKTEST_SYSTEM_PROMPT,
        f"全体: 勝率{overall.get('win_rate_pct')}%, PF{overall.get('profit_factor')}, "
        f"最大DD{overall.get('max_drawdown_pct')}%, 取引数{overall.get('trade_count')}\n"
        f"In-Sample: 勝率{in_sample.get('win_rate_pct')}%, PF{in_sample.get('profit_factor')}\n"
        f"Out-of-Sample: 勝率{out_of_sample.get('win_rate_pct')}%, PF{out_of_sample.get('profit_factor')}\n\n"
        "この結果を3〜5文で説明してください。",
    )
    if ai_text:
        return ai_text
    return (
        f"全体の勝率は{overall.get('win_rate_pct')}%、Profit Factorは{overall.get('profit_factor')}、"
        f"最大ドローダウンは{overall.get('max_drawdown_pct')}%でした。"
        f"In-Sample勝率{in_sample.get('win_rate_pct')}%に対しOut-of-Sample勝率{out_of_sample.get('win_rate_pct')}%であり、"
        "両者の差が大きい場合は過剰最適化の可能性に注意してください。"
    )
