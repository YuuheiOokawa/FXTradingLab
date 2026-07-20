from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_broker
from app.brokers.base import BrokerAdapter
from app.brokers.schemas import Granularity
from app.services.replay import close_open_decision, create_session, decide, get_session, step

router = APIRouter(prefix="/replay", tags=["replay"])


def _serialize_reasons(signal) -> list[dict] | None:
    if signal is None:
        return None
    return [{"status": r.status, "text": r.text, "points": r.points} for r in signal.reasons]


def _serialize_session(session, reveal_explanations: bool) -> dict:
    visible = session.visible_candles()
    decisions = []
    for d in session.decisions:
        show_explanation = reveal_explanations or session.training_mode or d.exit_price is not None
        decisions.append(
            {
                "decided_at_index": d.decided_at_index,
                "action": d.action,
                "entry_price": d.entry_price,
                "exit_price": d.exit_price,
                "pnl": d.pnl,
                "max_favorable": round(d.max_favorable, 5),
                "max_adverse": round(d.max_adverse, 5),
                "explanation": _serialize_reasons(d.signal_at_decision) if show_explanation else None,
            }
        )
    return {
        "id": session.id,
        "instrument": session.instrument,
        "granularity": session.granularity,
        "training_mode": session.training_mode,
        "current_index": session.current_index,
        "total_candles": len(session.candles),
        "is_at_end": session.is_at_end(),
        "has_open_decision": session.open_decision is not None,
        "candles": [c.model_dump(mode="json") for c in visible[-500:]],
        "decisions": decisions,
    }


class CreateReplayIn(BaseModel):
    instrument: str
    granularity: Granularity = Granularity.M15
    candle_count: int = 800
    training_mode: bool = False


@router.post("/sessions")
async def create_replay_session(body: CreateReplayIn, broker: BrokerAdapter = Depends(get_broker)) -> dict:
    candles = await broker.get_candles(body.instrument, body.granularity, body.candle_count)
    session = create_session(body.instrument, body.granularity.value, candles, body.training_mode)
    return _serialize_session(session, reveal_explanations=False)


@router.get("/sessions/{session_id}")
async def get_replay_session(session_id: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404, "replay session not found")
    return _serialize_session(session, reveal_explanations=False)


@router.post("/sessions/{session_id}/step")
async def step_replay_session(session_id: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404, "replay session not found")
    new_candle = step(session)
    result = _serialize_session(session, reveal_explanations=False)
    result["new_candle"] = new_candle.model_dump(mode="json") if new_candle else None
    return result


class DecideIn(BaseModel):
    action: str  # BUY | SELL | SKIP


@router.post("/sessions/{session_id}/decide")
async def decide_replay_session(session_id: str, body: DecideIn) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404, "replay session not found")
    if body.action not in ("BUY", "SELL", "SKIP"):
        raise HTTPException(400, "action must be BUY, SELL, or SKIP")
    decide(session, body.action)  # type: ignore[arg-type]
    return _serialize_session(session, reveal_explanations=True)


@router.post("/sessions/{session_id}/close")
async def close_replay_decision(session_id: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404, "replay session not found")
    record = close_open_decision(session)
    if record is None:
        raise HTTPException(400, "no open decision to close")
    return _serialize_session(session, reveal_explanations=True)
