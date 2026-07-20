"""AI explanation layer works with zero AI_API_KEY configured (docs/01_REQUIREMENTS.md
NFR-6) — the test environment never sets AI_API_KEY, so these exercise the
templated fallback path exclusively."""
from app.services import ai_explain


async def test_explain_signal_falls_back_to_template_without_api_key():
    reasons = [
        {"status": "met", "text": "EMA20 > EMA50 > EMA200", "points": 30},
        {"status": "failed", "text": "MACDは売り方向", "points": 0},
    ]
    text = await ai_explain.explain_signal("USD_JPY", "買い", 70, reasons)
    assert "USD_JPY" in text
    assert "買い" in text
    assert "70" in text


async def test_explain_trade_falls_back_to_template():
    text = await ai_explain.explain_trade(
        {"pair": "EUR_USD", "direction": "SELL", "pnl": -150.0, "signal_score": 60, "market_regime": "RANGE", "reason": "SL hit"}
    )
    assert "EUR_USD" in text
    assert "損失" in text


async def test_daily_summary_handles_zero_trades():
    text = await ai_explain.daily_summary(0, 0.0, 0)
    assert "まだ" in text or "0" in text


async def test_daily_summary_falls_back_to_template():
    text = await ai_explain.daily_summary(5, 12000.0, 3)
    assert "5" in text


async def test_explain_backtest_falls_back_to_template():
    summary = {
        "overall": {"win_rate_pct": 45.0, "profit_factor": 1.2, "max_drawdown_pct": 15.0, "trade_count": 20},
        "in_sample": {"win_rate_pct": 55.0, "profit_factor": 1.8},
        "out_of_sample": {"win_rate_pct": 20.0, "profit_factor": 0.5},
    }
    text = await ai_explain.explain_backtest(summary)
    assert "過剰最適化" in text
