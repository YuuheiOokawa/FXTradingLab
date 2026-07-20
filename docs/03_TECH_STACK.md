# 03. Tech Stack

## Decision summary

| Layer | Choice | Why |
|---|---|---|
| Frontend framework | Next.js 14 (App Router) + TypeScript | SSR/streaming for dashboard, good Vercel fit, huge ecosystem |
| Styling | Tailwind CSS + shadcn/ui | Fast, consistent dark-theme trading UI without a heavy design system |
| Charts | `lightweight-charts` (TradingView) | Purpose-built for candlesticks + overlays, handles high-frequency updates cheaply, free/OSS |
| State/data | TanStack Query (REST) + native WebSocket hook | Query for request/cache, WS for live ticks — avoids reinventing caching |
| Backend framework | Python 3.12 + FastAPI | Async I/O for streaming/WebSocket, first-class typing (Pydantic), great for numerics (pandas/numpy for indicators/backtest) |
| ORM | SQLAlchemy 2.0 (async) + Alembic | More mature for complex analytical queries and raw-SQL escape hatches than Prisma's Python story (which doesn't really exist — Prisma is JS/TS-first); SQLAlchemy is the standard pairing with FastAPI |
| Database | PostgreSQL 16 | Relational integrity for orders/positions/journal, window functions for analytics, TimescaleDB-compatible if tick volume grows |
| Cache/pubsub | Redis 7 | Live-tick pub/sub to WebSocket clients, rate limiting, background job locking |
| Background jobs | APScheduler (in-process worker) | Simple, no extra infra for a single-operator app; interface kept swappable for Celery+Redis if multi-instance scaling is ever needed |
| Numerics | pandas + numpy | Indicator math, backtest vectorization |
| Testing (backend) | pytest, pytest-asyncio, httpx | Standard, async-friendly |
| Testing (frontend) | Vitest + React Testing Library, Playwright (smoke) | Fast unit tests + real browser smoke test for chart/WebSocket |
| Containerization | Docker + docker-compose | Local parity, easy Railway/Fly deploy |

## Why not Prisma

Prisma's Python client is unofficial/community and lags the JS client badly; since the
backend is Python/FastAPI (chosen for async streaming + numerics), SQLAlchemy 2.0 async
+ Alembic is the standard, well-supported choice. Prisma remains a fine choice *if* the
backend were Node/TypeScript instead — it wasn't, for the reasons in the numerics row.

## Why not Celery in v1

Celery+Redis is the right answer once this needs multiple worker instances or
scheduled tasks with retries/observability at scale. For a single-operator app with one
worker process, APScheduler avoids running a broker + result backend for jobs that are,
today, just "poll prices every 2s" and "roll up candles every minute." The worker's
internal job interface (`app/worker/jobs/*.py`) is deliberately Celery-shaped
(`run(ctx)` functions with no APScheduler-specific state) so migrating is a
swap of the scheduler, not a rewrite of job logic.

## Why lightweight-charts over Recharts/Chart.js/D3

Candlestick + volume + multiple overlay panes (RSI/MACD) with tens of thousands of
points and live incremental updates is exactly what `lightweight-charts` was built for
(it's what TradingView itself ships for embeddable charts). Generic charting libraries
either can't handle the update volume smoothly or require building candlestick
rendering from scratch.
