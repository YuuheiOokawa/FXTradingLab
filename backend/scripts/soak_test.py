"""Soak test (docs/15_PRODUCTION_READINESS_REVIEW.md "Long-running / chaos
testing"): drive `MarketDataService.handle_tick()` through a large volume of
synthetic price ticks — 100,000+ by default — to catch memory leaks,
connection-pool exhaustion, and asyncio task leaks under sustained volume,
without needing real wall-clock hours to accumulate real ticks. The mock
broker's poll loop only produces ~2 ticks/sec/instrument at its default
config; 100,000 ticks that way would take ~14 hours. This script instead
calls the exact same tick-handling code path directly, as fast as the event
loop and I/O allow, which is a legitimate substitute for the goal (does the
pipeline hold up under volume?) even though it isn't real elapsed time.

Run against a disposable database — this creates real rows (MarketTick,
Candle, SystemEvent, Instrument) using synthetic instrument symbols
(SOAK_USDJPY etc. by default) and, unless --no-cleanup is passed, deletes
them again at the end. Do not point this at a database you care about
without reading the --no-cleanup warning below first.

Usage:
    cd backend && source .venv/bin/activate
    DATABASE_URL=postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab_test \
    REDIS_URL=redis://localhost:6379/1 \
    python -m scripts.soak_test --ticks 100000
"""
from __future__ import annotations

import argparse
import asyncio
import resource
import time

from sqlalchemy import delete, select

from app.brokers.mock import MockAdapter
from app.core.redis_client import get_redis
from app.db.models.journal import SystemEvent
from app.db.models.market import Candle as CandleModel
from app.db.models.market import Instrument, MarketTick
from app.db.session import AsyncSessionLocal, engine
from app.services.market_data import MarketDataService, ensure_instruments

DEFAULT_INSTRUMENTS = ["SOAK_USDJPY", "SOAK_EURJPY", "SOAK_GBPJPY", "SOAK_EURUSD"]


def _rss_mb() -> float:
    # ru_maxrss is KB on Linux, bytes on macOS — this project only targets
    # Linux deployment (Docker/Railway), so KB is the right divisor here.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


async def _cleanup(instrument_ids: dict[str, str]) -> None:
    async with AsyncSessionLocal() as session:
        ids = list(instrument_ids.values())
        await session.execute(delete(MarketTick).where(MarketTick.instrument_id.in_(ids)))
        await session.execute(delete(CandleModel).where(CandleModel.instrument_id.in_(ids)))
        await session.execute(delete(SystemEvent).where(SystemEvent.category == "price_quality"))
        await session.execute(delete(Instrument).where(Instrument.id.in_(ids)))
        await session.commit()


async def _row_counts(instrument_ids: dict[str, str]) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        ids = list(instrument_ids.values())
        ticks = (await session.execute(select(MarketTick).where(MarketTick.instrument_id.in_(ids)))).scalars().all()
        candles = (await session.execute(select(CandleModel).where(CandleModel.instrument_id.in_(ids)))).scalars().all()
        return {"market_ticks": len(ticks), "candles": len(candles)}


async def main(tick_count: int, instruments: list[str], report_every: int, cleanup: bool) -> None:
    redis = get_redis()
    broker = MockAdapter()
    service = MarketDataService(broker, redis)

    instrument_rows = await ensure_instruments(instruments)
    service._instrument_ids = {sym: str(row.id) for sym, row in instrument_rows.items()}
    await redis.set("system:broker_connected", "1", ex=999999)

    start_rss = _rss_mb()
    start_tasks = len(asyncio.all_tasks())
    start = time.monotonic()
    rejected = 0
    last_report_time = start

    print(f"Soak test: {tick_count} ticks across {len(instruments)} instruments")
    print(f"{'tick':>8} | {'ticks/s':>8} | {'rss MB':>8} | {'rss Δ':>8} | {'pool out/size':>13} | {'tasks Δ':>8} | rejected")

    for i in range(1, tick_count + 1):
        instrument = instruments[i % len(instruments)]
        tick = await broker.get_current_price(instrument)
        before = service._last_valid_tick.get(instrument)
        await service.handle_tick(tick)
        after = service._last_valid_tick.get(instrument)
        if after is before:
            rejected += 1

        if i % report_every == 0 or i == tick_count:
            now = time.monotonic()
            window_rate = report_every / max(now - last_report_time, 1e-6)
            last_report_time = now
            rss = _rss_mb()
            pool = engine.pool
            tasks = len(asyncio.all_tasks())
            print(
                f"{i:>8} | {window_rate:>8.1f} | {rss:>8.1f} | {rss - start_rss:>+8.1f} | "
                f"{pool.checkedout():>4}/{pool.size():<8} | {tasks - start_tasks:>+8} | {rejected}"
            )

    elapsed = time.monotonic() - start
    end_rss = _rss_mb()
    end_tasks = len(asyncio.all_tasks())
    counts = await _row_counts(service._instrument_ids)

    print()
    print("=== Summary ===")
    print(f"Ticks processed:    {tick_count} ({tick_count / elapsed:.1f}/s average) in {elapsed:.1f}s")
    print(f"Rejected by validate_tick: {rejected} ({rejected / tick_count:.2%})")
    print(f"RSS: {start_rss:.1f}MB -> {end_rss:.1f}MB (Δ {end_rss - start_rss:+.1f}MB)")
    print(f"Asyncio tasks: {start_tasks} -> {end_tasks} (Δ {end_tasks - start_tasks:+d})")
    print(f"DB engine pool: checked_out={engine.pool.checkedout()} size={engine.pool.size()}")
    print(f"MarketTick rows written: {counts['market_ticks']} (throttled to 1/5s/instrument — expected << tick count)")
    print(f"Candle rows written: {counts['candles']}")
    print()
    print("Interpretation: a large positive RSS delta with no plateau, a growing")
    print("asyncio task delta, or a growing pool checked_out count that never")
    print("returns to 0 between reports all indicate a leak — investigate before")
    print("treating this pass as clean. Zero rejected ticks is expected (the mock")
    print("broker's random walk stays within validate_tick's bounds by design);")
    print("a nonzero rejection rate here would itself be worth investigating.")

    if cleanup:
        await _cleanup(service._instrument_ids)
        print(f"\nCleaned up {len(service._instrument_ids)} synthetic instruments and their rows.")
    else:
        print(f"\n--no-cleanup was set: {list(service._instrument_ids.keys())} and their rows were left in place.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticks", type=int, default=100_000, help="total ticks to process (default: 100000)")
    parser.add_argument(
        "--instruments", nargs="+", default=DEFAULT_INSTRUMENTS, help="synthetic instrument symbols to cycle through"
    )
    parser.add_argument("--report-every", type=int, default=5_000, help="print a progress line every N ticks")
    parser.add_argument(
        "--no-cleanup",
        dest="cleanup",
        action="store_false",
        help="leave the synthetic instruments/rows in the database after the run (for manual inspection)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.ticks, args.instruments, args.report_every, args.cleanup))
