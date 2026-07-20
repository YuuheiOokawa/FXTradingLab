from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.journal import TradeJournal
from app.db.models.strategy import Signal

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


def _score_bucket(score: int) -> str:
    if score >= 80:
        return "80+"
    if score >= 70:
        return "70-79"
    if score >= 60:
        return "60-69"
    return "<60"


SCORE_BUCKET_ORDER = ["80+", "70-79", "60-69", "<60"]


@router.get("/analytics/signal-outcomes")
async def signal_outcome_breakdown(pair: str | None = None, session: AsyncSession = Depends(get_db)) -> dict:
    """Score-bucket signal outcome accuracy (docs/08_SIGNAL_ENGINE.md "Signal
    outcome history"): for each score band, how captured signals actually
    moved afterward — populated by app/worker/jobs/signal_capture.py +
    signal_outcome.py, not computed on request. See that job's module
    docstring for why this is a looser statistic than a real trade
    simulation (Backtest/Paper Trading), not a substitute for one.
    """
    query = select(Signal)
    if pair:
        from app.db.models.market import Instrument

        query = query.join(Instrument, Signal.instrument_id == Instrument.id).where(Instrument.symbol == pair)
    result = await session.execute(query)
    signals = result.scalars().all()

    buckets: dict[str, dict] = {b: {"total": 0, "pending": 0, "with_outcome": 0, "wins": 0, "fav": 0.0, "adv": 0.0, "after": 0.0, "tp": 0, "sl": 0} for b in SCORE_BUCKET_ORDER}
    for s in signals:
        b = buckets[_score_bucket(s.score)]
        b["total"] += 1
        if s.outcome_computed_at is None:
            b["pending"] += 1
            continue
        b["with_outcome"] += 1
        b["wins"] += 1 if (s.max_favorable_pips or 0) > (s.max_adverse_pips or 0) else 0
        b["fav"] += s.max_favorable_pips or 0.0
        b["adv"] += s.max_adverse_pips or 0.0
        b["after"] += s.price_after_horizon_pips or 0.0
        b["tp"] += 1 if s.tp_reached else 0
        b["sl"] += 1 if s.sl_reached else 0

    breakdown = []
    for key in SCORE_BUCKET_ORDER:
        b = buckets[key]
        n = b["with_outcome"]
        breakdown.append(
            {
                "score_bucket": key,
                "signal_count": b["total"],
                "pending_outcome_count": b["pending"],
                "outcome_count": n,
                "favorable_move_win_rate_pct": round(b["wins"] / n * 100, 2) if n else None,
                "avg_max_favorable_pips": round(b["fav"] / n, 2) if n else None,
                "avg_max_adverse_pips": round(b["adv"] / n, 2) if n else None,
                "avg_price_after_horizon_pips": round(b["after"] / n, 2) if n else None,
                "tp_reached_rate_pct": round(b["tp"] / n * 100, 2) if n else None,
                "sl_reached_rate_pct": round(b["sl"] / n * 100, 2) if n else None,
            }
        )
    return {"breakdown": breakdown}
