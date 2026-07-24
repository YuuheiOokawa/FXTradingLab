"""Yahoo Finance market-data adapter — real prices, no account, no KYC.

Exists because the built-in `MockAdapter` is a seeded random walk: useful for
exercising the app, worthless for judging a strategy. Connecting a broker feed
normally means opening an account, and some brokers require identity
verification even for a demo. This adapter removes that blocker for the
forward-testing phases, which only ever need PRICES — paper trading simulates
its own fills and never contacts a broker.

**Market data only.** `get_account`, `get_positions`, `create_order` and
`close_position` raise rather than return plausible-looking values, because
Yahoo is not a broker and there is no account behind it. Silently returning a
fake balance would let an order path "succeed" against nothing. Configure this
as `MARKET_DATA_PROVIDER` alongside a real `BROKER_PROVIDER`, or use it with
paper trading, which is what it is for.

Deliberate limitations, stated because they decide whether this is usable:

* **Unofficial endpoint.** No API contract, no uptime guarantee; it can change
  or start refusing requests without notice. Fine for personal research, not
  something to depend on for real-money execution.
* **Delayed, and no true bid/ask.** Yahoo publishes a single price, not a
  two-sided quote. A synthetic spread (`SYNTHETIC_SPREAD_PIPS`) is applied so
  downstream cost/staleness logic behaves sanely, but it is an assumption, not
  a real dealable spread — a live broker's spread will differ, especially
  around news.
* **Daily bars are the honest use.** The shipped playbook is a daily strategy,
  which is exactly what this serves well. Intraday granularities work but are
  history-limited by Yahoo (15m ≈ 60 days, 1h ≈ 730 days).

TLS note: some corporate networks terminate TLS with a private root CA that
certifi does not contain. `truststore` (when installed) makes Python use the
operating system's certificate store, which is where such a CA already lives.
Verification is never disabled.
"""
from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx

from app.brokers.base import BrokerAdapter
from app.brokers.errors import BrokerConnectionError
from app.brokers.schemas import (
    AccountSummary,
    BrokerPosition,
    Candle,
    Granularity,
    OrderRequest,
    OrderResult,
    PriceQuote,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

# App instrument code -> Yahoo symbol.
SYMBOL_MAP: dict[str, str] = {
    "USD_JPY": "USDJPY=X",
    "EUR_JPY": "EURJPY=X",
    "GBP_JPY": "GBPJPY=X",
    "EUR_USD": "EURUSD=X",
    "GBP_USD": "GBPUSD=X",
    "AUD_JPY": "AUDJPY=X",
    "AUD_USD": "AUDUSD=X",
    "CHF_JPY": "CHFJPY=X",
}

GRANULARITY_MAP: dict[Granularity, str] = {
    Granularity.M1: "1m",
    Granularity.M5: "5m",
    Granularity.M15: "15m",
    Granularity.H1: "1h",
    Granularity.H4: "1h",  # Yahoo has no 4h; see get_candles
    Granularity.D: "1d",
}

# Yahoo caps how far back each interval reaches. Requesting more silently
# returns less (or coarser bars), so the range is chosen to fit.
MAX_RANGE: dict[str, str] = {"1m": "7d", "5m": "60d", "15m": "60d", "1h": "730d", "1d": "10y"}

# Yahoo publishes one price, not a quote. Half of this is added/subtracted to
# synthesise bid/ask. Values are typical retail spreads, deliberately on the
# wide side so nothing downstream assumes a better fill than it would get.
SYNTHETIC_SPREAD_PIPS = 1.5


def pip_size(instrument: str) -> float:
    return 0.01 if instrument.endswith("JPY") else 0.0001


def _ssl_context() -> ssl.SSLContext | bool:
    """OS trust store when `truststore` is installed, otherwise normal certifi
    verification. Never returns an unverified context."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True


class YahooMarketDataAdapter(BrokerAdapter):
    """Read-only real market data. Not a broker — see the module docstring."""

    provider = "yahoo"

    def __init__(self, poll_interval_ms: int = 2000, timeout: float = 20.0) -> None:
        self._poll_interval_ms = poll_interval_ms
        self._timeout = timeout
        self._verify = _ssl_context()

    # ---------------------------------------------------------------- helpers --

    def _symbol(self, instrument: str) -> str:
        symbol = SYMBOL_MAP.get(instrument)
        if symbol is None:
            # Guessing a mapping risks silently pulling a different market's
            # prices, so refuse instead.
            raise BrokerConnectionError(
                f"no Yahoo symbol mapping for {instrument!r}; add it to app/brokers/yahoo.py SYMBOL_MAP"
            )
        return symbol

    async def _fetch(self, instrument: str, params: dict[str, str]) -> dict:
        url = f"{BASE_URL}/{self._symbol(instrument)}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
        except httpx.HTTPError as exc:
            raise BrokerConnectionError(f"Yahoo request failed for {instrument}: {exc}") from exc
        if resp.status_code != 200:
            raise BrokerConnectionError(f"Yahoo returned {resp.status_code} for {instrument}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise BrokerConnectionError(f"Yahoo returned non-JSON for {instrument}") from exc

        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise BrokerConnectionError(f"Yahoo error for {instrument}: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            raise BrokerConnectionError(f"Yahoo returned no data for {instrument}")
        return results[0]

    # ----------------------------------------------------------- market data --

    async def get_current_price(self, instrument: str) -> PriceQuote:
        result = await self._fetch(instrument, {"range": "1d", "interval": "1m"})
        meta = result.get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            raise BrokerConnectionError(f"Yahoo returned no price for {instrument}")

        # Prefer the exchange's own timestamp: the staleness check downstream is
        # only meaningful if this reflects when the price was made, not when we
        # happened to ask for it.
        raw_ts = meta.get("regularMarketTime")
        ts = datetime.fromtimestamp(raw_ts, tz=UTC) if raw_ts else datetime.now(UTC)

        half = SYNTHETIC_SPREAD_PIPS * pip_size(instrument) / 2
        return PriceQuote(
            instrument=instrument,
            bid=round(float(price) - half, 6),
            ask=round(float(price) + half, 6),
            ts=ts,
        )

    async def get_candles(
        self,
        instrument: str,
        granularity: Granularity,
        count: int,
        from_time: datetime | None = None,
    ) -> list[Candle]:
        interval = GRANULARITY_MAP[granularity]
        params = {"range": MAX_RANGE.get(interval, "1y"), "interval": interval}
        if granularity is Granularity.H4:
            # Four hourly bars collapse into one, so ask for 4x the history —
            # otherwise a 260-bar EMA200 request silently comes back short.
            params["range"] = MAX_RANGE["1h"]
        if from_time is not None:
            params = {
                "period1": str(int(from_time.timestamp())),
                "period2": str(int(datetime.now(UTC).timestamp())),
                "interval": interval,
            }
        result = await self._fetch(instrument, params)

        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        opens, highs = quote.get("open") or [], quote.get("high") or []
        lows, closes = quote.get("low") or [], quote.get("close") or []

        # Yahoo's last bar is the one still forming. Everything earlier is
        # closed. This flag is what stops the playbook reading a price that can
        # still move (a look-ahead bug) — see auto_trader._drop_forming_candle.
        last_index = len(timestamps) - 1

        candles: list[Candle] = []
        for i, ts in enumerate(timestamps):
            o, hi, lo, c = opens[i], highs[i], lows[i], closes[i]
            if None in (o, hi, lo, c):
                continue  # Yahoo emits nulls for gaps/holidays
            candles.append(
                Candle(
                    instrument=instrument,
                    granularity=granularity,
                    open_time=datetime.fromtimestamp(ts, tz=UTC),
                    open=float(o), high=float(hi), low=float(lo), close=float(c),
                    volume=0,  # Yahoo reports no meaningful FX volume
                    is_final=i < last_index,
                )
            )

        if granularity is Granularity.H4:
            candles = _resample_h4(candles)
        return candles[-count:] if count and len(candles) > count else candles

    async def stream_prices(self, instruments: list[str]) -> AsyncIterator[PriceQuote]:
        """Polls, because Yahoo offers no push feed. A failure for one
        instrument is logged and skipped rather than killing the stream."""
        while True:
            for instrument in instruments:
                try:
                    yield await self.get_current_price(instrument)
                except BrokerConnectionError:
                    logger.warning("yahoo: price poll failed for %s", instrument, extra={"symbol": instrument})
            await asyncio.sleep(self._poll_interval_ms / 1000)

    async def health_check(self) -> bool:
        try:
            await self.get_current_price("USD_JPY")
            return True
        except Exception:
            return False

    # --------------------------------------------------------------- trading --
    # Yahoo is not a broker. These raise instead of returning placeholder data
    # so an order path cannot appear to succeed against a non-existent account.

    def _not_a_broker(self, what: str) -> BrokerConnectionError:
        return BrokerConnectionError(
            f"YahooMarketDataAdapter is market-data only and cannot {what}. "
            "Set BROKER_PROVIDER to a real broker (or use paper trading) and keep "
            "MARKET_DATA_PROVIDER=yahoo for prices."
        )

    async def get_account(self) -> AccountSummary:
        raise self._not_a_broker("report an account")

    async def get_positions(self) -> list[BrokerPosition]:
        raise self._not_a_broker("report positions")

    async def create_order(self, order: OrderRequest) -> OrderResult:
        raise self._not_a_broker("place orders")

    async def close_position(self, instrument: str) -> OrderResult:
        raise self._not_a_broker("close positions")


def _resample_h4(candles: list[Candle]) -> list[Candle]:
    """Build 4-hour bars from hourly ones, since Yahoo has no 4h interval.

    Buckets align to 00:00/04:00/08:00... UTC. A bucket is final only when every
    hour in it is final, so a partly-formed 4h bar is never treated as closed.
    """
    buckets: dict[int, list[Candle]] = {}
    for c in candles:
        key = int(c.open_time.timestamp()) // 14400
        buckets.setdefault(key, []).append(c)

    out: list[Candle] = []
    for key in sorted(buckets):
        group = buckets[key]
        out.append(
            Candle(
                instrument=group[0].instrument,
                granularity=Granularity.H4,
                open_time=datetime.fromtimestamp(key * 14400, tz=UTC),
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=0,
                is_final=all(c.is_final for c in group),
            )
        )
    return out
