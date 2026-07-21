"""Test configuration. Sets env vars *before* any `app.*` import so
`app.core.config.get_settings()` (which is `lru_cache`d) picks up the test database
on its first call — see docs/13_TEST_STRATEGY.md for why this uses a real Postgres
test database rather than mocking the ORM.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BROKER_PROVIDER", "mock")
os.environ.setdefault("LIVE_TRADING_ENABLED", "false")

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.session import AsyncSessionLocal, engine

TABLES_TO_TRUNCATE = [
    "market_ticks",
    "candles",
    "signals",
    "backtest_trades",
    "backtests",
    "paper_orders",
    "paper_positions",
    "paper_accounts",
    "live_orders",
    "live_positions",
    "trade_journals",
    "risk_settings",
    "system_events",
    "notifications",
    "audit_logs",
    "strategy_configs",
    "strategies",
    "instruments",
    "broker_accounts",
    "users",
]


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def _reset_broker_singleton():
    from app.brokers.factory import reset_broker_adapter

    reset_broker_adapter()
    yield
    reset_broker_adapter()
