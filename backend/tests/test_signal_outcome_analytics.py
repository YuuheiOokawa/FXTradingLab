"""GET /api/v1/analytics/signal-outcomes (docs/08_SIGNAL_ENGINE.md "Signal
outcome history")."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.db.models.strategy import Signal
from app.main import app
from app.services.market_data import ensure_instruments


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _add_signal(db_session, instrument_id, score, ts, **outcome):
    signal = Signal(
        instrument_id=instrument_id,
        granularity="M15",
        ts=ts,
        direction="BUY",
        score=score,
        label="強い買い",
        regime_trend="UPTREND",
        regime_volatility="NORMAL",
        reasons=[],
        entry_price=150.0,
        **outcome,
    )
    db_session.add(signal)
    await db_session.commit()


async def test_buckets_by_score_and_reports_pending_separately(client, db_session):
    instruments = await ensure_instruments(["USD_JPY"])
    inst_id = instruments["USD_JPY"].id
    now = datetime.now(UTC)

    # 80+ bucket: one with a computed favorable outcome, one still pending.
    await _add_signal(
        db_session, inst_id, score=85, ts=now,
        outcome_computed_at=now, max_favorable_pips=40.0, max_adverse_pips=10.0,
        price_after_horizon_pips=30.0, tp_reached=False, sl_reached=False,
    )
    await _add_signal(db_session, inst_id, score=90, ts=now + timedelta(minutes=15))  # pending — no outcome fields set

    # 60-69 bucket: one with a losing (adverse > favorable) outcome.
    await _add_signal(
        db_session, inst_id, score=62, ts=now + timedelta(minutes=30),
        outcome_computed_at=now, max_favorable_pips=5.0, max_adverse_pips=25.0,
        price_after_horizon_pips=-20.0, tp_reached=False, sl_reached=True,
    )

    resp = await client.get("/api/v1/analytics/signal-outcomes")
    assert resp.status_code == 200
    breakdown = {b["score_bucket"]: b for b in resp.json()["breakdown"]}

    high = breakdown["80+"]
    assert high["signal_count"] == 2
    assert high["pending_outcome_count"] == 1
    assert high["outcome_count"] == 1
    assert high["favorable_move_win_rate_pct"] == 100.0
    assert high["avg_max_favorable_pips"] == 40.0

    mid = breakdown["60-69"]
    assert mid["outcome_count"] == 1
    assert mid["favorable_move_win_rate_pct"] == 0.0
    assert mid["sl_reached_rate_pct"] == 100.0

    empty = breakdown["70-79"]
    assert empty["signal_count"] == 0
    assert empty["favorable_move_win_rate_pct"] is None


async def test_filters_by_pair(client, db_session):
    instruments = await ensure_instruments(["USD_JPY", "EUR_JPY"])
    now = datetime.now(UTC)
    await _add_signal(db_session, instruments["USD_JPY"].id, score=85, ts=now)
    await _add_signal(db_session, instruments["EUR_JPY"].id, score=85, ts=now)

    resp = await client.get("/api/v1/analytics/signal-outcomes", params={"pair": "USD_JPY"})
    assert resp.status_code == 200
    breakdown = {b["score_bucket"]: b for b in resp.json()["breakdown"]}
    assert breakdown["80+"]["signal_count"] == 1
