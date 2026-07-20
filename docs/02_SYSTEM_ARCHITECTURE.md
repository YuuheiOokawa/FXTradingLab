# 02. System Architecture

## High-level diagram

```
┌────────────────────┐        WebSocket/SSE        ┌──────────────────────────────┐
│   Next.js Frontend  │◄────────────────────────────┤   FastAPI Backend             │
│  (Vercel / Docker)  │────────────HTTPS────────────►│  (Railway / Docker, always-on)│
└────────────────────┘        REST (JSON)            │                                │
                                                       │  ┌─────────────────────────┐ │
                                                       │  │ API layer (routers)      │ │
                                                       │  ├─────────────────────────┤ │
                                                       │  │ Signal Engine            │ │
                                                       │  │ Regime Classifier        │ │
                                                       │  │ Backtest Engine          │ │
                                                       │  │ Risk Engine              │ │
                                                       │  │ Paper Trading Engine     │ │
                                                       │  │ Order Orchestrator       │ │
                                                       │  ├─────────────────────────┤ │
                                                       │  │ BrokerAdapter interface  │ │
                                                       │  │  ├─ MockAdapter          │ │
                                                       │  │  └─ OandaAdapter         │ │
                                                       │  ├─────────────────────────┤ │
                                                       │  │ MarketDataService        │ │
                                                       │  │  (poll/stream → candles) │ │
                                                       │  └─────────────────────────┘ │
                                                       └───────────┬──────────────────┘
                                                                   │
                                                    ┌──────────────┼──────────────┐
                                                    ▼                              ▼
                                          ┌────────────────┐             ┌────────────────┐
                                          │  PostgreSQL     │             │  Redis          │
                                          │  (durable data) │             │ (pub/sub, cache,│
                                          │                  │             │  rate limiting) │
                                          └────────────────┘             └────────────────┘
                                                                                   ▲
                                                                          ┌────────┴────────┐
                                                                          │ Background worker│
                                                                          │ (APScheduler)    │
                                                                          │ - price polling  │
                                                                          │ - candle rollup  │
                                                                          │ - tick retention │
                                                                          └──────────────────┘
```

## Process model

- **API process** (`uvicorn app.main:app`) — serves REST + WebSocket. Stateless except
  for in-memory price cache (source of truth is Postgres/Redis).
- **Worker process** (`python -m app.worker`) — runs the market data poller
  (`MarketDataService`), candle aggregation, tick retention/cleanup, and (when
  FULL_AUTO is enabled) the signal→order evaluation loop. Separated from the API
  process so a slow backtest request never blocks price polling, and so the worker can
  be scaled/restarted independently.
- Both processes share the same codebase (`backend/app`) and the same DB/Redis.
- In local Docker Compose, both run as separate services from the same image with
  different entrypoints.

## Real-time data flow

1. Worker polls (or streams, if the adapter supports it) prices from `BrokerAdapter`
   every N seconds per instrument (configurable, default 2s for REST-polling adapters).
2. Each tick is: (a) published to Redis pub/sub channel `ticks:{instrument}`, (b)
   used to update the in-progress candle for every timeframe, (c) written to the
   `market_ticks` table only at a down-sampled rate (see `07_REALTIME_DATA_DESIGN.md`).
3. The API process's WebSocket endpoint subscribes to the relevant Redis channels per
   connected client and forwards ticks/candle-closes to the browser.
4. The frontend updates chart series and dashboard tiles incrementally (no page
   reload, no full-list refetch) using `lightweight-charts`' `update()` API and
   local React state merges.

## Why a separate worker instead of doing everything in request handlers

FastAPI request handlers are demand-driven; market monitoring must run continuously
regardless of whether a browser tab is open. A dedicated worker loop (APScheduler-based
in v1; swappable for Celery+Redis if/when multi-instance scaling is needed) is the
simplest correct model for a single-operator deployment.

## BrokerAdapter boundary

All broker-specific code lives behind `app/brokers/base.py::BrokerAdapter`. Nothing
outside `app/brokers/` may import a broker SDK or construct broker-specific request
payloads. This is what makes the OANDA-vs-alternative decision (`06_BROKER_API_DESIGN.md`)
reversible later without touching Signal Engine, Backtest Engine, or the frontend.

## Deployment topology (initial)

- Frontend → Vercel.
- Backend API + Worker → Railway (two services from one Docker image, always-on).
- PostgreSQL → Railway managed Postgres (or Supabase/Neon).
- Redis → Railway managed Redis.

See `12_DEPLOYMENT.md` for the full comparison and rationale.
