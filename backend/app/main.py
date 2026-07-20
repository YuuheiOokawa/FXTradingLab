from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from app.api.deps import require_auth
from app.api.routes import ai, backtest, journal, live, market, paper, replay, signals, simulate, system
from app.brokers.factory import get_market_data_provider
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis_client import get_redis
from app.core.request_context import set_request_id
from app.db.session import AsyncSessionLocal
from app.ws import prices as ws_prices
from app.ws import system as ws_system

_start_time = time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    if settings.app_env == "production" and not settings.app_api_token:
        raise RuntimeError(
            "APP_API_TOKEN must be set when APP_ENV=production (docs/11_SECURITY.md) — "
            "refusing to boot with auth silently disabled."
        )
    if settings.app_env != "development" and not settings.allowed_origins_list:
        logger.warning(
            "ALLOWED_ORIGINS is empty in a non-development environment; the browser "
            "frontend's own origin must be listed there or every cross-origin "
            "request will be blocked by CORS. Same-origin deployments (frontend "
            "and backend behind one reverse-proxy domain) don't need this."
        )
    yield


app = FastAPI(
    title="FX Trading Lab API",
    description="Personal FX monitoring / analysis / simulation / backtest / trading backend.",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Every log line emitted while handling this request carries the same
    request_id (docs/15_PRODUCTION_READINESS_REVIEW.md "Observability") —
    accepts an inbound X-Request-ID (e.g. from a reverse proxy) or mints one."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    set_request_id(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    # Non-development environments must explicitly list their frontend's origin(s)
    # via ALLOWED_ORIGINS (comma-separated) — never wildcarded outside dev. An
    # empty list here is a safe-by-default "block everything" rather than an
    # accidental "allow everything"; see docs/15_PRODUCTION_READINESS_REVIEW.md.
    allow_origins=["*"] if settings.app_env == "development" else settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1_dependencies = [Depends(require_auth)]

app.include_router(market.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(signals.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(simulate.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(replay.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(backtest.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(paper.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(live.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(journal.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(system.router, prefix="/api/v1", dependencies=api_v1_dependencies)
app.include_router(ai.router, prefix="/api/v1", dependencies=api_v1_dependencies)

# WebSocket endpoints can't use the REST bearer-auth dependency (browsers can't set
# custom headers on the WS handshake); each one checks a `?token=` query param
# instead via app/ws/auth.py, enforced identically to REST outside development.
app.include_router(ws_prices.router)
app.include_router(ws_system.router)


@app.get("/health")
async def health() -> dict:
    """Process liveness only — does not touch DB/Redis/broker. A load balancer
    restarting the process on /health failure would be pointless if the
    process itself is fine but a dependency is down; that's what /ready is
    for (docs/15_PRODUCTION_READINESS_REVIEW.md "Observability")."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    """Checks DB, Redis, and the market-data broker. Returns 200 with
    per-dependency status even on partial failure (not a bare 503) so a
    human/dashboard can see exactly which dependency is down, not just that
    *something* is — deliberately does NOT fail the whole app on a broker
    outage alone (broker issues are common/transient and the app's
    non-trading features — journal, analytics, settings — stay usable)."""
    from fastapi.responses import JSONResponse

    checks: dict[str, bool] = {}

    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        logger.exception("readiness check: database failed")
        checks["database"] = False

    try:
        await get_redis().ping()
        checks["redis"] = True
    except Exception:
        logger.exception("readiness check: redis failed")
        checks["redis"] = False

    try:
        checks["market_data_broker"] = await get_market_data_provider().health_check()
    except Exception:
        logger.exception("readiness check: broker health check failed")
        checks["market_data_broker"] = False

    # Only DB/Redis are load-bearing for the app to be considered "ready" —
    # see docstring above for why a broker outage alone doesn't fail this.
    overall_ready = checks["database"] and checks["redis"]
    return JSONResponse(status_code=200 if overall_ready else 503, content={"ready": overall_ready, "checks": checks})


@app.get("/metrics")
async def metrics() -> dict:
    """Plain-JSON operational metrics — not Prometheus exposition format,
    which would need an extra dependency this single-operator app doesn't
    otherwise need; this is enough to answer "is the worker actually seeing
    fresh prices" from the System page or a quick curl."""
    redis = get_redis()
    settings_ = get_settings()
    broker_connected = (await redis.get("system:broker_connected")) == "1"
    per_instrument: dict[str, dict] = {}
    for symbol in settings_.watchlist:
        latest = await redis.hgetall(f"price:{symbol}:latest")
        per_instrument[symbol] = {
            "last_tick_ts": latest.get("ts"),
            "mid": float(latest["mid"]) if "mid" in latest else None,
        }
    return {
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
        "broker_connected": broker_connected,
        "instruments": per_instrument,
    }
