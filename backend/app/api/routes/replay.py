from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_db
from app.brokers.base import BrokerAdapter
from app.brokers.schemas import Granularity
from app.db.models.market import Instrument
from app.services.market_data import ensure_instruments
from app.services.replay import close_open_decision, create_session, decide, get_session, is_at_end, step, visible_candles

router = APIRouter(prefix="/replay", tags=["replay"])


def _serialize_trade(t, reveal_explanation: bool) -> dict:
    return {
        "id": str(t.id),
        "decided_at_index": t.decided_at_index,
        "decided_at_time": t.decided_at_time.isoformat(),
        "action": t.action,
        "entry_price": t.entry_price,
        "stop_loss_pips": t.stop_loss_pips,
        "take_profit_pips": t.take_profit_pips,
        "exit_price": t.exit_price,
        "pnl": t.pnl,
        "max_favorable": round(t.max_favorable, 5),
        "max_adverse": round(t.max_adverse, 5),
        "judgment": t.judgment if reveal_explanation else None,
        "judgment_criteria": t.judgment_criteria if reveal_explanation else None,
        "explanation": t.signal_snapshot.get("reasons") if reveal_explanation else None,
    }


async def _serialize_session(session, instrument_symbol: str, reveal_explanations: bool) -> dict:
    visible = visible_candles(session)
    trades = [
        _serialize_trade(t, reveal_explanations or session.training_mode or t.exit_price is not None or t.action == "SKIP")
        for t in session.trades
    ]
    return {
        "id": str(session.id),
        "instrument": instrument_symbol,
        "granularity": session.granularity,
        "training_mode": session.training_mode,
        "start_time": session.start_time.isoformat(),
        "current_time": session.current_time.isoformat(),
        "speed": session.speed,
        "status": session.status,
        "initial_balance": session.initial_balance,
        "current_balance": session.current_balance,
        "current_index": session.current_index,
        "total_candles": len(session.candles),
        "is_at_end": is_at_end(session),
        "has_open_decision": any(t.action != "SKIP" and t.exit_price is None for t in session.trades),
        "candles": [c.model_dump(mode="json") for c in visible[-500:]],
        "decisions": trades,
    }


class CreateReplayIn(BaseModel):
    instrument: str
    granularity: Granularity = Granularity.M15
    candle_count: int = 800
    training_mode: bool = False
    initial_balance: float = 1_000_000.0


@router.post("/sessions")
async def create_replay_session(
    body: CreateReplayIn,
    broker: BrokerAdapter = Depends(get_broker),
    db: AsyncSession = Depends(get_db),
) -> dict:
    candles = await broker.get_candles(body.instrument, body.granularity, body.candle_count)
    if len(candles) < 10:
        raise HTTPException(400, "not enough candle history to start a replay session")
    instruments = await ensure_instruments([body.instrument])
    instrument = instruments[body.instrument]
    session = await create_session(
        db, instrument.id, body.granularity.value, candles, body.training_mode, body.initial_balance
    )
    return await _serialize_session(session, body.instrument, reveal_explanations=False)


async def _load_session_or_404(db: AsyncSession, session_id: uuid.UUID):
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(404, "replay session not found")
    return session


async def _symbol_for(db: AsyncSession, instrument_id: uuid.UUID) -> str:
    instrument = await db.get(Instrument, instrument_id)
    return instrument.symbol if instrument else "UNKNOWN"


@router.get("/sessions/{session_id}")
async def get_replay_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _load_session_or_404(db, session_id)
    symbol = await _symbol_for(db, session.instrument_id)
    return await _serialize_session(session, symbol, reveal_explanations=False)


@router.post("/sessions/{session_id}/step")
async def step_replay_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _load_session_or_404(db, session_id)
    new_candle = await step(db, session)
    symbol = await _symbol_for(db, session.instrument_id)
    result = await _serialize_session(session, symbol, reveal_explanations=False)
    result["new_candle"] = new_candle.model_dump(mode="json") if new_candle else None
    return result


class DecideIn(BaseModel):
    action: str  # BUY | SELL | SKIP
    stop_loss_pips: float | None = None
    take_profit_pips: float | None = None


@router.post("/sessions/{session_id}/decide")
async def decide_replay_session(session_id: uuid.UUID, body: DecideIn, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _load_session_or_404(db, session_id)
    if body.action not in ("BUY", "SELL", "SKIP"):
        raise HTTPException(400, "action must be BUY, SELL, or SKIP")
    await decide(db, session, body.action, body.stop_loss_pips, body.take_profit_pips)  # type: ignore[arg-type]
    symbol = await _symbol_for(db, session.instrument_id)
    return await _serialize_session(session, symbol, reveal_explanations=True)


@router.post("/sessions/{session_id}/close")
async def close_replay_decision(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _load_session_or_404(db, session_id)
    trade = await close_open_decision(db, session)
    if trade is None:
        raise HTTPException(400, "no open decision to close")
    symbol = await _symbol_for(db, session.instrument_id)
    return await _serialize_session(session, symbol, reveal_explanations=True)
