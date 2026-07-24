# FX Trading Lab

A personal-use FX monitoring, technical-analysis, trade-simulation, backtesting,
and (safely gated) live-trading web application. Real market data (via a
pluggable `BrokerAdapter`, defaulting to a realistic built-in simulator when no
broker credentials are configured), a real rule-based signal engine with
itemized explanations, a real event-driven backtest engine, and a real risk
management layer — not a mockup.

See `docs/00_PROJECT_OVERVIEW.md` for the full design rationale, and
`docs/14_IMPLEMENTATION_PLAN.md` for an honest phase-by-phase status of what's
implemented versus what's designed-but-not-built yet.

## Safety first

- **LIVE trading is disabled by default everywhere**, including in
  `production`. Enabling it requires three independent conditions to all be
  true simultaneously — see `docs/10_RISK_MANAGEMENT.md`.
- Every order (paper or live) is validated by a `RiskEngine` before it can
  reach a broker; a Kill Switch can halt new orders and flatten positions
  instantly.
- No broker API secret, and no backend credential of any kind, is ever sent to
  the browser — the frontend acts as a backend-for-frontend (BFF), proxying
  REST calls server-side and issuing short-lived, single-use tickets for the
  WebSocket price stream. See `docs/11_SECURITY.md` "BFF migration".

## Stack

Next.js 15 (App Router, TypeScript, Tailwind) · FastAPI (Python 3.12,
SQLAlchemy 2.0 async) · PostgreSQL 16 · Redis 7 · `lightweight-charts` ·
Docker Compose. Full rationale in `docs/03_TECH_STACK.md`.

## Quickstart (Docker Compose — recommended)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API + docs: http://localhost:8000/docs
- With zero configured broker credentials, everything works immediately
  against a built-in `MockAdapter` — realistic simulated USD/JPY, EUR/JPY,
  GBP/JPY, EUR/USD price action, indicators, signals, backtests, paper
  trading, replay. No API keys required to try the app.

To connect a real OANDA practice account instead, set in `.env`:

```
BROKER_PROVIDER=oanda
OANDA_API_TOKEN=...
OANDA_ACCOUNT_ID=...
OANDA_ENVIRONMENT=practice
```

## Local development (without Docker)

### Backend

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# Postgres + Redis running locally (or point DATABASE_URL/REDIS_URL elsewhere)
export DATABASE_URL=postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab
export REDIS_URL=redis://localhost:6379/0

alembic upgrade head
uvicorn app.main:app --reload          # API on :8000
python -m app.worker.main              # in a second terminal: market data worker

pytest                                  # run the test suite (needs a *_test DB — see below)
```

Tests run against a real Postgres database (not a mocked ORM — see
`docs/13_TEST_STRATEGY.md`). Create it once:

```bash
createdb -U fxlab fxlab_test
DATABASE_URL=postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab_test alembic upgrade head
```

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                             # :3000, expects the backend on :8000
```

## Local development on Windows (no Docker)

If Docker isn't available, the app runs directly against a local PostgreSQL
service, a portable Redis, a Python venv, and the Next.js dev server. This is
the exact setup this checkout was brought up under.

Prerequisites: PostgreSQL (any 16/17), Node.js 20+, Python 3.12+ (3.14 works).

### One-time setup

```powershell
# 1. Database — create the fxlab role and both databases (run as the postgres
#    superuser; adjust the psql path to your install).
$env:PGPASSWORD='<postgres-password>'
$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
& $psql -U postgres -h localhost -c "CREATE ROLE fxlab LOGIN PASSWORD 'fxlab';"
& $psql -U postgres -h localhost -c "CREATE DATABASE fxlab OWNER fxlab;"
& $psql -U postgres -h localhost -c "CREATE DATABASE fxlab_test OWNER fxlab;"

# 2. Redis — no Windows-native Redis, so use the portable build
#    (Memurai's MSI custom actions fail without SYSTEM's TEMP dirs). Placed at
#    ..\tools\redis\ so start-local.ps1 finds it; adjust that path if you move it.
#    Any Redis reachable at localhost:6379 works just as well.

# 3. Backend — venv + deps + migrations. (redis-server must be running for
#    nothing here, but the API/worker need it at runtime.)
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic upgrade head          # against fxlab
# test DB (once): point DATABASE_URL at fxlab_test, then upgrade head again.

# 4. Frontend
cd ..\frontend
npm install
```

The `backend/.env` and `frontend/.env.local` in this checkout are already set
for localhost (Postgres + Redis on localhost, `APP_ENV=development` so auth and
the /login gate are off, built-in mock broker). One gotcha: `MARKET_DATA_PROVIDER`
is typed as an optional Literal, so a **blank** `MARKET_DATA_PROVIDER=` line
(as in `.env.example`) fails startup validation — leave the key absent, not empty.

### Running

```powershell
# From the repo root — opens Redis, API, worker, and frontend in four windows:
.\start-local.ps1
```

- Frontend: http://localhost:3001 (3000 is reserved for another app on this
  machine, so the frontend's `dev` script binds 3001)
- API docs: http://localhost:8000/docs
- Health/readiness: http://localhost:8000/ready (DB + Redis + broker checks)

Or start each piece by hand (four terminals):

```powershell
# 1. Redis
..\tools\redis\Redis-8.8.0-Windows-x64-msys2\redis-server.exe --port 6379 --save "" --appendonly no
# 2. API            (in backend/)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# 3. Worker         (in backend/)
.\.venv\Scripts\python.exe -m app.worker.main
# 4. Frontend       (in frontend/) — binds :3001 (see package.json "dev")
npm run dev
```

The WebSocket price stream connects straight to the backend on `:8000`
(`NEXT_PUBLIC_WS_URL`), independent of the frontend's own port, so only the
frontend port changed.

## Automated trading (per-instrument playbook)

`app/services/playbook.py` gives **each instrument the strategy its own price
behaviour calls for**, because one shared rule loses: across ~23 years of real
daily data (2003-2026) a single EMA trend-follower applied to all four pairs
returned **-12,926 pips (PF 0.81)**, while the per-pair book below returned
**+14,859 pips (PF 1.64)** and was profitable in every nested 5/10/15/20/23-year
window.

| Instrument | Style | Exit | Regime gate | Stop / trail |
|---|---|---|---|---|
| USD/JPY | 20-day Donchian breakout | ATR trailing stop | ADX ≥ 25 | 3 / 4 ATR |
| EUR/JPY | EMA 10/30 cross, EMA200-filtered | ATR trailing stop | ADX ≥ 15 | 2 / 3 ATR |
| GBP/JPY | Bollinger 2.5σ fade, **long only** | back to the 20-day mean, 30-day cap | ADX ≤ 30 | 3 ATR |
| EUR/USD | RSI fade | back to the mean | — | **disabled** — its edge is inside the noise |

**Parameters are chosen by multi-era survival, not by best total return.** Extending
USD/JPY history back to 1996 produced a stretch (1996-2003) never used to select
anything — and the original parameters, tuned on 2003-2026, earned PF 1.29 there
and **PF 0.76, an outright loss, on the unused years**. The settings above are
profitable in every era tested:

| | early era | middle | recent |
|---|---|---|---|
| USD/JPY | 1996-2003 PF 1.39 | 2003-2015 PF 1.61 | 2015-2026 PF 1.17 |
| EUR/JPY | 2003-2010 PF 1.00 | 2010-2018 PF 2.58 | 2018-2026 PF 2.07 |
| GBP/JPY | 2003-2010 PF 2.09 | 2010-2018 PF 1.20 | 2018-2026 PF 2.74 |

Pooled across the three pairs this trades a slightly lower headline return for a
**36% smaller worst drawdown** (-2,073 → -1,329 pips) and a higher win rate
(50.0% → 53.2%). Once 1996-2003 was used to pick parameters it stopped being an
independent test, so only live forward testing produces evidence that was never
fitted to.

Position size is derived from `max_risk_per_trade_pct` so that being stopped out
costs the same fraction of equity on every pair (`app/services/position_sizing.py`),
and is halved when volatility spikes to twice its baseline. Stops and targets on
paper positions are enforced by `app/worker/jobs/paper_brackets.py`; trailing and
mean-reversion exits by `app/worker/jobs/playbook_manage.py`.

Enable it in **Settings → auto_mode = `full_auto`**. It trades the PAPER account
only — LIVE order submission is never wired to an automatic loop.

Live results are scored against the backtest's expectations on the **Analytics**
page (`GET /api/v1/analytics/forward-test`), counting only auto-trader trades so a
hand-placed order cannot flatter the record.

> This is a modest edge, not a money printer. The same 23-year study shows
> multi-year stretches (2013-2020) where the approach bleeds. Forward-test on
> paper before risking anything real.

### Connecting real market data (OANDA practice)

The built-in simulator is a seeded random walk — fine for exercising the app,
useless for judging a strategy. **Forward-test numbers only mean something once
real prices are connected.** Create a free OANDA **practice** account, then copy
what you need from `backend/.env.oanda.example` into `backend/.env`:

```
BROKER_PROVIDER=oanda
OANDA_API_TOKEN=...
OANDA_ACCOUNT_ID=...
OANDA_ENVIRONMENT=practice
```

Verify before trusting it — read-only, never places an order:

```bash
cd backend
python -m scripts.check_oanda
```

It checks credentials, spreads, that daily history is deep enough for the
playbook's EMA200 (~260 closed bars), that the still-forming bar is flagged
`complete: false` (the look-ahead guard depends on it), and that each pair's
playbook evaluates. Note the simulator marks every candle final, so that guard
is only genuinely exercised against a real feed.

Then set **auto_mode = `full_auto`** and let it run. Daily rules trade rarely, so
expect days-to-weeks before the Analytics forward test has enough closed trades
to say anything (it labels anything under 20 trades "too early").

### Real-money execution: built, gated, and not automated

`OrderOrchestrator.submit_live_order` is fully implemented — Risk Engine
validation against real broker account state, idempotent replay protection, and
distinct handling for a broker rejection versus a dropped connection (the latter
is recorded as `unknown`, never `rejected`, because a retry could otherwise open
a duplicate position).

It is reachable **only** through the manual `POST /api/v1/live/orders` endpoint,
and only when all three gates are open:

1. `LIVE_TRADING_ENABLED=true` in the environment,
2. `live_trading_admin_enabled` in Settings,
3. `confirm_live: true` on the individual request.

**No automatic code path can call it.** The auto-trader submits PAPER orders
exclusively. That is not a convention — `tests/test_live_execution.py` parses the
auto-trader's AST, scans every worker job, and drives a full evaluation cycle
with all three gates open, failing if a real order is ever attempted.

Use `POST /api/v1/live/orders/preview` first: it runs the identical risk
assessment (literally the same `_assess_live_order` call) with no execution path
in its body, so a "would approve" preview is the same verdict execution acts on.

## Project layout

```
FXTradingLab/
├── docs/               # 00-14: requirements, architecture, DB/API design,
│                        signal engine, backtest, risk, security, deployment,
│                        test strategy, implementation status
├── backend/            # FastAPI app: API + worker share one codebase
│   ├── app/
│   │   ├── brokers/     # BrokerAdapter interface + Mock/OANDA/GmoCoin(stub)
│   │   ├── services/    # signal engine, indicators, regime, backtest,
│   │   │                  risk engine, order orchestrator, market data, replay
│   │   ├── api/routes/  # REST endpoints
│   │   ├── ws/           # WebSocket endpoints (live prices, system events)
│   │   ├── db/models/    # SQLAlchemy models
│   │   └── worker/       # background process: price polling, retention, auto-trader
│   ├── alembic/          # migrations
│   └── tests/            # pytest — indicators, signal engine, risk engine,
│                            backtest, broker contract, order orchestrator
├── frontend/            # Next.js app (Dashboard, Markets, Chart, Signals,
│                            Replay, Simulation, Backtest, Paper Trading,
│                            Trades, Analytics, Settings, System)
└── docker-compose.yml    # postgres + redis + api + worker + frontend
```

## Modes

1. **BACKTEST** — historical validation.
2. **PAPER_LIVE** — real-time prices, virtual ¥1,000,000 account, no real broker calls.
3. **DEMO** — broker practice/demo account (e.g. OANDA `practice` environment).
4. **LIVE** — real account, real money. Off by default; see `docs/10_RISK_MANAGEMENT.md`.

## Deployment

See `docs/12_DEPLOYMENT.md` for the full platform comparison and
`docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` for the complete step-by-step guide
(cost estimate, env vars, verification, backups, rollback). Short version:
Vercel for the frontend, Railway for the backend (API + worker as two
always-on services from one Docker image, needed because the market-data
poller and WebSocket fan-out can't run on Vercel's serverless functions),
managed Postgres + Redis.

Nothing below runs automatically — these are the exact commands to run
yourself once you have accounts on both platforms (this repo/environment has
no deploy credentials for either).

```bash
# One-time CLI setup
npm install -g @railway/cli   # or: brew install railway
npm install -g vercel

# Railway: log in, create a project, add Postgres + Redis
railway login
railway init                                   # in repo root
railway add --database postgres
railway add --database redis

# Railway: create the two backend services (root directory = backend)
# — the dashboard is the easier way to set "Root Directory: backend" for
#   each service and the worker's Start Command override; see docs/17 §2.
railway up --service api                       # from backend/, after linking
railway run --service api alembic upgrade head # run the initial migration

# Vercel: deploy the frontend (root directory = frontend) — see
# docs/11_SECURITY.md "BFF migration" for what each of these is for.
cd frontend
vercel link
vercel env add NEXT_PUBLIC_WS_URL production
vercel env add BACKEND_INTERNAL_URL production
vercel env add BACKEND_API_TOKEN production
vercel env add APP_API_TOKEN production
vercel env add SESSION_SECRET production
vercel --prod
```

Full explanation of every step (including the worker's manual start-command
override, `ALLOWED_ORIGINS` wiring, and post-deploy verification) is in
`docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md`.

## License / disclaimer

Personal-use project. Nothing here is financial advice; signals are the
output of a documented, reproducible rule-based strategy, not a prediction.
