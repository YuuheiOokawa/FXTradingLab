"""POST /api/v1/backtests/walk-forward wiring — the algorithm itself is
covered by tests/test_walk_forward.py; this checks the route (request
validation, grid-size cap, response shape) against the real ASGI app."""
import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_runs_end_to_end_against_the_mock_broker(client):
    resp = await client.post(
        "/api/v1/backtests/walk-forward",
        json={
            "pair": "USD_JPY",
            "timeframe": "M15",
            "candle_count": 900,
            "train_bars": 300,
            "test_bars": 100,
            "param_grid": {
                "stop_loss_pips": [20.0, 30.0],
                "take_profit_pips": [40.0, 60.0],
                "min_score_threshold": [60],
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["windows"]) >= 1
    assert "combined_test_metrics" in body
    assert "parameter_stability" in body
    assert "disclaimer" in body
    # The response must never look like a "here's your production config" field.
    assert "recommended_params" not in body
    assert "best_params" not in body


async def test_rejects_a_grid_over_the_candidate_cap(client):
    resp = await client.post(
        "/api/v1/backtests/walk-forward",
        json={
            "pair": "USD_JPY",
            "timeframe": "M15",
            "candle_count": 900,
            "train_bars": 300,
            "test_bars": 100,
            "param_grid": {
                "stop_loss_pips": [10.0, 20.0, 30.0, 40.0, 50.0],
                "take_profit_pips": [20.0, 30.0, 40.0, 50.0, 60.0],
                "min_score_threshold": [50, 55, 60, 65, 70],
            },
        },
    )
    assert resp.status_code == 400


async def test_rejects_too_few_candles(client):
    resp = await client.post(
        "/api/v1/backtests/walk-forward",
        json={"pair": "USD_JPY", "timeframe": "M15", "candle_count": 100},
    )
    assert resp.status_code == 422  # below the candle_count ge=700 floor
