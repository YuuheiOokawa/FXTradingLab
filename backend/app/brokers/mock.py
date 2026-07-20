"""Deterministic-but-realistic simulated broker.

Used automatically whenever no real broker credentials are configured (see
app/brokers/factory.py), so the entire app — dashboard, charts, signals, backtest,
paper trading, replay — works out of the box with zero external accounts.

Price generation is a seeded random walk per instrument so that repeated calls for
the same historical window return the same candles (important for reproducible
backtests), while `get_current_price`/`stream_prices` continue the walk forward in
real time from an in-process cursor.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import numpy as np

from app.brokers.base import BrokerAdapter
from app.brokers.schemas import (
    GRANULARITY_SECONDS,
    AccountSummary,
    BrokerPosition,
    Candle,
    Granularity,
    OrderRequest,
    OrderResult,
    PriceQuote,
)

BASE_PRICES: dict[str, float] = {
    "USD_JPY": 157.30,
    "EUR_JPY": 168.90,
    "GBP_JPY": 197.40,
    "EUR_USD": 1.0735,
    "GBP_USD": 1.2560,
    "AUD_JPY": 103.20,
}

# Typical spread per instrument, in price units (not pips) — rough retail-broker realism.
TYPICAL_SPREAD: dict[str, float] = {
    "USD_JPY": 0.006,
    "EUR_JPY": 0.012,
    "GBP_JPY": 0.020,
    "EUR_USD": 0.00008,
    "GBP_USD": 0.00010,
    "AUD_JPY": 0.015,
}

ANNUALIZED_VOL: dict[str, float] = {
    # rough daily volatility as a fraction of price, used to scale the random walk
    "USD_JPY": 0.006,
    "EUR_JPY": 0.006,
    "GBP_JPY": 0.007,
    "EUR_USD": 0.005,
    "GBP_USD": 0.006,
    "AUD_JPY": 0.007,
}


def _seed_for(instrument: str, granularity: str, bucket_index: int) -> int:
    key = f"{instrument}:{granularity}:{bucket_index}".encode()
    return int(hashlib.sha256(key).hexdigest()[:8], 16)


def _base_price(instrument: str) -> float:
    return BASE_PRICES.get(instrument, 100.0)


def _vol(instrument: str) -> float:
    return ANNUALIZED_VOL.get(instrument, 0.006)


def generate_candles(
    instrument: str,
    granularity: Granularity,
    count: int,
    end_time: datetime,
) -> list[Candle]:
    """Deterministic seeded random-walk OHLC generator.

    Each bar's seed is derived from (instrument, granularity, absolute bucket index
    since epoch), so calling this twice for the same window always returns identical
    candles — required for reproducible backtests — while different windows/pairs
    diverge naturally.
    """
    step_seconds = GRANULARITY_SECONDS[granularity]
    end_bucket = int(end_time.timestamp() // step_seconds)
    base = _base_price(instrument)
    vol = _vol(instrument)
    bars_per_day = 86400 / step_seconds
    per_bar_sigma = base * vol / max(bars_per_day, 1) ** 0.5
    # Mean-reversion strength: pulls the walk back toward `base` so a long history
    # window never drifts to an implausible level for the pair (e.g. USD/JPY
    # wandering to 250) while still producing realistic-looking local trends.
    reversion = 0.01

    start_bucket = end_bucket - count + 1
    # Warm up from a fixed number of buckets *before* start_bucket (not a fixed
    # offset from end_bucket) so results stay correct for any `count`, including
    # counts larger than the warmup window. The mean-reversion pull decays the
    # influence of the exact anchor point geometrically (~0.99^WARMUP), so a fixed
    # warmup keeps the overlapping portion of the series stable across different
    # `count` values for the same end_time, without the per-call generation cost
    # scaling with an unrelated fixed constant.
    WARMUP = 1000
    anchor_bucket = start_bucket - WARMUP

    candles: list[Candle] = []
    cursor = base
    for bucket in range(anchor_bucket, end_bucket + 1):
        rng = np.random.default_rng(_seed_for(instrument, granularity.value, bucket))
        pull = reversion * (base - cursor)
        drift = pull + rng.normal(0, per_bar_sigma)
        intrabar_range = abs(rng.normal(0, per_bar_sigma * 1.4)) + per_bar_sigma * 0.2
        open_ = cursor
        close = max(open_ + drift, 0.0001)
        high = max(open_, close) + abs(rng.normal(0, intrabar_range * 0.4))
        low = min(open_, close) - abs(rng.normal(0, intrabar_range * 0.4))
        low = max(low, 0.0001)
        volume = int(abs(rng.normal(500, 150)))
        open_time = datetime.fromtimestamp(bucket * step_seconds, tz=UTC)
        if bucket >= start_bucket:
            candles.append(
                Candle(
                    instrument=instrument,
                    granularity=granularity,
                    open_time=open_time,
                    open=round(open_, 6),
                    high=round(high, 6),
                    low=round(low, 6),
                    close=round(close, 6),
                    volume=volume,
                    is_final=True,
                )
            )
        cursor = close
    return candles


class MockAdapter(BrokerAdapter):
    provider = "mock"

    def __init__(self, poll_interval_ms: int = 2000) -> None:
        self._poll_interval_ms = poll_interval_ms
        self._positions: dict[str, BrokerPosition] = {}
        self._balance = 1_000_000.0
        self._account_id = "MOCK-000-000"
        # Lightweight running cursor for live ticks, seeded once per instrument from
        # the deterministic historical series (see generate_candles' docstring) and
        # then advanced with a cheap, non-seeded mean-reverting step. This is
        # deliberately *not* the same code path as get_candles(): recomputing the
        # full seeded walk on every tick (as an earlier version of this file did)
        # is O(thousands of RNG draws) per call and pegs the event loop when polled
        # every couple hundred milliseconds.
        self._live_price: dict[str, float] = {}
        self._rng = np.random.default_rng()

    def _live_mid(self, instrument: str) -> float:
        if instrument not in self._live_price:
            seed_candles = generate_candles(instrument, Granularity.M1, 1, datetime.now(UTC))
            self._live_price[instrument] = seed_candles[-1].close if seed_candles else _base_price(instrument)
        base = _base_price(instrument)
        vol = _vol(instrument)
        sigma = base * vol / 240**0.5  # ~ per-poll-tick sigma assuming a few hundred ticks/day
        reversion = 0.02
        cursor = self._live_price[instrument]
        cursor += reversion * (base - cursor) + self._rng.normal(0, sigma)
        self._live_price[instrument] = max(cursor, 0.0001)
        return self._live_price[instrument]

    async def get_current_price(self, instrument: str) -> PriceQuote:
        now = datetime.now(UTC)
        mid = self._live_mid(instrument)
        spread = TYPICAL_SPREAD.get(instrument, mid * 0.0001)
        return PriceQuote(
            instrument=instrument,
            bid=round(mid - spread / 2, 6),
            ask=round(mid + spread / 2, 6),
            ts=now,
        )

    async def get_candles(
        self,
        instrument: str,
        granularity: Granularity,
        count: int,
        from_time: datetime | None = None,
    ) -> list[Candle]:
        end_time = from_time or datetime.now(UTC)
        return generate_candles(instrument, granularity, count, end_time)

    async def get_account(self) -> AccountSummary:
        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        return AccountSummary(
            account_id=self._account_id,
            balance=self._balance,
            equity=self._balance + unrealized,
            unrealized_pnl=unrealized,
            margin_used=sum(abs(p.size) * p.entry_price * 0.04 for p in self._positions.values()),
            margin_available=self._balance,
            currency="JPY",
        )

    async def get_positions(self) -> list[BrokerPosition]:
        for instrument, pos in self._positions.items():
            quote = await self.get_current_price(instrument)
            price = quote.bid if pos.direction == "BUY" else quote.ask
            pnl_per_unit = (price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - price)
            self._positions[instrument] = pos.model_copy(update={"unrealized_pnl": pnl_per_unit * pos.size})
        return list(self._positions.values())

    async def create_order(self, order: OrderRequest) -> OrderResult:
        if order.order_type != "market":
            from app.brokers.errors import BrokerOrderRejected

            raise BrokerOrderRejected(f"MockAdapter only supports market orders; got order_type={order.order_type!r}")
        quote = await self.get_current_price(order.instrument)
        fill_price = quote.ask if order.direction == "BUY" else quote.bid
        trade_id = str(uuid.uuid4())
        self._positions[order.instrument] = BrokerPosition(
            instrument=order.instrument,
            direction=order.direction,
            size=order.size,
            entry_price=fill_price,
            unrealized_pnl=0.0,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            trade_id=trade_id,
        )
        return OrderResult(
            success=True,
            broker_order_id=str(uuid.uuid4()),
            trade_id=trade_id,
            filled_price=fill_price,
            status="filled",
        )

    async def close_position(self, instrument: str) -> OrderResult:
        pos = self._positions.pop(instrument, None)
        if pos is None:
            return OrderResult(success=False, status="rejected", reject_reason="NO_OPEN_POSITION")
        quote = await self.get_current_price(instrument)
        price = quote.bid if pos.direction == "BUY" else quote.ask
        pnl_per_unit = (price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - price)
        self._balance += pnl_per_unit * pos.size
        return OrderResult(
            success=True,
            broker_order_id=str(uuid.uuid4()),
            trade_id=pos.trade_id,
            filled_price=price,
            status="filled",
        )

    async def stream_prices(self, instruments: list[str]) -> AsyncIterator[PriceQuote]:
        while True:
            for instrument in instruments:
                yield await self.get_current_price(instrument)
            await asyncio.sleep(self._poll_interval_ms / 1000)
