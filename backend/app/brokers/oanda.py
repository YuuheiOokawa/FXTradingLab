"""OANDA v20 REST/Streaming adapter.

Reference implementation of a real broker integration — see
docs/06_BROKER_API_DESIGN.md for why OANDA's v20 API shape was chosen as the
reference (industry-standard, well documented, practice accounts are trivial to
obtain for development) even though a Japan-resident's *live* account must go
through oanda.jp specifically (which exposes a compatible but gated API — see the
same doc). Instrument codes (`USD_JPY`, ...) and granularity codes (`M1`, `H4`, `D`,
...) are OANDA's native format, which is why `app/brokers/schemas.py` reuses them
directly instead of inventing an internal dialect.

Credentials come only from environment variables (`OANDA_API_TOKEN`,
`OANDA_ACCOUNT_ID`) — see app/core/config.py. This module never hardcodes a token.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx

from app.brokers.base import BrokerAdapter
from app.brokers.errors import (
    BrokerAuthError,
    BrokerConnectionError,
    BrokerOrderRejected,
    BrokerRateLimitError,
)
from app.brokers.schemas import (
    AccountSummary,
    BrokerPosition,
    Candle,
    Direction,
    Granularity,
    OrderRequest,
    OrderResult,
    PriceQuote,
)

_REST_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}
_STREAM_HOSTS = {
    "practice": "https://stream-fxpractice.oanda.com",
    "live": "https://stream-fxtrade.oanda.com",
}


class OandaAdapter(BrokerAdapter):
    provider = "oanda"

    def __init__(self, api_token: str, account_id: str, environment: str = "practice") -> None:
        if environment not in _REST_HOSTS:
            raise ValueError(f"invalid OANDA environment: {environment}")
        self._account_id = account_id
        self._environment = environment
        self._rest_base = _REST_HOSTS[environment]
        self._stream_base = _STREAM_HOSTS[environment]
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def _client(self, base_url: str, timeout: float = 10.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=base_url, headers=self._headers, timeout=timeout)

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 401 or resp.status_code == 403:
            raise BrokerAuthError(f"OANDA auth failed: {resp.status_code} {resp.text}")
        if resp.status_code == 429:
            raise BrokerRateLimitError("OANDA rate limit exceeded")
        if resp.status_code >= 500:
            raise BrokerConnectionError(f"OANDA server error: {resp.status_code}")
        if resp.status_code >= 400:
            raise BrokerOrderRejected(resp.text)

    async def get_current_price(self, instrument: str) -> PriceQuote:
        try:
            async with await self._client(self._rest_base) as client:
                resp = await client.get(
                    f"/v3/accounts/{self._account_id}/pricing",
                    params={"instruments": instrument},
                )
        except httpx.RequestError as exc:
            raise BrokerConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        data = resp.json()
        prices = data.get("prices", [])
        if not prices:
            raise BrokerConnectionError(f"no price returned for {instrument}")
        p = prices[0]
        bid = float(p["bids"][0]["price"])
        ask = float(p["asks"][0]["price"])
        return PriceQuote(instrument=instrument, bid=bid, ask=ask, ts=datetime.now(UTC))

    async def get_candles(
        self,
        instrument: str,
        granularity: Granularity,
        count: int,
        from_time: datetime | None = None,
    ) -> list[Candle]:
        params: dict[str, str | int] = {"granularity": granularity.value, "price": "M"}
        if from_time is not None:
            params["from"] = from_time.astimezone(UTC).isoformat()
            params["count"] = count
        else:
            params["count"] = count
        try:
            async with await self._client(self._rest_base) as client:
                resp = await client.get(f"/v3/instruments/{instrument}/candles", params=params)
        except httpx.RequestError as exc:
            raise BrokerConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        data = resp.json()
        result: list[Candle] = []
        for c in data.get("candles", []):
            mid = c["mid"]
            result.append(
                Candle(
                    instrument=instrument,
                    granularity=granularity,
                    open_time=datetime.fromisoformat(c["time"].replace("Z", "+00:00")),
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=int(c.get("volume", 0)),
                    is_final=bool(c.get("complete", True)),
                )
            )
        return result

    async def get_account(self) -> AccountSummary:
        try:
            async with await self._client(self._rest_base) as client:
                resp = await client.get(f"/v3/accounts/{self._account_id}/summary")
        except httpx.RequestError as exc:
            raise BrokerConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        acc = resp.json()["account"]
        return AccountSummary(
            account_id=acc["id"],
            balance=float(acc["balance"]),
            equity=float(acc["NAV"]),
            unrealized_pnl=float(acc["unrealizedPL"]),
            margin_used=float(acc["marginUsed"]),
            margin_available=float(acc["marginAvailable"]),
            currency=acc.get("currency", "JPY"),
        )

    async def get_positions(self) -> list[BrokerPosition]:
        try:
            async with await self._client(self._rest_base) as client:
                resp = await client.get(f"/v3/accounts/{self._account_id}/openPositions")
        except httpx.RequestError as exc:
            raise BrokerConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        positions: list[BrokerPosition] = []
        for p in resp.json().get("positions", []):
            long_units = float(p["long"]["units"])
            short_units = float(p["short"]["units"])
            if long_units != 0:
                positions.append(
                    BrokerPosition(
                        instrument=p["instrument"],
                        direction="BUY",
                        size=long_units,
                        entry_price=float(p["long"]["averagePrice"]),
                        unrealized_pnl=float(p["long"]["unrealizedPL"]),
                        trade_id=p["instrument"],
                    )
                )
            if short_units != 0:
                positions.append(
                    BrokerPosition(
                        instrument=p["instrument"],
                        direction="SELL",
                        size=abs(short_units),
                        entry_price=float(p["short"]["averagePrice"]),
                        unrealized_pnl=float(p["short"]["unrealizedPL"]),
                        trade_id=p["instrument"],
                    )
                )
        return positions

    async def create_order(self, order: OrderRequest) -> OrderResult:
        units = order.size if order.direction == "BUY" else -order.size
        payload: dict = {
            "order": {
                "type": "MARKET",
                "instrument": order.instrument,
                "units": str(int(units)),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "clientExtensions": {"id": order.idempotency_key[:64]},
            }
        }
        if order.stop_loss is not None:
            payload["order"]["stopLossOnFill"] = {"price": f"{order.stop_loss:.5f}"}
        if order.take_profit is not None:
            payload["order"]["takeProfitOnFill"] = {"price": f"{order.take_profit:.5f}"}
        try:
            async with await self._client(self._rest_base) as client:
                resp = await client.post(f"/v3/accounts/{self._account_id}/orders", json=payload)
        except httpx.RequestError as exc:
            raise BrokerConnectionError(str(exc)) from exc
        if resp.status_code >= 400:
            self._raise_for_status(resp)
        data = resp.json()
        fill = data.get("orderFillTransaction")
        if fill is None:
            reject = data.get("orderRejectTransaction", {})
            return OrderResult(
                success=False,
                status="rejected",
                reject_reason=reject.get("rejectReason", json.dumps(data)),
            )
        return OrderResult(
            success=True,
            broker_order_id=fill.get("orderID"),
            trade_id=fill.get("tradeOpened", {}).get("tradeID"),
            filled_price=float(fill.get("price", 0)),
            status="filled",
        )

    async def close_position(self, instrument: str) -> OrderResult:
        payload = {"longUnits": "ALL", "shortUnits": "ALL"}
        try:
            async with await self._client(self._rest_base) as client:
                resp = await client.put(
                    f"/v3/accounts/{self._account_id}/positions/{instrument}/close", json=payload
                )
        except httpx.RequestError as exc:
            raise BrokerConnectionError(str(exc)) from exc
        if resp.status_code >= 400:
            self._raise_for_status(resp)
        data = resp.json()
        return OrderResult(success=True, status="filled", filled_price=None, broker_order_id=None)

    async def stream_prices(self, instruments: list[str]) -> AsyncIterator[PriceQuote]:
        params = {"instruments": ",".join(instruments)}
        try:
            async with await self._client(self._stream_base, timeout=None) as client:
                async with client.stream(
                    "GET", f"/v3/accounts/{self._account_id}/pricing/stream", params=params
                ) as resp:
                    if resp.status_code >= 400:
                        self._raise_for_status(resp)
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        msg = json.loads(line)
                        if msg.get("type") != "PRICE":
                            continue
                        bid = float(msg["bids"][0]["price"])
                        ask = float(msg["asks"][0]["price"])
                        yield PriceQuote(
                            instrument=msg["instrument"],
                            bid=bid,
                            ask=ask,
                            ts=datetime.fromisoformat(msg["time"].replace("Z", "+00:00")),
                        )
        except httpx.RequestError as exc:
            raise BrokerConnectionError(str(exc)) from exc
