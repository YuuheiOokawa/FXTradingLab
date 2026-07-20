# 06. Broker API Design

> **Re-verified in docs/16_BROKER_SELECTION_REVIEW.md** — a dedicated pass
> specifically checking whether "GMO Coin" (known primarily as a crypto
> exchange) was mistakenly credited with an FX API that's actually
> crypto-only. Conclusion: the FX API is real and separate from the crypto
> API (different docs, different request host). See docs/16 for full sourcing
> and the one precision fix that came out of it (exact host name).

## Research findings (2026)

- **OANDA Japan (oanda.jp)** does offer a REST API to individual residents
  (`developer.oanda.com/docs/jp`), but it is gated: it requires "Gold" membership
  status and a Pro-course account with balance ≥ ¥250,000 on the NY server. New
  accounts get temporary Gold status; after that, maintaining it needs very large
  monthly volume. Demo/practice accounts expire after 30 days unless Gold. OANDA's
  global v20 API (used by OANDA US/Europe/Australia, with easy practice accounts) is
  **not** generally available to Japan residents due to regulatory entity separation.
- **GMO Coin 外国為替FX** has a genuinely open, individually-accessible public REST
  API (Public + Private endpoints, 10-language sample SDKs, `api.coin.z.com/fxdocs`),
  usable immediately after opening an account and generating an API key, with a
  30-day fee-free trial and a low 0.002%/trade fee thereafter. This is the most
  practical *actually reachable today* broker API for a Japan-resident individual.
- Other major JP retail brokers (SBI FXトレード, 楽天FX, 外為どっとコム, GMOクリック証券)
  do not currently expose an open individual trading REST API; MT4/MT5-only brokers
  require a paid third-party bridge (e.g. MetaApi.cloud), an extra dependency and
  latency/reliability risk not justified for v1.
- For pure market-data (no account needed) in PAPER/BACKTEST modes, GMO Coin's Public
  API and Twelve Data (free tier) are both usable without any broker account.

## Decision

- **Reference real adapter (implemented): `OandaAdapter`.** OANDA's v20 REST/streaming
  API shape is the industry-standard reference for FX broker APIs (stable, extremely
  well documented, and the same interface is used by OANDA's global entities where
  demo accounts are trivial to obtain for development/testing even though a JP
  resident's *live* account must go through oanda.jp specifically). Building the
  reference adapter against this API gives the cleanest `BrokerAdapter` contract and
  lets development/testing proceed immediately against a practice environment
  (`OANDA_ENVIRONMENT=practice`) without waiting on GMO Coin account approval.
- **Documented future adapter (interface stubbed, not implemented): `GmoCoinAdapter`.**
  Recommended as the actual path to a *live* JP account in Phase 10, since it's the
  broker Japan residents can realistically open and use today without a large balance
  gate. Left as a stub (`app/brokers/gmo_coin.py::GmoCoinAdapter` raising
  `NotImplementedError` per method with a docstring pointing at the fxdocs) so the
  interface boundary is proven to support a second broker without a rewrite.
- **Always-available fallback: `MockAdapter`.** Deterministic-but-randomized price
  generator + in-memory order/position book. Used automatically whenever
  `BROKER_API_TOKEN` is unset, so the whole app (dashboard, charts, signals,
  backtest, paper trading, replay) works with zero external credentials.

## BrokerAdapter interface

```python
class BrokerAdapter(Protocol):
    async def get_current_price(self, instrument: str) -> PriceQuote: ...
    async def get_candles(self, instrument: str, granularity: Granularity,
                           count: int, from_time: datetime | None = None) -> list[Candle]: ...
    async def get_account(self) -> AccountSummary: ...
    async def get_positions(self) -> list[BrokerPosition]: ...
    async def create_order(self, order: OrderRequest) -> OrderResult: ...
    async def close_position(self, instrument: str) -> OrderResult: ...
    async def stream_prices(self, instruments: list[str]) -> AsyncIterator[PriceQuote]: ...
```

All methods raise a common `BrokerError` hierarchy (`BrokerAuthError`,
`BrokerRateLimitError`, `BrokerConnectionError`, `BrokerOrderRejected`) so upstream
code (Risk Engine, Order Orchestrator, System status page) never needs to know which
concrete broker is behind the interface. `stream_prices` is implemented as a polling
loop with jittered interval for adapters without native streaming (Mock, GMO Coin
stub); `OandaAdapter` uses the true streaming endpoint when available and falls back
to polling.

## Selection at runtime

`app/brokers/factory.py` reads `BROKER_PROVIDER` (`mock` | `oanda` | `gmo_coin`)
and required credentials from environment variables; if `BROKER_PROVIDER=oanda`
but `OANDA_API_TOKEN` is missing, it logs a warning and falls back to
`MockAdapter` rather than failing app startup. This is what satisfies "the
app's main features work with zero configured API keys."

## MarketDataProvider vs TradingBroker split

Added in the production-readiness pass (`docs/15_PRODUCTION_READINESS_REVIEW.md`):
`app/brokers/base.py` splits `BrokerAdapter`'s methods into two `Protocol`s —
`MarketDataProvider` (price reads: `get_current_price`, `get_candles`,
`stream_prices`) and `TradingBroker` (order execution: `get_account`,
`get_positions`, `create_order`, `close_position`). A concrete adapter
(Mock/OANDA/GmoCoin) still implements the full `BrokerAdapter` ABC and
therefore structurally satisfies both — no adapter code changes needed. What
changed is `factory.py`, which now exposes `get_market_data_provider()` and
`get_trading_broker()` separately:

- `get_market_data_provider()` reads `MARKET_DATA_PROVIDER` (falls back to
  `BROKER_PROVIDER` if unset) — used everywhere prices are read: the worker's
  `MarketDataService`, the Signal Engine's backtest/live data fetches, and
  paper trading's fill-price lookups (paper trading never touches the trading
  broker at all).
- `get_trading_broker()` always reads `BROKER_PROVIDER` directly, never
  implicitly redirected — used only by the (currently disabled) LIVE order
  path.

**Why this is useful**: a market-data source and an order-execution target
don't have to be the same provider — e.g. a broader/cheaper data feed for
monitoring with a narrower, gated broker only for the actual trading account.

**Why this is risky if misused**: `factory.py::_warn_if_split()` logs a
startup warning, and `GET /system/status`'s `providers_split` field drives a
visible banner on the System page, whenever the two differ — because the
displayed price and the price an order would actually fill at can diverge
(spread/latency skew), and instrument symbols may not map 1:1 across
providers (e.g. one uses `USD_JPY`, another `USDJPY`). This is surfaced
loudly rather than silently, by design.
