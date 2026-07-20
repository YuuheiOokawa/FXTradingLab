"""Broker adapter contract tests (docs/13_TEST_STRATEGY.md): the same expectations
run against MockAdapter directly and against OandaAdapter with its HTTP calls
mocked via respx, so both satisfy the BrokerAdapter protocol identically.
"""
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.brokers.errors import BrokerAuthError, BrokerOrderRejected
from app.brokers.mock import MockAdapter
from app.brokers.oanda import OandaAdapter
from app.brokers.schemas import Granularity, OrderRequest


@pytest.fixture
def mock_adapter():
    return MockAdapter()


@pytest.fixture
def oanda_adapter():
    return OandaAdapter(api_token="test-token", account_id="001-001-1234567-001", environment="practice")


async def test_mock_get_current_price_shape(mock_adapter):
    quote = await mock_adapter.get_current_price("USD_JPY")
    assert quote.instrument == "USD_JPY"
    assert quote.ask > quote.bid
    assert quote.mid == pytest.approx((quote.bid + quote.ask) / 2)


async def test_mock_create_and_close_order_round_trip(mock_adapter):
    order = OrderRequest(instrument="USD_JPY", direction="BUY", size=1000, stop_loss=150.0, take_profit=160.0, idempotency_key="k1")
    result = await mock_adapter.create_order(order)
    assert result.success is True
    assert result.status == "filled"

    positions = await mock_adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].instrument == "USD_JPY"

    close_result = await mock_adapter.close_position("USD_JPY")
    assert close_result.success is True
    positions_after = await mock_adapter.get_positions()
    assert len(positions_after) == 0


async def test_mock_candles_deterministic_for_same_window():
    end = datetime(2026, 1, 1, tzinfo=UTC)
    a = await MockAdapter().get_candles("USD_JPY", Granularity.H1, 100, end)
    b = await MockAdapter().get_candles("USD_JPY", Granularity.H1, 100, end)
    assert [c.close for c in a] == [c.close for c in b]


@respx.mock
async def test_oanda_get_current_price_parses_response(oanda_adapter):
    respx.get("https://api-fxpractice.oanda.com/v3/accounts/001-001-1234567-001/pricing").mock(
        return_value=httpx.Response(
            200,
            json={"prices": [{"instrument": "USD_JPY", "bids": [{"price": "157.10"}], "asks": [{"price": "157.16"}]}]},
        )
    )
    quote = await oanda_adapter.get_current_price("USD_JPY")
    assert quote.bid == 157.10
    assert quote.ask == 157.16


@respx.mock
async def test_oanda_auth_error_maps_to_broker_auth_error(oanda_adapter):
    respx.get("https://api-fxpractice.oanda.com/v3/accounts/001-001-1234567-001/pricing").mock(
        return_value=httpx.Response(401, text="unauthorized")
    )
    with pytest.raises(BrokerAuthError):
        await oanda_adapter.get_current_price("USD_JPY")


@respx.mock
async def test_oanda_create_order_success(oanda_adapter):
    respx.post("https://api-fxpractice.oanda.com/v3/accounts/001-001-1234567-001/orders").mock(
        return_value=httpx.Response(
            201,
            json={"orderFillTransaction": {"orderID": "123", "price": "157.20", "tradeOpened": {"tradeID": "456"}}},
        )
    )
    order = OrderRequest(instrument="USD_JPY", direction="BUY", size=1000, stop_loss=150.0, take_profit=160.0, idempotency_key="k2")
    result = await oanda_adapter.create_order(order)
    assert result.success is True
    assert result.broker_order_id == "123"
    assert result.trade_id == "456"
    assert result.filled_price == 157.20


@respx.mock
async def test_oanda_create_order_rejected_by_broker(oanda_adapter):
    respx.post("https://api-fxpractice.oanda.com/v3/accounts/001-001-1234567-001/orders").mock(
        return_value=httpx.Response(
            201,
            json={"orderRejectTransaction": {"rejectReason": "INSUFFICIENT_MARGIN"}},
        )
    )
    order = OrderRequest(instrument="USD_JPY", direction="BUY", size=1_000_000_000, stop_loss=150.0, take_profit=160.0, idempotency_key="k3")
    result = await oanda_adapter.create_order(order)
    assert result.success is False
    assert result.status == "rejected"
    assert "INSUFFICIENT_MARGIN" in (result.reject_reason or "")


@respx.mock
async def test_oanda_get_candles_parses_response(oanda_adapter):
    respx.get("https://api-fxpractice.oanda.com/v3/instruments/USD_JPY/candles").mock(
        return_value=httpx.Response(
            200,
            json={
                "candles": [
                    {
                        "time": "2026-01-01T00:00:00.000000000Z",
                        "mid": {"o": "157.0", "h": "157.5", "l": "156.8", "c": "157.3"},
                        "volume": 120,
                        "complete": True,
                    }
                ]
            },
        )
    )
    candles = await oanda_adapter.get_candles("USD_JPY", Granularity.H1, 1)
    assert len(candles) == 1
    assert candles[0].open == 157.0
    assert candles[0].close == 157.3
