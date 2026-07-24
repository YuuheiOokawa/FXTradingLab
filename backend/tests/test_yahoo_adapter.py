"""Yahoo market-data adapter tests.

Two things carry real weight here:

* **It must refuse to trade.** Yahoo is not a broker. If `get_account` returned
  a plausible balance or `create_order` returned a fake fill, an order path
  could appear to succeed against nothing at all.
* **The forming-bar flag must be right.** `auto_trader._drop_forming_candle`
  trusts `is_final` to avoid reading a price that can still move. Mislabel it
  and every backtest-validated rule starts trading on look-ahead data.

HTTP is mocked with respx (same approach as the OANDA adapter tests), so these
run offline and deterministically.
"""
import httpx
import pytest
import respx

from app.brokers.errors import BrokerConnectionError
from app.brokers.factory import MARKET_DATA_ONLY_PROVIDERS, get_trading_broker, reset_broker_adapter
from app.brokers.schemas import Granularity, OrderRequest
from app.brokers.yahoo import SYMBOL_MAP, YahooMarketDataAdapter, pip_size

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


@pytest.fixture
def adapter():
    return YahooMarketDataAdapter()


def _chart(timestamps, closes, *, meta_price=150.0, meta_time=1_700_000_000):
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {"regularMarketPrice": meta_price, "regularMarketTime": meta_time},
                    "timestamp": list(timestamps),
                    "indicators": {
                        "quote": [
                            {
                                "open": [c - 0.1 for c in closes],
                                "high": [c + 0.2 for c in closes],
                                "low": [c - 0.2 for c in closes],
                                "close": list(closes),
                            }
                        ]
                    },
                }
            ],
        }
    }


class TestNotABroker:
    """The whole point of this adapter is prices without an account."""

    async def test_get_account_refuses(self, adapter):
        with pytest.raises(BrokerConnectionError, match="market-data only"):
            await adapter.get_account()

    async def test_get_positions_refuses(self, adapter):
        with pytest.raises(BrokerConnectionError, match="market-data only"):
            await adapter.get_positions()

    async def test_create_order_refuses(self, adapter):
        order = OrderRequest(instrument="USD_JPY", direction="BUY", size=1000, idempotency_key="k")
        with pytest.raises(BrokerConnectionError, match="market-data only"):
            await adapter.create_order(order)

    async def test_close_position_refuses(self, adapter):
        with pytest.raises(BrokerConnectionError, match="market-data only"):
            await adapter.close_position("USD_JPY")

    def test_configuring_it_as_the_trading_broker_fails_loudly(self, monkeypatch):
        """Caught at startup rather than at the moment an order is attempted."""
        from app.core.config import get_settings

        reset_broker_adapter()
        get_settings.cache_clear()
        monkeypatch.setenv("BROKER_PROVIDER", "yahoo")
        try:
            with pytest.raises(ValueError, match="cannot execute orders"):
                get_trading_broker()
        finally:
            reset_broker_adapter()
            get_settings.cache_clear()

    def test_it_is_registered_as_market_data_only(self):
        assert "yahoo" in MARKET_DATA_ONLY_PROVIDERS


class TestFormingCandle:
    @respx.mock
    async def test_only_the_last_bar_is_marked_forming(self, adapter):
        respx.get(f"{BASE}/USDJPY=X").mock(
            return_value=httpx.Response(200, json=_chart([1, 86401, 172801], [150.0, 151.0, 152.0]))
        )
        candles = await adapter.get_candles("USD_JPY", Granularity.D, 10)
        assert [c.is_final for c in candles] == [True, True, False]

    @respx.mock
    async def test_null_rows_are_dropped_not_zero_filled(self, adapter):
        """Yahoo emits nulls for holidays; a 0.0 bar would look like a crash to
        every indicator downstream."""
        payload = _chart([1, 86401, 172801], [150.0, 151.0, 152.0])
        q = payload["chart"]["result"][0]["indicators"]["quote"][0]
        q["close"][1] = None
        q["high"][1] = None
        respx.get(f"{BASE}/USDJPY=X").mock(return_value=httpx.Response(200, json=payload))
        candles = await adapter.get_candles("USD_JPY", Granularity.D, 10)
        assert len(candles) == 2
        assert all(c.close > 0 for c in candles)

    @respx.mock
    async def test_count_returns_the_most_recent_bars(self, adapter):
        respx.get(f"{BASE}/USDJPY=X").mock(
            return_value=httpx.Response(200, json=_chart(list(range(0, 86400 * 5, 86400)), [1.0, 2.0, 3.0, 4.0, 5.0]))
        )
        candles = await adapter.get_candles("USD_JPY", Granularity.D, 2)
        assert [c.close for c in candles] == [4.0, 5.0]


class TestPricing:
    @respx.mock
    async def test_synthesises_a_two_sided_quote(self, adapter):
        respx.get(f"{BASE}/USDJPY=X").mock(
            return_value=httpx.Response(200, json=_chart([1], [150.0], meta_price=150.0))
        )
        q = await adapter.get_current_price("USD_JPY")
        assert q.bid < 150.0 < q.ask
        assert q.spread == pytest.approx(1.5 * pip_size("USD_JPY"), abs=1e-6)

    @respx.mock
    async def test_uses_the_exchange_timestamp_not_local_time(self, adapter):
        """Staleness checks are meaningless if this reflects when we asked."""
        respx.get(f"{BASE}/USDJPY=X").mock(
            return_value=httpx.Response(200, json=_chart([1], [150.0], meta_time=1_700_000_000))
        )
        q = await adapter.get_current_price("USD_JPY")
        assert int(q.ts.timestamp()) == 1_700_000_000

    @respx.mock
    async def test_missing_price_raises_rather_than_guessing(self, adapter):
        payload = _chart([1], [150.0])
        payload["chart"]["result"][0]["meta"] = {}
        respx.get(f"{BASE}/USDJPY=X").mock(return_value=httpx.Response(200, json=payload))
        with pytest.raises(BrokerConnectionError):
            await adapter.get_current_price("USD_JPY")

    def test_jpy_and_non_jpy_pip_sizes(self):
        assert pip_size("USD_JPY") == 0.01
        assert pip_size("EUR_USD") == 0.0001


class TestErrorHandling:
    async def test_unmapped_instrument_refuses_instead_of_guessing(self, adapter):
        """Guessing a symbol risks quietly pulling a different market's prices."""
        with pytest.raises(BrokerConnectionError, match="SYMBOL_MAP"):
            await adapter.get_current_price("XAU_USD")

    @respx.mock
    async def test_http_error_becomes_broker_connection_error(self, adapter):
        respx.get(f"{BASE}/USDJPY=X").mock(return_value=httpx.Response(503))
        with pytest.raises(BrokerConnectionError):
            await adapter.get_current_price("USD_JPY")

    @respx.mock
    async def test_yahoo_error_payload_is_surfaced(self, adapter):
        respx.get(f"{BASE}/USDJPY=X").mock(
            return_value=httpx.Response(200, json={"chart": {"error": {"code": "Not Found"}, "result": None}})
        )
        with pytest.raises(BrokerConnectionError):
            await adapter.get_current_price("USD_JPY")

    @respx.mock
    async def test_health_check_is_false_when_unreachable(self, adapter):
        respx.get(f"{BASE}/USDJPY=X").mock(side_effect=httpx.ConnectError("down"))
        assert await adapter.health_check() is False


class TestH4Resampling:
    @respx.mock
    async def test_hourly_bars_collapse_into_aligned_four_hour_buckets(self, adapter):
        # 8 hourly bars starting at 00:00 UTC -> two 4h buckets.
        stamps = [i * 3600 for i in range(8)]
        closes = [float(i) for i in range(1, 9)]
        respx.get(f"{BASE}/USDJPY=X").mock(return_value=httpx.Response(200, json=_chart(stamps, closes)))
        candles = await adapter.get_candles("USD_JPY", Granularity.H4, 10)
        assert len(candles) == 2
        first = candles[0]
        assert first.open_time.hour == 0
        assert first.close == 4.0          # last hourly close in the bucket
        assert first.high == pytest.approx(4.2)  # max across the bucket
        assert first.granularity is Granularity.H4

    @respx.mock
    async def test_bucket_is_not_final_until_every_hour_in_it_is(self, adapter):
        stamps = [i * 3600 for i in range(8)]
        closes = [float(i) for i in range(1, 9)]
        respx.get(f"{BASE}/USDJPY=X").mock(return_value=httpx.Response(200, json=_chart(stamps, closes)))
        candles = await adapter.get_candles("USD_JPY", Granularity.H4, 10)
        assert candles[0].is_final is True
        assert candles[-1].is_final is False  # contains the still-forming hour


def test_watchlist_instruments_are_all_mapped():
    """A missing mapping would make the adapter refuse mid-run for that pair."""
    for symbol in ("USD_JPY", "EUR_JPY", "GBP_JPY", "EUR_USD"):
        assert symbol in SYMBOL_MAP
