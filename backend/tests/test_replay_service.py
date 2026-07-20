"""Persisted Replay sessions (docs/01_REQUIREMENTS.md FR-9,
docs/15_PRODUCTION_READINESS_REVIEW.md "Replay"). Real Postgres, not mocks —
this is specifically about proving DB persistence (a session survives being
looked up through a fresh query, the way a server restart would require),
not about re-testing the judgment logic itself (see test_replay_judgment.py)."""
from datetime import UTC, datetime

from app.brokers.mock import generate_candles
from app.brokers.schemas import Granularity
from app.services import replay
from app.services.market_data import ensure_instruments

INSTRUMENT = "USD_JPY"


async def _make_candles(count=300):
    return generate_candles(INSTRUMENT, Granularity.M15, count, datetime.now(UTC))


async def test_session_and_trades_are_actually_persisted_to_the_db(db_session):
    instruments = await ensure_instruments([INSTRUMENT])
    candles = await _make_candles()

    session = await replay.create_session(db_session, instruments[INSTRUMENT].id, "M15", candles, training_mode=False)
    await replay.decide(db_session, session, "BUY")

    # Fetch through a brand new query - not the same in-memory object - to
    # prove this round-trips through the DB rather than an app-level cache
    # (the bug in the original in-memory implementation).
    reloaded = await replay.get_session(db_session, session.id)
    assert reloaded is not None
    assert reloaded.id == session.id
    assert len(reloaded.trades) == 1
    assert reloaded.trades[0].action == "BUY"
    assert reloaded.trades[0].judgment in ("good", "neutral", "risky")


async def test_visible_candles_never_exceeds_current_index_no_future_leak(db_session):
    instruments = await ensure_instruments([INSTRUMENT])
    candles = await _make_candles(300)

    session = await replay.create_session(db_session, instruments[INSTRUMENT].id, "M15", candles, training_mode=False)
    visible = replay.visible_candles(session)
    assert len(visible) == session.current_index + 1
    assert visible[-1].open_time == candles[session.current_index].open_time
    # The raw stored snapshot has the full series - visible_candles() must
    # never return more than current_index+1, which is the sole enforcement
    # point for "no future candle reaches the frontend".
    assert len(session.candles) == 300
    assert len(visible) < 300

    for _ in range(5):
        await replay.step(db_session, session)
    visible_after = replay.visible_candles(session)
    assert len(visible_after) == session.current_index + 1
    assert visible_after[-1].open_time == candles[session.current_index].open_time


async def test_step_past_the_end_returns_none_and_marks_finished(db_session):
    instruments = await ensure_instruments([INSTRUMENT])
    candles = await _make_candles(15)  # small series, warmup clamps current_index near the end

    session = await replay.create_session(db_session, instruments[INSTRUMENT].id, "M15", candles, training_mode=False)
    while not replay.is_at_end(session):
        await replay.step(db_session, session)

    result = await replay.step(db_session, session)
    assert result is None
    reloaded = await replay.get_session(db_session, session.id)
    assert reloaded.status == "finished"


async def test_decide_then_close_computes_pnl_and_updates_balance(db_session):
    instruments = await ensure_instruments([INSTRUMENT])
    candles = await _make_candles(300)
    session = await replay.create_session(
        db_session, instruments[INSTRUMENT].id, "M15", candles, training_mode=False, initial_balance=500_000.0
    )

    trade = await replay.decide(db_session, session, "BUY")
    assert trade.entry_price is not None
    assert trade.exit_price is None

    await replay.step(db_session, session)
    closed = await replay.close_open_decision(db_session, session)
    assert closed.exit_price is not None
    assert closed.pnl is not None

    reloaded = await replay.get_session(db_session, session.id)
    assert reloaded.current_balance == 500_000.0 + closed.pnl


async def test_skip_never_opens_a_position(db_session):
    instruments = await ensure_instruments([INSTRUMENT])
    candles = await _make_candles(300)
    session = await replay.create_session(db_session, instruments[INSTRUMENT].id, "M15", candles, training_mode=False)

    trade = await replay.decide(db_session, session, "SKIP")
    assert trade.entry_price is None
    assert trade.action == "SKIP"
    assert replay._open_trade(session) is None

    # Closing with nothing open must be a clean no-op, not an error.
    result = await replay.close_open_decision(db_session, session)
    assert result is None


async def test_candle_snapshot_is_frozen_at_creation_time(db_session):
    """The stored `candles` JSON must be exactly what was passed in at
    creation - the whole no-future-leak guarantee rests on this never being
    re-fetched from a live/mock feed later."""
    instruments = await ensure_instruments([INSTRUMENT])
    candles = await _make_candles(300)
    session = await replay.create_session(db_session, instruments[INSTRUMENT].id, "M15", candles, training_mode=False)

    reloaded = await replay.get_session(db_session, session.id)
    stored = replay._rehydrate_candles(reloaded.candles)
    assert len(stored) == len(candles)
    assert stored[0].open_time == candles[0].open_time
    assert stored[-1].close == candles[-1].close
