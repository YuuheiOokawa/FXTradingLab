"""GMO Coin 外国為替FX adapter — documented stub, not yet implemented.

IMPORTANT — do not confuse GMO Coin's two separate API products:
- Crypto API (BTC_JPY, ETH_JPY, ...): https://api.coin.z.com/docs/
- FX API (USD_JPY, EUR_JPY, ...):      https://api.coin.z.com/fxdocs/
  (docs live under api.coin.z.com/fxdocs; the actual request base host is
  forex-api.coin.z.com per those docs — verify the exact paths directly before
  implementing, see docs/16_BROKER_SELECTION_REVIEW.md for the verification
  trail). These are legally and technically distinct: GMO Coin, Inc. holds both
  a crypto-exchange registration and, since its Oct 2023 FX launch, a separate
  Financial Instruments Business Operator registration that permits margin FX.
  Pointing this adapter at the crypto host/symbols by mistake would silently
  trade the wrong asset class — this is exactly the kind of mistake
  docs/16_BROKER_SELECTION_REVIEW.md's re-verification pass was checking for.

docs/06_BROKER_API_DESIGN.md explains why this is the recommended real path to an
actual Japan-resident *live* account (unlike OANDA Japan's API, it doesn't require a
Gold-tier balance gate): GMO Coin's FX API has Public (unauthenticated market data)
and Private (HMAC-signed, account/order) endpoint groups, 21 currency pairs as of
2026-05 including all four of this app's default watchlist pairs.

This class exists to prove the `BrokerAdapter` boundary supports a second real
broker without changing anything outside `app/brokers/` — implementing it for real
requires (a) a funded GMO Coin FX account to test against, which isn't available in
this build environment, and (b) a direct read of the live fxdocs pages to confirm
exact endpoint paths/payload shapes (automated fetches of api.coin.z.com hit
anti-bot protection during research — see docs/16). Each method raises
`NotImplementedError` with a pointer to the relevant fxdocs section so a future
implementer has the exact shape to fill in.
"""
from __future__ import annotations

import hashlib
import hmac
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


def generate_private_api_signature(api_secret: str, timestamp_ms: str, method: str, path: str, body: str = "") -> str:
    """HMAC-SHA256 signature for GMO Coin's FX Private API, per the
    documented scheme (timestamp + method + path + body, HMAC-SHA256 keyed
    by the API secret, hex digest) — see docs/06_BROKER_API_DESIGN.md and
    docs/16_BROKER_SELECTION_REVIEW.md.

    CAVEAT (docs/15_PRODUCTION_READINESS_REVIEW.md "GMO Coin Fixture Based
    Test"): this was implemented from the publicly documented algorithm
    (corroborated across multiple independent third-party write-ups) rather
    than a direct read of the live fxdocs page — automated fetches of
    api.coin.z.com hit anti-bot protection during this and the prior
    review's research (see docs/16). `tests/test_gmo_coin_signature.py`
    verifies this function is internally consistent (deterministic, keyed
    correctly, sensitive to every input) — it does NOT verify the result
    matches what GMO Coin's real server actually expects, since that can
    only be confirmed against a real account. Verify against
    https://api.coin.z.com/fxdocs/ directly before relying on this for a
    real account, and do not treat a passing test suite as proof this is
    correct against the live API.

    `path` must start with `/v1` and must NOT include a `/private` prefix
    segment, per the documented scheme (GET requests use an empty body).
    """
    message = f"{timestamp_ms}{method.upper()}{path}{body}"
    return hmac.new(api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


class GmoCoinAdapter(BrokerAdapter):
    provider = "gmo_coin"

    def __init__(self, api_key: str, api_secret: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret

    def _sign(self, timestamp_ms: str, method: str, path: str, body: str = "") -> str:
        return generate_private_api_signature(self._api_secret, timestamp_ms, method, path, body)

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
