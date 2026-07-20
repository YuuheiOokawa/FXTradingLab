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
- No broker API secret is ever sent to the browser — all broker communication
  happens server-side only.

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

See `docs/12_DEPLOYMENT.md` for the full comparison. Short version: Vercel for
the frontend, Railway (or Render/Fly) for the backend (API + worker as two
always-on services from one Docker image, needed because the market-data
poller and WebSocket fan-out can't run on Vercel's serverless functions),
managed Postgres + Redis.

## License / disclaimer

Personal-use project. Nothing here is financial advice; signals are the
output of a documented, reproducible rule-based strategy, not a prediction.
