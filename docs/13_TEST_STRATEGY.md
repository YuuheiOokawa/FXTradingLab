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

**Corrected during `docs/15_PRODUCTION_READINESS_REVIEW.md`**: this section
previously overclaimed what actually runs — verified against the real
`.github/workflows/ci.yml` rather than assumed. Current, accurate state:

`.github/workflows/ci.yml` runs on every push/PR, gating the merge on:
- Backend: `alembic upgrade head` against a real Postgres service container,
  then `pytest --cov=app` (gating — a failing test blocks the PR).
- Frontend: `eslint .` (gating), `tsc --noEmit` (gating), `vitest run` (gating),
  `next build` (gating).
- `docker compose config -q` validation (gating).

Two gaps, tracked honestly rather than hidden:
- `ruff check .` runs but is **advisory only** (`|| true`) — the codebase
  currently has ~39 pre-existing lint findings (mostly test-file import
  ordering and unused locals) that were not cleaned up as part of this
  review; flipping this to gating is a follow-up, not done yet.
- `mypy` is installed as a backend dev dependency but is **not wired into
  CI at all** — running it manually surfaces ~33 findings, a mix of missing
  third-party stub packages (`pandas-stubs`) and a handful of real
  `Optional`-narrowing gaps (e.g. `Instrument | None` accessed without a
  null check in a few route handlers) that would need fixing before this
  could gate without immediately breaking the pipeline. Not done this pass.
- The Playwright smoke test described below is **not automated in CI** —
  browser verification in this review was performed manually, repeatedly,
  against a running `docker compose` stack, not via a CI job. Wiring a
  headless Playwright job (bring up `docker compose`, wait for `/ready`,
  run the smoke script) is a reasonable follow-up but wasn't built this pass.

A manual-trigger (`workflow_dispatch`) deployment workflow
(`.github/workflows/deploy.yml`) is prepared for Railway/Vercel deploys but
never fires automatically on a merge — see that file's header comment and
`docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` for how to use it.

## What "done" means for a PR touching trading logic

Any change to Signal Engine, Risk Engine, Backtest Engine, or a Broker adapter must
include or update tests in the corresponding file above — this is a review checklist
item, not just a CI gate, because silent behavior drift in these modules is the
highest-consequence failure mode in this app.
