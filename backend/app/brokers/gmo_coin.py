"""GMO Coin 外国為替FX adapter — documented stub, not yet implemented.

docs/06_BROKER_API_DESIGN.md explains why this is the recommended real path to an
actual Japan-resident *live* account (unlike OANDA Japan's API, it doesn't require a
Gold-tier balance gate): GMO Coin exposes a genuinely open individual-accessible
REST API at https://api.coin.z.com/fxdocs/ with Public (unauthenticated market data)
and Private (HMAC-signed, account/order) endpoint groups.

This class exists to prove the `BrokerAdapter` boundary supports a second real
broker without changing anything outside `app/brokers/` — implementing it for real
requires a funded GMO Coin account to test against, which isn't available in this
build environment. Each method raises `NotImplementedError` with a pointer to the
relevant fxdocs section so a future implementer has the exact shape to fill in.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from app.brokers.base import BrokerAdapter
from app.brokers.schemas import (
    AccountSummary,
    BrokerPosition,
    Candle,
    Granularity,
    OrderRequest,
    OrderResult,
    PriceQuote,
)

_NOT_IMPLEMENTED = (
    "GmoCoinAdapter.{method} is not implemented yet. See "
    "https://api.coin.z.com/fxdocs/ ({endpoint}) and docs/06_BROKER_API_DESIGN.md. "
    "Set BROKER_PROVIDER=oanda or leave unset (mock) until this is built."
)


class GmoCoinAdapter(BrokerAdapter):
    provider = "gmo_coin"

    def __init__(self, api_key: str, api_secret: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret

    async def get_current_price(self, instrument: str) -> PriceQuote:
        raise NotImplementedError(
            _NOT_IMPLEMENTED.format(method="get_current_price", endpoint="Public API /v1/ticker")
        )

    async def get_candles(
        self,
        instrument: str,
        granularity: Granularity,
        count: int,
        from_time: datetime | None = None,
    ) -> list[Candle]:
        raise NotImplementedError(
            _NOT_IMPLEMENTED.format(method="get_candles", endpoint="Public API /v1/klines")
        )

    async def get_account(self) -> AccountSummary:
        raise NotImplementedError(
            _NOT_IMPLEMENTED.format(method="get_account", endpoint="Private API /v1/account/assets")
        )

    async def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError(
            _NOT_IMPLEMENTED.format(method="get_positions", endpoint="Private API /v1/openPositions")
        )

    async def create_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError(
            _NOT_IMPLEMENTED.format(method="create_order", endpoint="Private API POST /v1/order")
        )

    async def close_position(self, instrument: str) -> OrderResult:
        raise NotImplementedError(
            _NOT_IMPLEMENTED.format(method="close_position", endpoint="Private API POST /v1/closeBulkOrder")
        )

    async def stream_prices(self, instruments: list[str]) -> AsyncIterator[PriceQuote]:
        raise NotImplementedError(
            _NOT_IMPLEMENTED.format(method="stream_prices", endpoint="WebSocket Public API")
        )
        yield  # pragma: no cover - makes this an async generator for the type checker
