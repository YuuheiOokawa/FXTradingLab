from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_app_settings, get_db, get_live_trading_broker
from app.brokers.base import BrokerAdapter
from app.brokers.errors import BrokerError
from app.brokers.schemas import OrderRequest
from app.core.config import Settings, get_settings
from app.core.request_context import order_context
from app.services.order_orchestrator import LiveTradingDisabled, OrderOrchestrator
from app.services.repo import get_or_create_risk_settings
from app.services.risk_engine import RiskRejected

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/preflight")
async def broker_preflight(broker: BrokerAdapter = Depends(get_live_trading_broker)) -> dict:
    """Validates the configured TRADING broker's credentials actually work —
    authentication, account access, price access — WITHOUT ever placing an
    order (docs/15_PRODUCTION_READINESS_REVIEW.md "Broker Credential
    Validation"). Previously the only way to discover a broker misconfig
    (wrong token, wrong account ID, wrong environment) was to wait for it to
    surface as a confusing failure somewhere else at runtime; this lets an
    operator check right after entering credentials, before relying on them
    for anything.

    Each check is independent and captured separately — a failure in one
    doesn't stop the others from running, so a single call diagnoses
    "auth is fine but this account has no access to this instrument" as
    distinctly from "the token itself is wrong".
    """
    settings = get_settings()
    checks: dict[str, dict] = {}

    try:
        account = await broker.get_account()
        checks["authentication_and_account"] = {"ok": True, "account_id": account.account_id, "currency": account.currency}
    except BrokerError as exc:
        checks["authentication_and_account"] = {"ok": False, "error": str(exc)}

    checks["instruments"] = {}
    for symbol in settings.watchlist:
        try:
            quote = await broker.get_current_price(symbol)
            checks["instruments"][symbol] = {"ok": True, "bid": quote.bid, "ask": quote.ask}
        except BrokerError as exc:
            checks["instruments"][symbol] = {"ok": False, "error": str(exc)}

    all_ok = checks["authentication_and_account"]["ok"] and all(v["ok"] for v in checks["instruments"].values())
    return {"provider": broker.provider, "environment": settings.broker_environment, "all_ok": all_ok, "checks": checks}


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


class LiveOrderPreviewIn(BaseModel):
    instrument: str
    direction: str
    size: float
    stop_loss: float | None = None
    take_profit: float | None = None


@router.post("/orders/preview")
async def preview_live_order(
    body: LiveOrderPreviewIn,
    broker: BrokerAdapter = Depends(get_live_trading_broker),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Runs Risk Engine validation and order construction against the real
    broker's real account state — never places an order (see
    OrderOrchestrator.preview_live_order's docstring for why that's a
    structural guarantee, not a flag). Always available regardless of the
    three LIVE gates, since there's nothing here for those gates to protect
    against."""
    orchestrator = OrderOrchestrator(broker)
    order = OrderRequest(
        instrument=body.instrument,
        direction=body.direction,  # type: ignore[arg-type]
        size=body.size,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        idempotency_key="preview-only",  # never persisted as a real order; see preview_live_order
    )
    return await orchestrator.preview_live_order(session, order)


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
    with order_context(order.idempotency_key):
        try:
            await orchestrator.submit_live_order(session, order, confirm_live=body.confirm_live)
        except LiveTradingDisabled as exc:
            raise HTTPException(
                403, detail={"error": {"code": "LIVE_TRADING_DISABLED", "missing_gates": exc.missing_gates}}
            ) from exc
        except RiskRejected as exc:
            raise HTTPException(422, detail={"error": {"code": exc.code, "message": exc.message}}) from exc
