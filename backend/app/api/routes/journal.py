from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.journal import TradeJournal

router = APIRouter(tags=["journal"])


@router.get("/journal/trades")
async def list_trades(
    source: str | None = None,
    pair: str | None = None,
    direction: str | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = select(TradeJournal).order_by(TradeJournal.closed_at.desc()).limit(min(limit, 1000))
    if source:
        query = query.where(TradeJournal.source == source)
    if pair:
        query = query.where(TradeJournal.pair == pair)
    if direction:
        query = query.where(TradeJournal.direction == direction)
    result = await session.execute(query)
    return [
        {
            "id": str(t.id),
            "source": t.source,
            "pair": t.pair,
            "direction": t.direction,
            "entry_time": t.entry_time.isoformat(),
            "entry_price": t.entry_price,
            "exit_time": t.exit_time.isoformat(),
            "exit_price": t.exit_price,
            "size": t.size,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "pnl": t.pnl,
            "reason": t.reason,
            "signal_score": t.signal_score,
            "strategy_code": t.strategy_code,
            "market_regime": t.market_regime,
            "closed_at": t.closed_at.isoformat(),
        }
        for t in result.scalars().all()
    ]


DIMENSION_EXTRACTORS = {
    "hour": lambda t: t.entry_time.hour,
    "weekday": lambda t: t.entry_time.strftime("%A"),
    "pair": lambda t: t.pair,
    "direction": lambda t: t.direction,
    "regime": lambda t: t.market_regime or "unknown",
    "score_bucket": lambda t: f"{(t.signal_score or 0) // 10 * 10}-{(t.signal_score or 0) // 10 * 10 + 9}",
}


@router.get("/analytics/win-rate")
async def win_rate_breakdown(dimension: str = "pair", session: AsyncSession = Depends(get_db)) -> dict:
    extractor = DIMENSION_EXTRACTORS.get(dimension)
    if extractor is None:
        return {"error": f"unknown dimension '{dimension}'", "valid_dimensions": list(DIMENSION_EXTRACTORS)}

    result = await session.execute(select(TradeJournal))
    trades = result.scalars().all()

    buckets: dict[str, dict] = {}
    for t in trades:
        key = str(extractor(t))
        bucket = buckets.setdefault(key, {"trades": 0, "wins": 0, "total_pnl": 0.0})
        bucket["trades"] += 1
        bucket["wins"] += 1 if t.pnl > 0 else 0
        bucket["total_pnl"] += t.pnl

    breakdown = [
        {
            "key": key,
            "trades": b["trades"],
            "win_rate_pct": round(b["wins"] / b["trades"] * 100, 2) if b["trades"] else 0.0,
            "total_pnl": round(b["total_pnl"], 2),
        }
        for key, b in sorted(buckets.items())
    ]
    return {"dimension": dimension, "breakdown": breakdown}
