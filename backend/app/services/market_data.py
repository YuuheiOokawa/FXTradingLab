"""Continuous market monitoring: broker stream -> candle builders -> Redis pub/sub
+ Postgres persistence. Runs inside the worker process (app/worker/main.py), never
inside a request handler — see docs/02_SYSTEM_ARCHITECTURE.md.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

import orjson
from redis.asyncio import Redis

from app.brokers.base import BrokerAdapter
from app.brokers.errors import BrokerConnectionError
from app.brokers.schemas import GRANULARITY_SECONDS, Candle, Granularity, PriceQuote
from app.core.config import get_settings
from app.db.models.market import Candle as CandleModel
from app.db.models.market import Instrument, MarketTick
from app.db.models.journal import SystemEvent
from app.db.session import AsyncSessionLocal
from app.services.candle_builder import CandleBuilder
from app.services.price_quality import validate_tick

logger = logging.getLogger(__name__)

ALL_GRANULARITIES = [Granularity.M1, Granularity.M5, Granularity.M15, Granularity.H1, Granularity.H4, Granularity.D]

DEFAULT_INSTRUMENT_META: dict[str, dict] = {
    "USD_JPY": {"display_name": "米ドル/円", "pip_size": 0.01, "price_precision": 3},
    "EUR_JPY": {"display_name": "ユーロ/円", "pip_size": 0.01, "price_precision": 3},
    "GBP_JPY": {"display_name": "英ポンド/円", "pip_size": 0.01, "price_precision": 3},
    "EUR_USD": {"display_name": "ユーロ/米ドル", "pip_size": 0.0001, "price_precision": 5},
    "GBP_USD": {"display_name": "英ポンド/米ドル", "pip_size": 0.0001, "price_precision": 5},
    "AUD_JPY": {"display_name": "豪ドル/円", "pip_size": 0.01, "price_precision": 3},
}


async def ensure_instruments(symbols: list[str]) -> dict[str, Instrument]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        existing = {i.symbol: i for i in result.scalars().all()}
        missing = [s for s in symbols if s not in existing]
        for symbol in missing:
            meta = DEFAULT_INSTRUMENT_META.get(symbol, {"display_name": symbol, "pip_size": 0.01, "price_precision": 3})
            instrument = Instrument(symbol=symbol, is_watched=True, **meta)
            session.add(instrument)
            existing[symbol] = instrument
        if missing:
            await session.commit()
            for symbol in missing:
                await session.refresh(existing[symbol])
        return existing


class MarketDataService:
    """Owns one CandleBuilder per (instrument, granularity), consumes the broker's
    price stream, and fans updates out to Redis + Postgres."""

    def __init__(self, broker: BrokerAdapter, redis: Redis) -> None:
        self._broker = broker
        self._redis = redis
        self._settings = get_settings()
        self._builders: dict[tuple[str, Granularity], CandleBuilder] = {}
        self._last_tick_persist: dict[str, datetime] = {}
        self._instrument_ids: dict[str, str] = {}
        self._last_valid_tick: dict[str, PriceQuote] = {}

    def _builder(self, instrument: str, granularity: Granularity) -> CandleBuilder:
        key = (instrument, granularity)
        if key not in self._builders:
            self._builders[key] = CandleBuilder(instrument, granularity)
        return self._builders[key]

    async def _publish_tick(self, tick: PriceQuote) -> None:
        payload = {
            "type": "tick",
            "instrument": tick.instrument,
            "bid": tick.bid,
            "ask": tick.ask,
            "mid": tick.mid,
            "spread": tick.spread,
            "ts": tick.ts.isoformat(),
        }
        await self._redis.publish(f"ticks:{tick.instrument}", orjson.dumps(payload))
        key = f"price:{tick.instrument}:latest"
        await self._redis.hset(key, mapping={k: str(v) for k, v in payload.items()})
        # TTL so this hash can't outlive a dead worker indefinitely — without
        # this, /metrics (and anything else reading it) would keep showing a
        # "fresh-looking" last-tick timestamp from before the worker died,
        # which defeats the point of a staleness check
        # (docs/15_PRODUCTION_READINESS_REVIEW.md "Observability").
        await self._redis.expire(key, self._settings.price_stale_seconds * 3)
        await self._redis.set(f"price:{tick.instrument}:stale", "0", ex=self._settings.price_stale_seconds * 3)

    async def _publish_candle(self, candle: Candle, event: str) -> None:
        payload = {
            "type": event,
            "instrument": candle.instrument,
            "granularity": candle.granularity.value,
            "candle": candle.model_dump(mode="json"),
        }
        await self._redis.publish(
            f"candles:{candle.instrument}:{candle.granularity.value}", orjson.dumps(payload)
        )

    async def _maybe_persist_tick(self, tick: PriceQuote) -> None:
        last = self._last_tick_persist.get(tick.instrument)
        if last is not None and (tick.ts - last).total_seconds() < 5:
            return
        self._last_tick_persist[tick.instrument] = tick.ts
        instrument_id = self._instrument_ids.get(tick.instrument)
        if instrument_id is None:
            return
        async with AsyncSessionLocal() as session:
            session.add(MarketTick(instrument_id=instrument_id, ts=tick.ts, bid=tick.bid, ask=tick.ask))
            await session.commit()

    async def _persist_candle(self, candle: Candle) -> None:
        instrument_id = self._instrument_ids.get(candle.instrument)
        if instrument_id is None:
            return
        async with AsyncSessionLocal() as session:
            existing = await session.execute(
                select(CandleModel).where(
                    CandleModel.instrument_id == instrument_id,
                    CandleModel.granularity == candle.granularity.value,
                    CandleModel.open_time == candle.open_time,
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                session.add(
                    CandleModel(
                        instrument_id=instrument_id,
                        granularity=candle.granularity.value,
                        open_time=candle.open_time,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        is_final=True,
                    )
                )
            else:
                row.open, row.high, row.low, row.close, row.volume, row.is_final = (
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    True,
                )
            await session.commit()

    async def _log_event(self, category: str, severity: str, message: str, context: dict | None = None) -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                SystemEvent(
                    ts=datetime.now(UTC), category=category, severity=severity, message=message, context=context or {}
                )
            )
            await session.commit()

    async def handle_tick(self, tick: PriceQuote) -> None:
        previous = self._last_valid_tick.get(tick.instrument)
        result = validate_tick(tick, previous)
        if not result.valid:
            logger.warning("rejected bad tick for %s: %s", tick.instrument, result.reason)
            await self._log_event(
                "price_quality",
                "warning",
                f"rejected tick for {tick.instrument}: {result.reason}",
                {"instrument": tick.instrument, "bid": tick.bid, "ask": tick.ask, "ts": tick.ts.isoformat()},
            )
            return
        self._last_valid_tick[tick.instrument] = tick

        await self._publish_tick(tick)
        await self._maybe_persist_tick(tick)
        for granularity in ALL_GRANULARITIES:
            result = self._builder(tick.instrument, granularity).update(tick)
            if result.closed_candle is not None:
                await self._persist_candle(result.closed_candle)
                await self._publish_candle(result.closed_candle, "candle_close")
            await self._publish_candle(result.candle, "candle_update")

    async def run(self, instruments: list[str]) -> None:
        instrument_rows = await ensure_instruments(instruments)
        self._instrument_ids = {sym: str(row.id) for sym, row in instrument_rows.items()}
        await self._redis.set("system:broker_connected", "1", ex=self._settings.price_stale_seconds * 3)
        backoff = 2.0
        while True:
            try:
                async for tick in self._broker.stream_prices(instruments):
                    backoff = 2.0
                    await self._redis.set("system:broker_connected", "1", ex=self._settings.price_stale_seconds * 3)
                    await self.handle_tick(tick)
            except BrokerConnectionError as exc:
                await self._redis.set("system:broker_connected", "0")
                await self._log_event("broker", "error", f"price stream disconnected: {exc}")
                logger.warning("broker stream error, retrying in %.0fs: %s", backoff, exc)
                import asyncio

                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
