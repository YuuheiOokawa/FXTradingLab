# 12. Deployment

## Backend hosting comparison

| | Railway | Render | Fly.io | Cloud Run | ECS/Fargate | EC2 |
|---|---|---|---|---|---|---|
| Always-on process (worker) | Yes | Yes (paid) | Yes | No¹ | Yes | Yes |
| WebSocket support | Yes | Yes | Yes | Yes | Yes | Yes |
| Managed Postgres | Yes | Yes | Yes (via Fly Postgres) | No (needs Cloud SQL) | No (needs RDS) | No (self-managed) |
| Managed Redis | Yes | Yes | Yes (Upstash addon) | No | No | No |
| Docker-native | Yes | Yes | Yes | Yes | Yes | Yes |
| Pricing model | Usage-based, generous hobby tier | Flat per-service | Usage-based | Pay-per-request | Pay-per-task | Pay-per-instance |
| Solo-dev ops burden | Very low | Low | Low-medium (fly.toml, regions) | Medium (needs Cloud SQL/Memorystore wiring) | High (VPC, ALB, task defs) | Highest (full OS mgmt) |
| Logs/observability | Built-in | Built-in | Built-in | Cloud Logging | CloudWatch | Self-set-up |

¹ Cloud Run scales to zero by default; an always-on background worker needs a
minimum-instance setting (extra cost) or a separate always-on Compute Engine/GKE
job — awkward fit for "continuously poll FX prices."

**Decision:** Railway for backend (API + worker as two services from one image) +
managed Postgres + managed Redis. It's the only option here that gives an always-on
process, WebSockets, managed Postgres, and managed Redis with near-zero ops
configuration — the right trade for a solo-developer personal project. Render is the
credible runner-up if Railway pricing/availability ever becomes an issue (same
capability shape).

## Frontend hosting

**Vercel** for the Next.js frontend — first-class Next.js support, generous free
tier, trivial preview deployments. Vercel Serverless Functions are *not* used for
anything requiring long-lived connections; the frontend is a pure client of the
Railway-hosted backend for REST and WebSocket.

## Why not "everything on Vercel"

Vercel's serverless functions are request-scoped and cannot run the continuous market
data poller, hold long-lived WebSocket fan-out state, or run multi-minute backtests
reliably — exactly the workloads this app needs always-on. Vercel Edge/Serverless is
excellent for the frontend and would be a poor fit for the backend worker, hence the
split topology.

## Two proposed configurations

### Initial personal operation
```
Frontend  → Vercel (Next.js, free/hobby tier)
Backend   → Railway: 2 services (api, worker) from one Docker image, hobby/starter plan
Database  → Railway managed Postgres
Cache     → Railway managed Redis
```
Cost: roughly $0-15/mo depending on usage tier; no infra to patch/manage.

### Future full-scale operation
```
Frontend  → Vercel Pro (better analytics/limits)
Backend   → Fly.io or ECS/Fargate, multiple regions/instances, Celery+Redis replacing
            APScheduler for horizontal worker scaling
Database  → Managed Postgres with read replica (Railway Pro / RDS / Cloud SQL)
Cache     → Managed Redis cluster
Observability → Structured logging + Sentry + uptime checks
```

## Environments

`development` (local Docker Compose), `staging`, `production` — each with its own
`.env`, its own `DATABASE_URL`, and its own `BROKER_ENVIRONMENT` (`practice`/`live`)
setting that is **never derived from `APP_ENV`**. A `production` deploy defaults to
`BROKER_ENVIRONMENT=practice` and `LIVE_TRADING_ENABLED=false` exactly like every
other environment; switching either requires an explicit, separate operator action
(see `10_RISK_MANAGEMENT.md`).

## Docker

`docker-compose.yml` at repo root runs `frontend`, `backend` (api), `worker`,
`postgres`, `redis` for local development, matching the two-process backend split
used in the Railway deployment.
