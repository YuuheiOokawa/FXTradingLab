# 12. Deployment

## Backend hosting comparison

| | Railway | Render | Fly.io | Cloud Run | ECS/Fargate | EC2 |
|---|---|---|---|---|---|---|
| Always-on process (worker) | Yes | Yes (paid) | Yes | No¹ | Yes | Yes |
| WebSocket support | Yes | Yes | Yes | Yes | Yes | Yes |
| Managed Postgres | Yes | Yes | Yes (via Fly Postgres) | No (needs Cloud SQL) | No (needs RDS) | No (self-managed) |
| Managed Redis | Yes | Yes | Yes (Upstash addon) | No | No | No |
| Docker-native | Yes | Yes | Yes | Yes | Yes | Yes |
| Pricing model | Usage-based, $5/mo Hobby minimum | Flat per-service | Usage-based | Pay-per-request | Pay-per-task | Pay-per-instance |
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

**Verified against Railway's current (2026) official docs** (`docs.railway.com` —
the primary domain moved from `railway.app`; `*.up.railway.app` still exists only
for auto-generated service subdomains):
- Services run continuously with no free-tier "sleep" — confirmed suitable for the
  always-on worker.
- Deploying multiple services (`api`, `worker`) from one GitHub repo, each with its
  own root directory/start command and shared project-level env vars, is an
  explicitly supported, documented pattern (not a workaround).
- WebSocket connections are exempt from Railway's proxy inactivity/request
  timeouts — no special config needed beyond a normal HTTP/1.1 upgrade.
- Postgres/Redis are still first-class one-click template services, billed as
  regular Railway services under the same usage-based CPU/RAM/storage/egress
  pricing — no separate "managed database" price tier.

Sources: [Railway pricing plans](https://docs.railway.com/pricing/plans),
[monorepo/multi-service docs](https://docs.railway.com/deployments/monorepo),
[Socket.IO/WebSocket guide](https://docs.railway.com/guides/socketio),
[Redis template docs](https://docs.railway.com/databases/redis).

## Frontend hosting

**Vercel** for the Next.js frontend — first-class Next.js support, generous free
tier, trivial preview deployments. Vercel Serverless Functions are *not* used for
anything requiring long-lived connections; the frontend is a pure client of the
Railway-hosted backend for REST and WebSocket.

Verified current (2026) Hobby-tier limits: 100GB bandwidth/mo, 1M edge requests/mo,
personal/non-commercial use only, and — unlike Railway — no overage purchase option
(a deployment pauses until the next billing cycle if a hard cap is hit rather than
metering further usage). Source: [Vercel Hobby plan docs](https://vercel.com/docs/plans/hobby),
[Vercel Functions limits](https://vercel.com/docs/functions/limitations).

## Why not "everything on Vercel"

Vercel's serverless functions are request-scoped and cannot run the continuous market
data poller, hold long-lived WebSocket fan-out state, or run multi-minute backtests
reliably — exactly the workloads this app needs always-on. Vercel Edge/Serverless is
excellent for the frontend and would be a poor fit for the backend worker, hence the
split topology.

**2026 update, re-verified for this review**: Vercel shipped native WebSocket
support in public beta on June 22, 2026 (built on Fluid Compute). This does **not**
change the recommendation above — it's scoped to serving WebSocket connections from
within a Function's duration budget (5-minute default, a 30-minute beta ceiling on
Pro/Enterprise only), connections are pinned to one function instance for that
duration, and there is still no general "always-on background process" product on
Vercel. A continuous price-polling worker that must run indefinitely and fan out to
every connected client still belongs on Railway. Sources:
[Vercel WebSocket beta changelog](https://vercel.com/changelog/websocket-support-is-now-in-public-beta),
[Vercel Functions WebSockets docs](https://vercel.com/docs/functions/websockets).

## Two proposed configurations

### Initial personal operation
```
Frontend  → Vercel (Next.js, free/hobby tier)
Backend   → Railway: 2 services (api, worker) from one Docker image, hobby/starter plan
Database  → Railway managed Postgres
Cache     → Railway managed Redis
```
Cost: Vercel Hobby is free (personal use). Railway Hobby is a $5/mo minimum that
includes $5 of usage credit, then meters overage per-second (roughly
$0.000463/vCPU-min, $0.014/GB-hour RAM, $0.25/GB-month storage, $0.10/GB egress as
of this writing — verify current rates at
[docs.railway.com/pricing](https://docs.railway.com/pricing) before budgeting,
since these are metered rates that change independently of the plan price). Running
2 backend services + Postgres + Redis continuously will likely exceed the included
$5 credit for this app's workload — budget roughly $10-20/mo total as a realistic
starting estimate, not $5/mo flat. No infra to patch/manage either way.

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
