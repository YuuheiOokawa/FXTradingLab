# 14. Implementation Plan & Status

Phases as specified in the project brief, with honest status. This file is the
source of truth for "what actually works today" vs "designed but not yet built" —
keep it updated as work lands.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project init, DB schema, base UI shell, BrokerAdapter abstraction | ✅ Implemented |
| 2 | Real market price polling, realtime chart, candle aggregation | ✅ Implemented |
| 3 | Technical indicators, Signal Engine, regime classification, MTF analysis | ✅ Implemented |
| 4 | What-if trade simulator, Replay mode | ✅ Implemented (backend + UI) |
| 5 | Backtest engine, backtest analytics/UI | ✅ Implemented |
| 6 | Paper trading (virtual ¥1,000,000 account) | ✅ Implemented |
| 7 | Demo broker connectivity | ✅ via `OandaAdapter` against `practice` environment; `GmoCoinAdapter` left as a documented stub (see `06_BROKER_API_DESIGN.md`) |
| 8 | Risk Engine, Order Orchestrator, Kill Switch | ✅ Implemented |
| 9 | Production deployment configs | ✅ Dockerfiles, docker-compose, Railway/Vercel config committed; actual cloud deploy not performed from this environment (no cloud credentials available here) — see `12_DEPLOYMENT.md` for the exact steps to deploy |
| 10 | Live trading | ⚠️ Scaffolded and gated OFF by default (`LIVE_TRADING_ENABLED=false`); `POST /live/orders` route and UI exist but real order submission is intentionally blocked pending the three-condition gate in `10_RISK_MANAGEMENT.md` |

## Known gaps / next steps (tracked honestly, not hidden)

- `GmoCoinAdapter` (the recommended real path to an actual Japan-resident live
  account per `06_BROKER_API_DESIGN.md`) is a stub — implementing it fully requires
  a funded GMO Coin account to test against, which this environment doesn't have.
- AI explanation endpoints (`08_SIGNAL_ENGINE.md`) work with a templated fallback;
  wiring a real LLM provider requires `AI_API_KEY` to be supplied by the operator.
- Discord/LINE/email notification channels are interface-ready
  (`app/services/notifications/channel.py`) but only `in_app` has a concrete
  implementation in v1.
- Walk-Forward Analysis is designed as an extension of the backtest engine's
  `run_range()` primitive but not implemented as a UI-facing feature yet.
- No automated cloud deployment was executed as part of this build — Docker images
  and IaC-adjacent config (Railway/Vercel project files) are provided; an operator
  with cloud accounts must run the actual `railway up` / `vercel deploy` and set
  environment variables per `.env.example`.

## How to pick this back up

1. `docker compose up` — brings up Postgres, Redis, backend API, worker, frontend.
2. With zero env vars set, everything works against `MockAdapter` (synthetic but
   realistic price action) — confirm the dashboard, chart, signals, backtest, replay,
   and paper trading all function before touching real credentials.
3. To test against real OANDA practice data: set `BROKER_PROVIDER=oanda`,
   `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `OANDA_ENVIRONMENT=practice` in `.env`.
4. Live trading stays off until an operator deliberately completes all three gates
   in `10_RISK_MANAGEMENT.md` — do not attempt to bypass this from code.
