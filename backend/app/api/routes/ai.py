from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_db
from app.brokers.base import BrokerAdapter
from app.brokers.schemas import Granularity
from app.db.models.journal import TradeJournal
from app.services import ai_explain
from app.services.signal_engine import evaluate

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/explain/signal/{symbol}")
async def explain_signal(
    symbol: str, granularity: Granularity = Granularity.M15, broker: BrokerAdapter = Depends(get_broker)
) -> dict:
    candles = await broker.get_candles(symbol, granularity, 300)
    import pandas as pd

    df = pd.DataFrame(
        {
            "open_time": [c.open_time for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )
    signal = evaluate(df)
    reasons = [{"status": r.status, "text": r.text, "points": r.points} for r in signal.reasons]
    text = await ai_explain.explain_signal(symbol, signal.label, signal.score, reasons)
    return {"instrument": symbol, "label": signal.label, "score": signal.score, "explanation": text}


@router.get("/explain/trade/{trade_id}")
async def explain_trade(trade_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> dict:
    trade = await session.get(TradeJournal, trade_id)
    if trade is None:
        raise HTTPException(404, "trade not found")
    text = await ai_explain.explain_trade(
        {
            "pair": trade.pair,
            "direction": trade.direction,
            "pnl": trade.pnl,
            "signal_score": trade.signal_score,
            "market_regime": trade.market_regime,
            "reason": trade.reason,
        }
    )
    return {"trade_id": str(trade_id), "explanation": text}


@router.get("/daily-summary")
async def daily_summary(session: AsyncSession = Depends(get_db)) -> dict:
    from datetime import UTC, datetime

    from sqlalchemy import select

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(select(TradeJournal.pnl).where(TradeJournal.closed_at >= today_start))
    pnls = [p for (p,) in result.all()]
    text = await ai_explain.daily_summary(len(pnls), sum(pnls), sum(1 for p in pnls if p > 0))
    return {"trade_count": len(pnls), "total_pnl": sum(pnls), "explanation": text}


@router.get("/explain/backtest/{backtest_id}")
async def explain_backtest(backtest_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> dict:
    from app.db.models.trading import Backtest

    backtest = await session.get(Backtest, backtest_id)
    if backtest is None:
        raise HTTPException(404, "backtest not found")
    text = await ai_explain.explain_backtest(backtest.summary)
    return {"backtest_id": str(backtest_id), "explanation": text}
