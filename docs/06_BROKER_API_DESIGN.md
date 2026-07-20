# 06. Broker API Design

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

`app/brokers/factory.py::get_broker_adapter()` reads `BROKER_PROVIDER`
(`mock` | `oanda` | `gmo_coin`) and required credentials from environment variables;
if `BROKER_PROVIDER=oanda` but `OANDA_API_TOKEN` is missing, it logs a warning and
falls back to `MockAdapter` rather than failing app startup. This is what satisfies
"the app's main features work with zero configured API keys."
