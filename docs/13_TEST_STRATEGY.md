# 13. Test Strategy

## Backend (pytest)

- **Unit** — indicators (`test_indicators.py`, checked against hand-computed/reference
  values), regime classifier, signal scoring components, backtest metrics math.
- **Broker adapter contract** — `test_broker_adapters.py` runs the *same* test suite
  against `MockAdapter` and against `OandaAdapter` with HTTP calls mocked (via
  `respx`), asserting both satisfy the `BrokerAdapter` protocol identically (e.g.
  `create_order` return shape, error mapping to the common `BrokerError` hierarchy).
- **Signal Engine** — fixtures with synthetic OHLC series engineered to hit each
  scoring branch (clean EMA stack, mixed MTF agreement, RSI cross, MACD cross, regime
  switch for Bollinger logic) with asserted expected score ranges and reason text.
- **Risk Engine** — one test per rejection rule (10 rules in `10_RISK_MANAGEMENT.md`),
  each asserting `RiskRejected` is raised **and** that a mock broker's `create_order`
  was never invoked. A dedicated test also drives the kill switch mid-FULL_AUTO-loop
  and asserts no further orders are placed.
- **Order Orchestrator / idempotency** — submits the same `idempotency_key` twice
  concurrently (`asyncio.gather`) and asserts exactly one broker order results.
- **Backtest engine** — golden-fixture test: fixed synthetic candle series + fixed
  config → exact expected trade list and metrics (regression-proof against future
  refactors).
- **Integration** — `httpx.AsyncClient` against the FastAPI app with a test Postgres
  (via `pytest-asyncio` + a Dockerized test DB in CI), covering the REST endpoints
  end-to-end including DB writes.

## Frontend (Vitest + Testing Library, Playwright)

- Component tests for the signal score breakdown component (renders ✓/△/✗ correctly
  from a fixture `SignalResult`), the order ticket calculator (max loss / RR /
  est. margin arithmetic), and the replay controls (step/play/pause/speed).
- Playwright smoke test: load Dashboard, load Chart page against the Mock backend,
  assert candles render and at least one WebSocket tick updates a tile — catches
  integration breakage the unit tests can't.

## CI

`.github/workflows/ci.yml` runs on every push/PR: backend lint (ruff) + type check
(mypy) + pytest with coverage; frontend lint (eslint) + type check (tsc) + vitest;
docker-compose config validation. Playwright smoke test is a separate, slower job.

## What "done" means for a PR touching trading logic

Any change to Signal Engine, Risk Engine, Backtest Engine, or a Broker adapter must
include or update tests in the corresponding file above — this is a review checklist
item, not just a CI gate, because silent behavior drift in these modules is the
highest-consequence failure mode in this app.
