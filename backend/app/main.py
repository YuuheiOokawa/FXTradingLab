from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_auth
from app.api.routes import ai, backtest, journal, live, market, paper, replay, signals, simulate, system
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.ws import prices as ws_prices
from app.ws import system as ws_system


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    if settings.app_env == "production" and not settings.app_api_token:
        raise RuntimeError(
            "APP_API_TOKEN must be set when APP_ENV=production (docs/11_SECURITY.md) — "
            "refusing to boot with auth silently disabled."
        )
    yield


app = FastAPI(
    title="FX Trading Lab API",
    description="Personal FX monitoring / analysis / simulation / backtest / trading backend.",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
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

# WebSocket endpoints are not behind the REST bearer-auth dependency (browsers can't
# set custom headers on the WS handshake); see docs/11_SECURITY.md for the
# same-origin/deployment-network assumptions this relies on in v1.
app.include_router(ws_prices.router)
app.include_router(ws_system.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
