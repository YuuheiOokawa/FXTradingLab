from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_db
from app.brokers.base import BrokerAdapter
from app.brokers.errors import BrokerError
from app.brokers.schemas import OrderRequest
from app.core.request_context import order_context
from app.db.models.market import Instrument
from app.db.models.trading import PaperOrder, PaperPosition
from app.services.order_orchestrator import OrderOrchestrator
from app.services.repo import get_or_create_paper_account
from app.services.risk_engine import RiskRejected

router = APIRouter(prefix="/paper", tags=["paper"])


@router.get("/account")
async def get_paper_account(session: AsyncSession = Depends(get_db)) -> dict:
    account = await get_or_create_paper_account(session)
    result = await session.execute(
        select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.status == "open")
    )
    open_positions = result.scalars().all()
    return {
        "balance": account.balance,
        "high_water_mark": account.high_water_mark,
        "currency": account.currency,
        "open_position_count": len(open_positions),
    }


@router.get("/positions")
async def list_positions(session: AsyncSession = Depends(get_db)) -> list[dict]:
    account = await get_or_create_paper_account(session)
    result = await session.execute(
        select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.status == "open")
    )
    from app.db.models.market import Instrument

    positions = result.scalars().all()
    out = []
    for p in positions:
        instrument = await session.get(Instrument, p.instrument_id)
        out.append(
            {
                "id": str(p.id),
                "instrument": instrument.symbol if instrument else None,
                "direction": p.direction,
                "size": p.size,
                "entry_price": p.entry_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "opened_at": p.opened_at.isoformat(),
            }
        )
    return out


class PaperOrderIn(BaseModel):
    instrument: str
    direction: str
    size: float
    order_type: str = "market"  # market | limit | stop
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    idempotency_key: str


@router.post("/orders")
async def submit_paper_order(
    body: PaperOrderIn,
    broker: BrokerAdapter = Depends(get_broker),
    session: AsyncSession = Depends(get_db),
) -> dict:
    orchestrator = OrderOrchestrator(broker)
    order = OrderRequest(
        instrument=body.instrument,
        direction=body.direction,  # type: ignore[arg-type]
        size=body.size,
        order_type=body.order_type,  # type: ignore[arg-type]
        limit_price=body.limit_price,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        idempotency_key=body.idempotency_key,
    )
    with order_context(order.idempotency_key):
        try:
            outcome = await orchestrator.submit_paper_order(session, order)
        except RiskRejected as exc:
            raise HTTPException(422, detail={"error": {"code": exc.code, "message": exc.message}}) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    return {
        "approved": outcome.approved,
        "order_id": str(outcome.order.id) if outcome.order else None,
        "position_id": str(outcome.position.id) if outcome.position else None,
        "status": outcome.order.status if outcome.order else None,
    }


@router.get("/orders")
async def list_paper_orders(status: str | None = None, session: AsyncSession = Depends(get_db)) -> list[dict]:
    account = await get_or_create_paper_account(session)
    query = select(PaperOrder).where(PaperOrder.account_id == account.id)
    if status:
        query = query.where(PaperOrder.status == status)
    query = query.order_by(PaperOrder.created_at.desc()).limit(200)
    result = await session.execute(query)
    orders = result.scalars().all()
    out = []
    for o in orders:
        instrument = await session.get(Instrument, o.instrument_id)
        out.append(
            {
                "id": str(o.id),
                "instrument": instrument.symbol if instrument else None,
                "direction": o.direction,
                "size": o.size,
                "order_type": o.order_type,
                "limit_price": o.limit_price,
                "stop_loss": o.stop_loss,
                "take_profit": o.take_profit,
                "status": o.status,
                "reject_reason": o.reject_reason,
                "created_at": o.created_at.isoformat(),
            }
        )
    return out


@router.post("/orders/{order_id}/cancel")
async def cancel_paper_order(
    order_id: uuid.UUID,
    broker: BrokerAdapter = Depends(get_broker),
    session: AsyncSession = Depends(get_db),
) -> dict:
    orchestrator = OrderOrchestrator(broker)
    try:
        order = await orchestrator.cancel_pending_order(session, order_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"id": str(order.id), "status": order.status}


@router.post("/positions/{position_id}/close")
async def close_position(
    position_id: uuid.UUID,
    broker: BrokerAdapter = Depends(get_broker),
    session: AsyncSession = Depends(get_db),
) -> dict:
    orchestrator = OrderOrchestrator(broker)
    with order_context(str(position_id)):
        try:
            position = await orchestrator.close_paper_position(session, position_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        except BrokerError as exc:
            # docs/15_PRODUCTION_READINESS_REVIEW.md: a broker outage during close
            # must surface as a clean, retryable error — not a raw 500 — and must
            # not leave the position in a half-closed state (nothing was written
            # to the DB yet at the point get_current_price fails, so the position
            # stays "open" and this is safe to simply retry).
            raise HTTPException(502, detail={"error": {"code": "BROKER_UNAVAILABLE", "message": str(exc)}}) from exc
    return {
        "id": str(position.id),
        "status": position.status,
        "close_price": position.close_price,
        "realized_pnl": position.realized_pnl,
    }
