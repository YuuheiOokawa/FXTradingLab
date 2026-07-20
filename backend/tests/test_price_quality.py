from datetime import UTC, datetime, timedelta

from app.brokers.schemas import PriceQuote
from app.services.price_quality import validate_tick


def _tick(bid: float, ask: float, ts: datetime | None = None) -> PriceQuote:
    return PriceQuote(instrument="USD_JPY", bid=bid, ask=ask, ts=ts or datetime.now(UTC))


def test_accepts_a_normal_tick():
    result = validate_tick(_tick(157.30, 157.31), None)
    assert result.valid is True


def test_rejects_non_positive_price():
    assert validate_tick(_tick(0, 157.31), None).valid is False
    assert validate_tick(_tick(157.30, -1), None).valid is False


def test_rejects_bid_greater_than_or_equal_to_ask():
    assert validate_tick(_tick(157.31, 157.30), None).valid is False
    assert validate_tick(_tick(157.30, 157.30), None).valid is False


def test_rejects_extreme_spread():
    # ~6.4% spread relative to mid — far beyond any real FX spread.
    result = validate_tick(_tick(150.0, 160.0), None)
    assert result.valid is False
    assert "spread" in result.reason


def test_rejects_timestamp_not_after_previous():
    now = datetime.now(UTC)
    previous = _tick(157.30, 157.31, now)
    same_time = _tick(157.30, 157.31, now)
    earlier = _tick(157.30, 157.31, now - timedelta(seconds=1))
    assert validate_tick(same_time, previous).valid is False
    assert validate_tick(earlier, previous).valid is False


def test_rejects_extreme_price_jump():
    now = datetime.now(UTC)
    previous = _tick(157.30, 157.31, now)
    jumped = _tick(165.0, 165.01, now + timedelta(seconds=2))  # ~4.9% jump, clearly over the 3% threshold
    result = validate_tick(jumped, previous)
    assert result.valid is False
    assert "jump" in result.reason


def test_accepts_normal_movement_after_previous_tick():
    now = datetime.now(UTC)
    previous = _tick(157.30, 157.31, now)
    small_move = _tick(157.32, 157.33, now + timedelta(seconds=2))
    assert validate_tick(small_move, previous).valid is True
