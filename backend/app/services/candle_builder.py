"""In-memory OHLC candle construction from a tick stream (docs/07_REALTIME_DATA_DESIGN.md).

One `CandleBuilder` per (instrument, granularity). `update()` returns the current
in-progress candle plus whether this tick closed the previous bucket, so the caller
can decide what to persist/publish without the builder knowing about DB or Redis.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.brokers.schemas import GRANULARITY_SECONDS, Candle, Granularity, PriceQuote


@dataclass
class CandleUpdateResult:
    candle: Candle
    closed_candle: Candle | None  # set only on the tick that finalizes a bucket


class CandleBuilder:
    def __init__(self, instrument: str, granularity: Granularity) -> None:
        self.instrument = instrument
        self.granularity = granularity
        self._step = GRANULARITY_SECONDS[granularity]
        self._current: Candle | None = None

    def _bucket_open_time(self, ts: datetime) -> datetime:
        epoch = int(ts.timestamp())
        bucket_epoch = (epoch // self._step) * self._step
        return datetime.fromtimestamp(bucket_epoch, tz=UTC)

    def update(self, tick: PriceQuote) -> CandleUpdateResult:
        open_time = self._bucket_open_time(tick.ts)
        price = tick.mid

        if self._current is None or self._current.open_time != open_time:
            closed = None
            if self._current is not None:
                closed = self._current.model_copy(update={"is_final": True})
            self._current = Candle(
                instrument=self.instrument,
                granularity=self.granularity,
                open_time=open_time,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1,
                is_final=False,
            )
            return CandleUpdateResult(candle=self._current, closed_candle=closed)

        self._current = self._current.model_copy(
            update={
                "high": max(self._current.high, price),
                "low": min(self._current.low, price),
                "close": price,
                "volume": self._current.volume + 1,
            }
        )
        return CandleUpdateResult(candle=self._current, closed_candle=None)
