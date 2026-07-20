from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_db, get_live_trading_broker
from app.brokers.base import BrokerAdapter
from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.db.models.journal import Notification
from app.services.order_orchestrator import OrderOrchestrator
from app.services.repo import get_or_create_risk_settings

router = APIRouter(tags=["system"])


@router.get("/system/status")
async def system_status(
    market_data_broker: BrokerAdapter = Depends(get_broker),
    trading_broker: BrokerAdapter = Depends(get_live_trading_broker),
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    redis = get_redis()
    broker_connected = (await redis.get("system:broker_connected")) == "1"
    risk_settings = await get_or_create_risk_settings(session)
    providers_split = market_data_broker.provider != trading_broker.provider
    return {
        "broker_provider": trading_broker.provider,
        "market_data_provider": market_data_broker.provider,
        "providers_split": providers_split,
        "broker_environment": settings.broker_environment,
        "broker_connected": broker_connected,
        "kill_switch_active": risk_settings.kill_switch_active,
        "auto_mode": risk_settings.auto_mode,
        "live_trading_enabled_env": settings.live_trading_enabled,
        "live_trading_admin_enabled": risk_settings.live_trading_admin_enabled,
        "app_env": settings.app_env,
        "watchlist": settings.watchlist,
    }


class RiskSettingsIn(BaseModel):
    max_risk_per_trade_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_drawdown_pct: float | None = None
    max_concurrent_positions: int | None = None
    max_same_symbol_positions: int | None = None
    consecutive_loss_stop_count: int | None = None
    max_spread_pips_default: float | None = None
    auto_mode: str | None = None
    live_trading_admin_enabled: bool | None = None


def _serialize_risk_settings(rs) -> dict:
    return {
        "max_risk_per_trade_pct": rs.max_risk_per_trade_pct,
        "max_daily_loss_pct": rs.max_daily_loss_pct,
        "max_drawdown_pct": rs.max_drawdown_pct,
        "max_concurrent_positions": rs.max_concurrent_positions,
        "max_same_symbol_positions": rs.max_same_symbol_positions,
        "consecutive_loss_stop_count": rs.consecutive_loss_stop_count,
        "max_spread_pips_default": rs.max_spread_pips_default,
        "kill_switch_active": rs.kill_switch_active,
        "auto_mode": rs.auto_mode,
        "live_trading_admin_enabled": rs.live_trading_admin_enabled,
    }


@router.get("/settings/risk")
async def get_risk_settings(session: AsyncSession = Depends(get_db)) -> dict:
    rs = await get_or_create_risk_settings(session)
    return _serialize_risk_settings(rs)


@router.put("/settings/risk")
async def update_risk_settings(body: RiskSettingsIn, session: AsyncSession = Depends(get_db)) -> dict:
    rs = await get_or_create_risk_settings(session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rs, field, value)
    await session.commit()
    await session.refresh(rs)
    return _serialize_risk_settings(rs)


class KillSwitchIn(BaseModel):
    activate: bool
    flatten_positions: bool = False


@router.post("/live/kill-switch")
async def kill_switch(
    body: KillSwitchIn, broker: BrokerAdapter = Depends(get_broker), session: AsyncSession = Depends(get_db)
) -> dict:
    orchestrator = OrderOrchestrator(broker)
    if body.activate:
        return await orchestrator.activate_kill_switch(session, body.flatten_positions)
    return await orchestrator.deactivate_kill_switch(session)


@router.get("/notifications")
async def list_notifications(unread_only: bool = False, session: AsyncSession = Depends(get_db)) -> list[dict]:
    query = select(Notification).order_by(Notification.ts.desc()).limit(100)
    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712
    result = await session.execute(query)
    return [
        {
            "id": str(n.id),
            "ts": n.ts.isoformat(),
            "channel": n.channel,
            "kind": n.kind,
            "title": n.title,
            "body": n.body,
            "is_read": n.is_read,
        }
        for n in result.scalars().all()
    ]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    notification = await session.get(Notification, notification_id)
    if notification is None:
        return {"ok": False}
    notification.is_read = True
    await session.commit()
    return {"ok": True}
