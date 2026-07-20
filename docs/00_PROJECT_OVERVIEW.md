# 00. Project Overview — FX Trading Lab

## What this is

FX Trading Lab is a personal-use web application for real-time FX market monitoring,
technical analysis, trade simulation, backtesting, and (eventually, behind hard safety
gates) live order execution. It is built to be genuinely useful, not a demo: real market
data, real technical analysis, a real backtest engine, and a real (but disabled-by-default)
path to live trading.

The core design principle is **explainability**: every BUY/SELL signal shown to the user
comes with a numeric score (0-100) and a human-readable breakdown of which conditions were
met, partially met, or failed. The app never claims to predict the future — it only reports
what a defined, reproducible rule-based strategy currently says.

## Staged rollout model

The app is architected so a user can move through increasing levels of real-money risk
without re-architecting anything:

1. **BACKTEST** — strategy validation against historical candles.
2. **PAPER_LIVE** (real-time paper trading) — real market prices, virtual money.
3. **DEMO** — broker demo/practice account, real order-matching semantics, no real money.
4. **LIVE (small size)** — real broker account, hard risk caps.
5. **LIVE (full operation)** — same code path as (4), larger risk limits, opt-in only.

Modes 1-3 are safe by construction (no path to a real broker order). Mode 4/5 both go
through the same `LIVE` code path, which is disabled by default and requires three
independent conditions to be true simultaneously (see `10_RISK_MANAGEMENT.md`).

## Non-goals (v1)

- Multi-user SaaS / multi-tenant auth (this is a single-operator personal tool; a `users`
  table exists for future-proofing but the app runs single-user).
- Fully autonomous "black box" AI trading. AI is explanation/analysis only — see
  `08_SIGNAL_ENGINE.md`.
- Order execution on exchanges other than the configured `BrokerAdapter`.
- Guaranteeing profitability. This is a research/monitoring/execution tool, not a signal
  service.

## Repository layout

```
FXTradingLab/
├── docs/               # this design documentation (00-14)
├── backend/            # FastAPI application (Python)
├── frontend/           # Next.js application (TypeScript)
├── docker-compose.yml  # local dev: frontend + backend + postgres + redis
└── README.md
```

See `14_IMPLEMENTATION_PLAN.md` for phase-by-phase status of what is implemented today
versus what is designed-but-not-yet-built.
