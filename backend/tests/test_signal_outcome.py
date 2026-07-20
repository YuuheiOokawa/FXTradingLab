"""Signal outcome computation (docs/08_SIGNAL_ENGINE.md "Signal outcome
history"). Real test DB — this exercises the actual candle-window query and
pip arithmetic, not a mocked version of it."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models.market import Candle
from app.db.models.strategy import Signal
from app.services.market_data import ensure_instruments
from app.worker.jobs import signal_outcome

PIP = 0.01  # USD_JPY


async def _make_signal(db_session, instrument_id, ts, direction="BUY", entry_price=150.0) -> Signal:
    signal = Signal(
        instrument_id=instrument_id,
        granularity="M15",
        ts=ts,
        direction=direction,
        score=80,
        label="強い買い" if direction == "BUY" else "強い売り",
        regime_trend="UPTREND",
        regime_volatility="NORMAL",
        reasons=[],
        entry_price=entry_price,
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


async def _add_candle(db_session, instrument_id, open_time, o, h, low, c) -> None:
    db_session.add(
        Candle(
            instrument_id=instrument_id,
            granularity="M15",
            open_time=open_time,
            open=o,
            high=h,
            low=low,
            close=c,
        )
    )
    await db_session.commit()


async def test_skips_signals_whose_horizon_has_not_elapsed(db_session):
    instruments = await ensure_instruments(["USD_JPY"])
    now = datetime.now(UTC)
    await _make_signal(db_session, instruments["USD_JPY"].id, ts=now - timedelta(minutes=30))

    result = await signal_outcome.run()

    assert result["computed"] == 0  # < OUTCOME_HORIZON_MINUTES old, not in the query at all


async def test_skips_signals_with_incomplete_candle_coverage(db_session):
    instruments = await ensure_instruments(["USD_JPY"])
    now = datetime.now(UTC)
    signal_ts = now - timedelta(minutes=signal_outcome.OUTCOME_HORIZON_MINUTES + 30)
    await _make_signal(db_session, instruments["USD_JPY"].id, ts=signal_ts)
    # Only one candle shortly after ts — nowhere near covering the 4h horizon.
    await _add_candle(db_session, instruments["USD_JPY"].id, signal_ts + timedelta(minutes=15), 150.0, 150.1, 149.9, 150.05)

    result = await signal_outcome.run()

    assert result["pending"] == 1
    assert result["computed"] == 0
    row = (await db_session.execute(select(Signal))).scalar_one()
    assert row.outcome_computed_at is None


async def test_computes_favorable_and_adverse_pips_for_a_buy_signal(db_session):
    instruments = await ensure_instruments(["USD_JPY"])
    now = datetime.now(UTC)
    signal_ts = now - timedelta(minutes=signal_outcome.OUTCOME_HORIZON_MINUTES + 30)
    inst_id = instruments["USD_JPY"].id
    entry = 150.0
    await _make_signal(db_session, inst_id, ts=signal_ts, direction="BUY", entry_price=entry)

    # Price rises 0.50 (50 pips) favorable, dips 0.10 (10 pips) adverse, ends
    # up 0.30 (30 pips) favorable — spanning candles all the way to the
    # horizon so coverage is complete.
    horizon_end = signal_ts + timedelta(minutes=signal_outcome.OUTCOME_HORIZON_MINUTES)
    await _add_candle(db_session, inst_id, signal_ts + timedelta(minutes=15), 150.0, 150.10, 149.90, 150.05)
    await _add_candle(db_session, inst_id, signal_ts + timedelta(minutes=30), 150.05, 150.50, 150.00, 150.40)
    await _add_candle(db_session, inst_id, horizon_end, 150.40, 150.45, 150.30, 150.30)

    result = await signal_outcome.run()

    assert result["computed"] == 1
    row = (await db_session.execute(select(Signal))).scalar_one()
    assert row.outcome_computed_at is not None
    assert row.max_favorable_pips == 50.0  # (150.50 - 150.00) / 0.01
    assert row.max_adverse_pips == 10.0  # (150.00 - 149.90) / 0.01
    assert row.price_after_horizon_pips == 30.0  # (150.30 - 150.00) / 0.01
    assert row.tp_reached is False  # assumed TP is 60 pips; only reached 50
    assert row.sl_reached is False


async def test_sell_signal_direction_is_inverted_correctly(db_session):
    instruments = await ensure_instruments(["USD_JPY"])
    now = datetime.now(UTC)
    signal_ts = now - timedelta(minutes=signal_outcome.OUTCOME_HORIZON_MINUTES + 30)
    inst_id = instruments["USD_JPY"].id
    entry = 150.0
    await _make_signal(db_session, inst_id, ts=signal_ts, direction="SELL", entry_price=entry)

    horizon_end = signal_ts + timedelta(minutes=signal_outcome.OUTCOME_HORIZON_MINUTES)
    # Price falls to 149.40 (60 pips favorable for a SELL) then recovers a
    # bit; also pokes 0.05 above entry (5 pips adverse for a SELL).
    await _add_candle(db_session, inst_id, signal_ts + timedelta(minutes=15), 150.0, 150.05, 149.90, 149.95)
    await _add_candle(db_session, inst_id, signal_ts + timedelta(minutes=30), 149.95, 150.05, 149.40, 149.60)
    await _add_candle(db_session, inst_id, horizon_end, 149.60, 149.65, 149.55, 149.60)

    result = await signal_outcome.run()

    assert result["computed"] == 1
    row = (await db_session.execute(select(Signal))).scalar_one()
    assert row.max_favorable_pips == 60.0  # (150.00 - 149.40) / 0.01
    assert row.max_adverse_pips == 5.0  # (150.05 - 150.00) / 0.01
    assert row.price_after_horizon_pips == 40.0  # (150.00 - 149.60) / 0.01
    assert row.tp_reached is True  # assumed TP is 60 pips, exactly reached
    assert row.sl_reached is False
