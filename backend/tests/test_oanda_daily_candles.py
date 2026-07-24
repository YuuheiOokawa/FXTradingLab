"""OANDA daily-candle contract, focused on what the playbook depends on.

The playbook (app/services/playbook.py) is evaluated on DAILY candles and its
correctness rests on never reading a candle that is still forming — doing so is
look-ahead, and it silently flatters live results. `auto_trader._drop_forming_candle`
implements that guard by trusting `Candle.is_final`, so these tests pin the
mapping from OANDA's `complete` flag onto that field, and pin the guard itself.
"""
import httpx
import pytest
import respx

from app.brokers.oanda import OandaAdapter
from app.brokers.schemas import Granularity
from app.services.auto_trader import _drop_forming_candle

BASE = "https://api-fxpractice.oanda.com/v3"


@pytest.fixture
def adapter():
    return OandaAdapter(api_token="test-token", account_id="001-001-1234567-001", environment="practice")


def _candle(time: str, close: str, complete: bool) -> dict:
    return {
        "time": time,
        "volume": 100,
        "complete": complete,
        "mid": {"o": "150.000", "h": "151.000", "l": "149.000", "c": close},
    }


@respx.mock
async def test_daily_granularity_is_requested_verbatim(adapter):
    route = respx.get(f"{BASE}/instruments/USD_JPY/candles").mock(
        return_value=httpx.Response(200, json={"candles": [_candle("2026-07-22T00:00:00Z", "150.5", True)]})
    )
    await adapter.get_candles("USD_JPY", Granularity.D, 300)
    assert route.called
    assert route.calls.last.request.url.params["granularity"] == "D"
    assert route.calls.last.request.url.params["count"] == "300"


@respx.mock
async def test_incomplete_candle_is_marked_not_final(adapter):
    """OANDA returns today's still-forming bar with complete=false. If that were
    mapped to is_final=True the bot would trade on a close that can still move."""
    respx.get(f"{BASE}/instruments/USD_JPY/candles").mock(
        return_value=httpx.Response(
            200,
            json={
                "candles": [
                    _candle("2026-07-21T00:00:00Z", "150.5", True),
                    _candle("2026-07-22T00:00:00Z", "151.5", True),
                    _candle("2026-07-23T00:00:00Z", "152.5", False),  # today, still forming
                ]
            },
        )
    )
    candles = await adapter.get_candles("USD_JPY", Granularity.D, 3)
    assert [c.is_final for c in candles] == [True, True, False]


@respx.mock
async def test_missing_complete_flag_defaults_to_final(adapter):
    """A historical bar with the flag omitted must not be discarded as forming."""
    respx.get(f"{BASE}/instruments/USD_JPY/candles").mock(
        return_value=httpx.Response(
            200,
            json={"candles": [{"time": "2026-07-21T00:00:00Z", "volume": 1,
                               "mid": {"o": "1", "h": "1", "l": "1", "c": "1"}}]},
        )
    )
    candles = await adapter.get_candles("USD_JPY", Granularity.D, 1)
    assert candles[0].is_final is True


class TestFormingCandleGuard:
    """`_drop_forming_candle` is the only thing standing between the playbook and
    a look-ahead bug, so it is tested on its own."""

    class _C:
        def __init__(self, is_final: bool) -> None:
            self.is_final = is_final

    def test_drops_a_trailing_forming_candle(self):
        candles = [self._C(True), self._C(True), self._C(False)]
        assert len(_drop_forming_candle(candles)) == 2

    def test_keeps_everything_when_last_is_closed(self):
        candles = [self._C(True), self._C(True)]
        assert len(_drop_forming_candle(candles)) == 2

    def test_handles_empty_input(self):
        assert _drop_forming_candle([]) == []

    def test_treats_missing_attribute_as_closed(self):
        """MockAdapter's candles have is_final=True; an adapter that omits the
        attribute entirely must not have its whole history dropped."""
        class Bare:
            pass

        assert len(_drop_forming_candle([Bare(), Bare()])) == 2
