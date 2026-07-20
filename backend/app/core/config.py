"""Application configuration.

All secrets and environment-dependent values are read from environment variables
only (see docs/11_SECURITY.md). Never hardcode a credential here or anywhere else.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "staging", "production"]
BrokerEnvironment = Literal["practice", "live"]
BrokerProvider = Literal["mock", "oanda", "gmo_coin"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: AppEnv = "development"
    app_api_token: str | None = Field(default=None, description="Bearer token for /api/v1/* and /ws/* in non-dev envs")
    log_level: str = "INFO"
    # "text" (human-readable, default — good for local dev) | "json" (structured,
    # one JSON object per line — for log aggregators in real deployments).
    log_format: str = "text"
    service_name: str = "fx-trading-lab"
    # Comma-separated allowed CORS origins for non-development environments, e.g.
    # "https://fxlab.example.com". Deliberately NOT wildcarded outside dev — see
    # docs/15_PRODUCTION_READINESS_REVIEW.md "Security". Empty in production means
    # the browser frontend's own origin must be explicitly listed here or every
    # request will be blocked; this is intentionally a hard failure mode rather
    # than silently allowing "*" against a real deployment.
    allowed_origins: str = ""

    # --- Database ---
    database_url: str = "postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Broker selection ---
    # `broker_provider` is used for BOTH market data and trading unless
    # `market_data_provider` is set to something different — see
    # docs/15_PRODUCTION_READINESS_REVIEW.md "BrokerAdapter split" and
    # app/brokers/factory.py. Splitting them is a real capability (e.g. a wider
    # market-data source with a narrower/gated trading broker) but carries real
    # risk (spread/latency skew, symbol mapping) that factory.py warns about.
    broker_provider: BrokerProvider = "mock"
    market_data_provider: BrokerProvider | None = None
    broker_environment: BrokerEnvironment = "practice"

    # OANDA
    oanda_api_token: str | None = None
    oanda_account_id: str | None = None
    oanda_environment: BrokerEnvironment = "practice"

    # GMO Coin (stub adapter, see docs/06_BROKER_API_DESIGN.md)
    gmo_coin_api_key: str | None = None
    gmo_coin_api_secret: str | None = None

    # --- Market data ---
    poll_interval_ms: int = 2000
    price_stale_seconds: int = 10
    tick_retention_days: int = 7
    candle_1m_retention_days: int = 90
    default_watchlist: str = "USD_JPY,EUR_JPY,GBP_JPY,EUR_USD"

    # --- Live trading gate (see docs/10_RISK_MANAGEMENT.md) ---
    # Condition 1 of 3. MUST default to false in every environment, including production.
    live_trading_enabled: bool = False

    # --- AI (optional; app works fully without this) ---
    ai_api_key: str | None = None
    ai_provider: str = "anthropic"

    # --- Notifications (future channels) ---
    discord_webhook_url: str | None = None
    line_notify_token: str | None = None

    @field_validator("live_trading_enabled")
    @classmethod
    def _live_trading_never_implicit(cls, v: bool) -> bool:
        # Defensive: this validator exists so that a future refactor can't quietly
        # change the default without this file's intent being obvious at review time.
        return bool(v)

    @property
    def watchlist(self) -> list[str]:
        return [s.strip() for s in self.default_watchlist.split(",") if s.strip()]

    @property
    def auth_required(self) -> bool:
        return self.app_env != "development"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [s.strip() for s in self.allowed_origins.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
