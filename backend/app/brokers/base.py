from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from app.brokers.schemas import (
    AccountSummary,
    BrokerPosition,
    Candle,
    Granularity,
    OrderRequest,
    OrderResult,
    PriceQuote,
)


class BrokerAdapter(ABC):
    """The single boundary through which all broker-specific behavior must pass.

    Nothing outside `app/brokers/` may import a broker SDK or construct a
    broker-specific request payload — see docs/06_BROKER_API_DESIGN.md and
    docs/02_SYSTEM_ARCHITECTURE.md. Swapping the configured provider must never
    require a change anywhere else in the codebase.
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
