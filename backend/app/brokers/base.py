from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.brokers.schemas import (
    AccountSummary,
    BrokerPosition,
    Candle,
    Granularity,
    OrderRequest,
    OrderResult,
    PriceQuote,
)


@runtime_checkable
class MarketDataProvider(Protocol):
    """The read-only subset of `BrokerAdapter`: where prices/candles come from.
    Deliberately separate from `TradingBroker` (docs/15_PRODUCTION_READINESS_REVIEW.md
    "BrokerAdapter split") — a market data source and an order-execution target
    don't have to be the same provider. `app/brokers/factory.py` can configure
    them independently via `MARKET_DATA_PROVIDER` / `BROKER_PROVIDER`."""

    provider: str

    async def get_current_price(self, instrument: str) -> PriceQuote: ...

    async def get_candles(
        self,
        instrument: str,
        granularity: Granularity,
        count: int,
        from_time: datetime | None = None,
    ) -> list[Candle]: ...

    def stream_prices(self, instruments: list[str]) -> AsyncIterator[PriceQuote]: ...

    async def health_check(self) -> bool: ...


@runtime_checkable
class TradingBroker(Protocol):
    """The order-execution subset of `BrokerAdapter`: where orders actually go.
    See `MarketDataProvider` above for why this is split out. Using a different
    provider here than for market data introduces real risk — price the trading
    broker fills at may differ from the price the app displayed (spread/latency
    skew), and instrument symbols may not map 1:1 across providers
    (`docs/15_PRODUCTION_READINESS_REVIEW.md` documents the required warning)."""

    provider: str

    async def get_account(self) -> AccountSummary: ...

    async def get_positions(self) -> list[BrokerPosition]: ...

    async def create_order(self, order: OrderRequest) -> OrderResult: ...

    async def close_position(self, instrument: str) -> OrderResult: ...

    async def health_check(self) -> bool: ...


class BrokerAdapter(ABC):
    """The single boundary through which all broker-specific behavior must pass.

    Nothing outside `app/brokers/` may import a broker SDK or construct a
    broker-specific request payload — see docs/06_BROKER_API_DESIGN.md and
    docs/02_SYSTEM_ARCHITECTURE.md. Swapping the configured provider must never
    require a change anywhere else in the codebase.

    Structurally satisfies both `MarketDataProvider` and `TradingBroker` above —
    a concrete adapter (Mock/OANDA/GmoCoin) is usable as either or both without
    any adapter-side change; the split only affects how `app/brokers/factory.py`
    wires instances together.
    """

    provider: str

    @abstractmethod
    async def get_current_price(self, instrument: str) -> PriceQuote: ...

    @abstractmethod
    async def get_candles(
        self,
        instrument: str,
        granularity: Granularity,
        count: int,
        from_time: datetime | None = None,
    ) -> list[Candle]: ...

    @abstractmethod
    async def get_account(self) -> AccountSummary: ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    async def create_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def close_position(self, instrument: str) -> OrderResult: ...

    @abstractmethod
    def stream_prices(self, instruments: list[str]) -> AsyncIterator[PriceQuote]: ...

    async def health_check(self) -> bool:
        """Default implementation: a successful price fetch implies connectivity.
        Adapters may override with a cheaper/more specific check."""
        try:
            await self.get_current_price("USD_JPY")
            return True
        except Exception:
            return False
