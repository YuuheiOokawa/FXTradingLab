# 18. End-to-End Testing

This complements `13_TEST_STRATEGY.md`, not replaces it. The backend pytest
suite and frontend vitest suite are what actually verify correctness (fill
logic, risk checks, judgment scoring, etc.) — they run fast, in isolation,
against mocked boundaries. The E2E suite below cannot see that level of
detail; it exists for a different failure class: **wiring** breaks that only
show up when the real frontend talks to the real backend through a real
browser — a renamed API field nothing else caught, a page that 500s only
once actual data is in the DB, a mutation whose success handler doesn't
update the UI. Treat a green E2E run as "the app is navigable and the wiring
holds," not as a substitute for the unit/integration suites' correctness
coverage.

## What it covers

`frontend/e2e/full-flow.spec.ts` drives a real Chromium browser through the
same journey an operator actually follows, end to end, in one serial run:

1. **Dashboard** — loads, watchlist prices render, no console/JS errors.
2. **Markets** — instrument list renders.
3. **Chart** — candlestick chart actually draws (canvas present).
4. **Signals** — live score breakdown renders.
5. **Replay** — create a session, decide BUY with SL/TP, confirm a judgment
   badge (良い判断/普通/危険な判断) appears, step forward, close the
   decision. Exercises the persisted `ReplaySession`/`ReplayTrade` path and
   the non-outcome-based judgment scoring end to end.
6. **Simulation** — submit a what-if trade, confirm live P/L tracking
   renders.
7. **Backtest** — run a (small, for speed) backtest, confirm the equity
   curve and results panel render.
8. **Paper Trading** — place a real market order with SL/TP through the
   Risk Engine, confirm the position opens with the slippage-adjusted fill;
   then close it in a follow-up step.
9. **Trades** — confirm the just-closed paper trade appears in the journal
   (proves `POST /paper/positions/{id}/close` actually writes to
   `TradeJournalEntry`, not just updates in-memory state).
10. **Analytics** — loads without error.
11. **System** — dependency status tiles render; the Kill Switch is armed
    and then disarmed in the same test, so the suite never leaves the app in
    a stopped state.

Every step also asserts the accumulated `console.error`/`pageerror`/
`requestfailed` list for that page is empty (WebSocket upgrade "failures",
which are a normal side effect of the HTTP-to-WS protocol switch, are
filtered out).

## Running it

The suite assumes Postgres, Redis, the FastAPI backend, the worker process,
and the Next.js dev server are **already running** — it does not start them
itself, since the backend/worker live outside npm's process tree. From the
repo root, in separate terminals (or see `docker-compose.yml` for a
single-command version of the first four):

```bash
# 1. Infra
pg_ctl start / service postgresql start   # however your Postgres is managed
service redis-server start

# 2. Backend
cd backend && source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. Worker (separate terminal)
cd backend && source .venv/bin/activate
python -m app.worker.main

# 4. Frontend (separate terminal)
cd frontend
npm run dev

# 5. E2E suite (separate terminal, once all four above are up)
cd frontend
npm run test:e2e
```

First run needs the Playwright browser binary: `npx playwright install
chromium` (skip this if `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` is set and a
pre-installed Chromium is pointed to via `PLAYWRIGHT_CHROMIUM_PATH`).

`E2E_BASE_URL` (default `http://localhost:3000`) and `E2E_API_URL` (default
`http://localhost:8000`) override the target if you're running against a
non-default port.

## Why it's advisory in CI, not a required gate

`.github/workflows/ci.yml` has an `e2e` job that boots the full stack in CI
and runs this suite, but it's `continue-on-error: true` — the same pattern
already used for `ruff`/`pip-audit`/`npm audit`. Reasons this isn't a
required merge gate the way lint/typecheck/unit tests are:

- It depends on the mock broker's synthetic tick generation timing, which
  is not deterministic to the millisecond the way a unit test's fixtures
  are.
- A single serial run through 11 real pages is inherently slower and has
  more moving parts (WebSocket delivery, APScheduler job timing) than any
  one unit test, so it has more surface area for CI-environment flakiness
  unrelated to an actual regression.
- Failing PRs on flaky infrastructure trains people to `--no-verify` past
  CI, which is worse than an advisory signal that's usually right.

A failing E2E run in CI is still worth reading — `playwright-report/` is
uploaded as a build artifact on failure — it just doesn't block the merge
on its own.

## Extending it

New pages/flows should get a new `test(...)` block in the same file (or a
new spec file for a genuinely separate journey) rather than growing the
existing tests further — keep each `test()` focused on one page/flow so a
failure's title tells you where to look without opening the trace.
