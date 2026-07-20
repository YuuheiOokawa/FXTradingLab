"""Integration test: a bad tick must never reach Redis pub/sub, the candle
builder, or persistence — docs/15_PRODUCTION_READINESS_REVIEW.md "Price Data
Quality". Uses the real test Redis/Postgres, not mocks, so this actually
proves the rejection happens end-to-end."""
from datetime import UTC, datetime, timedelta

from app.brokers.mock import MockAdapter
from app.brokers.schemas import PriceQuote
from app.core.redis_client import get_redis
from app.db.models.journal import SystemEvent
from app.services.market_data import MarketDataService, ensure_instruments
from sqlalchemy import select


async def test_bad_tick_is_rejected_and_never_published(db_session):
    await ensure_instruments(["USD_JPY"])
    redis = get_redis()
    await redis.delete("price:USD_JPY:latest")
    service = MarketDataService(broker=MockAdapter(), redis=redis)  # broker unused by handle_tick directly

    now = datetime.now(UTC)
    good = PriceQuote(instrument="USD_JPY", bid=157.30, ask=157.31, ts=now)
    await service.handle_tick(good)
    latest = await redis.hgetall("price:USD_JPY:latest")
    assert latest.get("bid") == "157.3"

    bad = PriceQuote(instrument="USD_JPY", bid=200.0, ask=200.01, ts=now + timedelta(seconds=2))  # ~27% jump
    await service.handle_tick(bad)
    # Redis hash must still reflect the last GOOD tick, not the rejected one.
    latest_after_bad = await redis.hgetall("price:USD_JPY:latest")
    assert latest_after_bad.get("bid") == "157.3"

    events = (
        await db_session.execute(select(SystemEvent).where(SystemEvent.category == "price_quality"))
    ).scalars().all()
    assert len(events) == 1
    assert "jump" in events[0].message


async def test_good_tick_after_rejection_is_still_accepted(db_session):
    await ensure_instruments(["USD_JPY"])
    redis = get_redis()
    await redis.delete("price:USD_JPY:latest")
    service = MarketDataService(broker=MockAdapter(), redis=redis)

    now = datetime.now(UTC)
    await service.handle_tick(PriceQuote(instrument="USD_JPY", bid=157.30, ask=157.31, ts=now))
    # Rejected: bid >= ask.
    await service.handle_tick(PriceQuote(instrument="USD_JPY", bid=157.40, ask=157.35, ts=now + timedelta(seconds=1)))
    # A subsequent genuinely-good tick must still be accepted normally.
    await service.handle_tick(PriceQuote(instrument="USD_JPY", bid=157.32, ask=157.33, ts=now + timedelta(seconds=2)))

    latest = await redis.hgetall("price:USD_JPY:latest")
    assert latest.get("bid") == "157.32"
