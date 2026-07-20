from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_app_settings, get_db, get_live_trading_broker
from app.brokers.base import BrokerAdapter
from app.brokers.errors import BrokerError
from app.brokers.schemas import OrderRequest
from app.core.config import Settings
from app.services.order_orchestrator import LiveTradingDisabled, OrderOrchestrator
from app.services.repo import get_or_create_risk_settings
from app.services.risk_engine import RiskRejected

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/status")
async def live_status(
    session: AsyncSession = Depends(get_db), settings: Settings = Depends(get_app_settings)
) -> dict:
    """Reports which of the three LIVE gates (docs/10_RISK_MANAGEMENT.md) are
    currently satisfied, without ever accepting an order — used by the Settings UI
    to show the operator exactly what stands between them and LIVE trading."""
    risk_settings = await get_or_create_risk_settings(session)
    return {
        "env_var_enabled": settings.live_trading_enabled,
        "admin_setting_enabled": risk_settings.live_trading_admin_enabled,
        "per_order_confirmation_required": True,
        "ready": settings.live_trading_enabled and risk_settings.live_trading_admin_enabled,
    }


@router.get("/account")
async def get_live_account(broker: BrokerAdapter = Depends(get_live_trading_broker)) -> dict:
    try:
        account = await broker.get_account()
    except BrokerError as exc:
        raise HTTPException(502, f"broker error: {exc}") from exc
    return account.model_dump()


@router.get("/positions")
async def get_live_positions(broker: BrokerAdapter = Depends(get_live_trading_broker)) -> list[dict]:
    try:
        positions = await broker.get_positions()
    except BrokerError as exc:
        raise HTTPException(502, f"broker error: {exc}") from exc
    return [p.model_dump() for p in positions]


class LiveOrderIn(BaseModel):
    instrument: str
    direction: str
    size: float
    stop_loss: float | None = None
    take_profit: float | None = None
    idempotency_key: str
    confirm_live: bool = False


@router.post("/orders")
async def submit_live_order(
    body: LiveOrderIn,
    broker: BrokerAdapter = Depends(get_live_trading_broker),
    session: AsyncSession = Depends(get_db),
) -> dict:
    orchestrator = OrderOrchestrator(broker)
    order = OrderRequest(
        instrument=body.instrument,
        direction=body.direction,  # type: ignore[arg-type]
        size=body.size,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        idempotency_key=body.idempotency_key,
    )
    try:
        await orchestrator.submit_live_order(session, order, confirm_live=body.confirm_live)
    except LiveTradingDisabled as exc:
        raise HTTPException(403, detail={"error": {"code": "LIVE_TRADING_DISABLED", "missing_gates": exc.missing_gates}}) from exc
    except RiskRejected as exc:
        raise HTTPException(422, detail={"error": {"code": exc.code, "message": exc.message}}) from exc
