"""Signal snapshot capture (docs/08_SIGNAL_ENGINE.md "Signal outcome
history"). Uses the real test DB, not mocks — dedup is enforced by a real
unique constraint, which a mock could hide a bug behind."""
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.strategy import Signal
from app.services.market_data import ensure_instruments
from app.services.regime import RegimeResult
from app.services.signal_engine import Reason, SignalResult
from app.worker.jobs import signal_capture


@pytest.fixture(autouse=True)
def _single_instrument_watchlist(monkeypatch):
    """The default watchlist has 4 instruments; these tests only care about
    one, so pin it down rather than asserting against len(settings.watchlist)
    everywhere."""
    settings = get_settings()
    monkeypatch.setattr(settings, "default_watchlist", "USD_JPY")
    yield
    monkeypatch.setattr(settings, "default_watchlist", "USD_JPY,EUR_JPY,GBP_JPY,EUR_USD")


def _strong_buy_signal() -> SignalResult:
    return SignalResult(
        direction="BUY",
        score=80,
        label="強い買い",
        regime=RegimeResult(trend="UPTREND", volatility="NORMAL", adx_value=30.0, atr_value=0.1, atr_avg=0.1),
        reasons=[Reason(status="met", text="EMA aligned", points=20)],
        buy_score=80,
        sell_score=0,
    )


def _weak_signal() -> SignalResult:
    return SignalResult(
        direction="BUY",
        score=20,
        label="様子見",
        regime=RegimeResult(trend="RANGE", volatility="NORMAL", adx_value=10.0, atr_value=0.1, atr_avg=0.1),
        reasons=[],
        buy_score=20,
        sell_score=10,
    )


async def test_captures_a_row_when_score_crosses_the_threshold(db_session, monkeypatch):
    await ensure_instruments(["USD_JPY"])
    monkeypatch.setattr(signal_capture, "evaluate", lambda *a, **k: _strong_buy_signal())

    result = await signal_capture.run()

    assert result["captured"] == 1
    rows = (await db_session.execute(select(Signal))).scalars().all()
    assert len(rows) == 1
    assert rows[0].direction == "BUY"
    assert rows[0].score == 80
    assert rows[0].entry_price > 0


async def test_does_not_capture_below_threshold(db_session, monkeypatch):
    await ensure_instruments(["USD_JPY"])
    monkeypatch.setattr(signal_capture, "evaluate", lambda *a, **k: _weak_signal())

    result = await signal_capture.run()

    assert result["captured"] == 0
    rows = (await db_session.execute(select(Signal))).scalars().all()
    assert rows == []


async def test_running_twice_against_the_same_candle_does_not_duplicate(db_session, monkeypatch):
    await ensure_instruments(["USD_JPY"])
    monkeypatch.setattr(signal_capture, "evaluate", lambda *a, **k: _strong_buy_signal())

    # get_candles is called fresh each run() but MockAdapter's generator is
    # deterministic for a fixed "now" bucket, so both runs see the same last
    # M15 candle open_time -> same dedup key.
    await signal_capture.run()
    result2 = await signal_capture.run()

    assert result2["captured"] == 0
    rows = (await db_session.execute(select(Signal))).scalars().all()
    assert len(rows) == 1
