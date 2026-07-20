# 17. Production Deployment Guide

Concrete, copy-pasteable steps for a first personal deployment. This
environment has no cloud account credentials, so no deploy was executed from
here — this is the exact procedure to run yourself once you have accounts on
the target platforms. See `docs/12_DEPLOYMENT.md` for the platform comparison
and rationale; this doc is the "now actually do it" companion.

## Prerequisites

- A GitHub repo containing this project (push this branch to your own repo or
  fork if you haven't already).
- Accounts on: [Vercel](https://vercel.com), [Railway](https://railway.com)
  (Railway's primary domain moved from `railway.app` to `railway.com` — the
  `.up.railway.app` domain format still exists but only for
  auto-generated per-service subdomains), and (optionally, once you're ready
  to test against a real broker) [OANDA](https://www.oanda.jp) or
  [GMO Coin](https://coin.z.com/jp/).
- A generated secret for `APP_API_TOKEN`, e.g.:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

## Expected cost

Verified against each platform's current official pricing docs (2026):

- **Vercel**: free on the Hobby tier for personal/non-commercial use — 100GB
  bandwidth/mo and 1M edge requests/mo, which this app's traffic won't come
  close to. Hobby has no overage purchase option (a deployment pauses until
  the next billing cycle if a hard cap is ever hit, rather than metering
  further usage) — not a practical concern at personal scale, but know it's
  there. [Hobby plan docs](https://vercel.com/docs/plans/hobby).
- **Railway**: usage-based on top of a plan minimum, not flat pricing. Hobby
  is $5/mo and includes $5 of usage credit (you're billed the $5 minimum even
  if you use less; usage above $5 is metered per-second). Running this app's
  4 Railway services continuously (api, worker, Postgres, Redis) will likely
  exceed the included $5 credit — budget roughly **$10-20/mo** as a realistic
  starting estimate, not $5/mo flat. Exact metered rates (CPU/RAM/storage/
  egress) are published and change independently of the plan price — check
  [docs.railway.com/pricing](https://docs.railway.com/pricing) before
  budgeting precisely, don't rely on this doc's memory of them.

## Architecture fit re-verified (2026)

Re-confirmed directly against each platform's current docs before writing this
guide, since platform capabilities and pricing models change over time:

- Railway services run continuously with no free-tier "sleep" — confirmed
  suitable for the always-on worker process this app needs.
- Deploying two services (`api`, `worker`) from one GitHub repo, each with its
  own root directory and start command, sharing project-level environment
  variables, is an explicitly documented and supported Railway pattern (not a
  workaround) — see [monorepo docs](https://docs.railway.com/deployments/monorepo).
- Railway's proxy exempts WebSocket connections from its normal inactivity/
  request timeouts — no special configuration needed beyond the standard
  HTTP/1.1 upgrade this app already does.
- Vercel shipped native WebSocket support in public beta in June 2026, but it
  remains duration-capped (5-minute default, 30-minute beta ceiling on
  Pro/Enterprise only) and connections pin to a single function instance —
  it is not a substitute for an always-on background worker. This app's
  continuous price-polling/WebSocket-fan-out process stays on Railway; Vercel
  is frontend-only in this deployment. See
  [Vercel WebSocket beta changelog](https://vercel.com/changelog/websocket-support-is-now-in-public-beta).

## 1. Database + Redis (Railway)

1. Create a new Railway project.
2. Add a **PostgreSQL** service (Railway's "New" → "Database" → "PostgreSQL")
   and a **Redis** service the same way. Railway generates connection strings
   automatically as service-linked environment variables
   (`DATABASE_URL`-shaped for Postgres — confirm the exact variable name in
   the Railway dashboard's "Variables" tab for that service, since Railway
   exposes it as e.g. `DATABASE_URL` or `POSTGRES_URL` depending on template
   version).
3. Note: our app expects an `asyncpg`-style URL —
   `postgresql+asyncpg://user:pass@host:port/db` — Railway's generated URL is
   plain `postgresql://...`; add the `+asyncpg` driver segment yourself when
   setting the backend's `DATABASE_URL` variable (or set it via Railway's
   variable reference syntax, e.g. `postgresql+asyncpg://${{Postgres.PGUSER}}:...`).

## 2. Backend API + Worker (Railway)

Two services from the **same** GitHub repo, both with **Root Directory** set
to `backend`:

### Service "api"
1. New service → Deploy from GitHub repo → root directory `backend`.
2. Railway auto-detects the `Dockerfile`. Confirm build settings pick it up
   (Settings → Build → Builder = Dockerfile).
3. Environment variables (Settings → Variables) — copy every key from
   `.env.example`, filling in real values:
   ```
   APP_ENV=production
   APP_API_TOKEN=<the token you generated above>
   ALLOWED_ORIGINS=https://<your-vercel-domain>
   DATABASE_URL=<from step 1, with +asyncpg>
   REDIS_URL=<from step 1>
   BROKER_PROVIDER=mock            # start here; switch once you've verified the deploy
   LIVE_TRADING_ENABLED=false      # never set true on first deploy
   LOG_FORMAT=json
   ```
4. `backend/railway.toml` already sets the start command
   (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`) and healthcheck
   (`/health`) — no manual override needed for this service.
5. Deploy. Confirm `https://<api-domain>/health` and
   `https://<api-domain>/ready` both return 200.

### Service "worker"
1. New service → same GitHub repo → root directory `backend` again.
2. **Manually override the Start Command** (Settings → Deploy → Start
   Command): `python -m app.worker.main` — this is the one step Railway
   doesn't support declaring twice from a single `railway.toml`
   (`backend/railway.toml` documents this at the top of the file).
3. Same environment variables as the "api" service (copy them over, or use
   Railway's shared/project-level variables so both services stay in sync).
4. No healthcheck path applies (it's not an HTTP service) — use Railway's
   process-restart-on-crash default instead.
5. Deploy. Check the worker's logs for `worker starting: market_data_provider=...`
   and confirm no repeated `BrokerConnectionError` lines.

### Run the initial migration

Either add a one-off **Migrate** service (mirroring
`docker-compose.yml`'s `migrate` service: same image, command
`alembic upgrade head`, no restart policy needed since it's one-shot), or run
it manually via Railway's shell:
```bash
railway run --service api alembic upgrade head
```

## 3. Frontend (Vercel)

1. Import the GitHub repo into Vercel; set **Root Directory** to `frontend`
   in the project's General settings (Vercel auto-detects Next.js once the
   root directory is correct).
2. Environment variables (Project Settings → Environment Variables):
   ```
   NEXT_PUBLIC_API_URL=https://<your-railway-api-domain>
   NEXT_PUBLIC_APP_API_TOKEN=<same token as APP_API_TOKEN above>
   ```
3. Deploy. Once live, go back to the Railway "api" service and set
   `ALLOWED_ORIGINS` to the real `https://<project>.vercel.app` domain (or
   your custom domain once attached) — the app is designed to fail closed
   (block all cross-origin requests) until this is set correctly in any
   non-development environment, so the frontend won't be able to reach the
   API until this matches.

### Optional: deploy via GitHub Actions instead of the CLI

`.github/workflows/deploy.yml` is a prepared, manual-trigger deploy workflow
(`workflow_dispatch` only — it never fires automatically on push or merge).
Once you've done steps 1-3 above manually the first time (so the Railway
services and Vercel project exist), you can re-deploy either side later via
the Actions tab → "Deploy (manual)" → "Run workflow" instead of the CLI
commands above. Requires four repo secrets first: `RAILWAY_TOKEN`,
`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` — see the comment at the
top of that workflow file for where to get each one. Consider adding required
reviewers to the `production` GitHub Environment (Settings → Environments) for
a second confirmation step before any deploy runs.

## 4. Verify the deployment

1. Visit the Vercel URL — you should land on `/login` (since
   `NEXT_PUBLIC_APP_API_TOKEN` is set); log in with the token.
2. Dashboard should show live-updating prices for the default watchlist
   within a few seconds (confirms worker → Redis → WebSocket → frontend path).
3. Run a small backtest, submit a paper order, hit the Kill Switch and
   deactivate it again — confirms the full API surface and DB writes work.
4. Check `https://<api-domain>/ready` periodically (or wire it into an
   uptime monitor — see "Monitoring" below).

## 5. Connecting a real broker (optional, when ready)

Still `BROKER_ENVIRONMENT=practice` / `OANDA_ENVIRONMENT=practice` at this
stage — see `docs/06_BROKER_API_DESIGN.md` and `docs/16_BROKER_SELECTION_REVIEW.md`
for how to actually obtain OANDA/GMO Coin credentials. Set on the **api** and
**worker** Railway services identically:
```
BROKER_PROVIDER=oanda
OANDA_API_TOKEN=...
OANDA_ACCOUNT_ID=...
OANDA_ENVIRONMENT=practice
```
Redeploy both services (env var changes require a restart). LIVE trading
stays gated regardless — see `docs/10_RISK_MANAGEMENT.md`; do not set
`LIVE_TRADING_ENABLED=true` until you've deliberately decided to and
understand every one of the three required gates.

## Database backup / restore / retention

Railway's managed Postgres includes automated backups on paid plans — check
the current retention window in your Railway project's Postgres service
settings (Settings → Backups), since exact retention periods are a
plan-dependent detail that changes over time; don't rely on this doc's
memory of it. Independent of that, take your own backups periodically:

**Manual backup:**
```bash
# Get the connection string from Railway's Postgres service "Connect" tab.
pg_dump "postgresql://user:pass@host:port/railway" \
  --format=custom --file="fxlab-backup-$(date +%Y%m%d).dump"
```

**Restore (into a fresh database — never restore over a live one without a
separate backup of the current state first):**
```bash
pg_restore --clean --if-exists --no-owner \
  --dbname="postgresql://user:pass@host:port/railway" \
  fxlab-backup-YYYYMMDD.dump
```

**Retention policy for this app specifically**: trade history
(`trade_journals`, `paper_positions`, `backtest_trades`, etc.) should be kept
indefinitely — it's the record of everything the app has done. Only
`market_ticks` and old `M1` candles are intentionally pruned automatically
(`TICK_RETENTION_DAYS`, `CANDLE_1M_RETENTION_DAYS` — see
`docs/04_DATABASE_DESIGN.md`); back up before ever manually truncating
anything else.

**Suggested cadence for a personal deployment**: a weekly manual `pg_dump`
downloaded locally is enough at this scale (a personal trading journal, not a
high-volume production system) — set a calendar reminder, or automate it with
a scheduled GitHub Action that runs `pg_dump` and uploads the artifact
somewhere you control.

## Rollback

- **Bad deploy (code)**: Railway and Vercel both keep prior deployments —
  use each platform's dashboard "Rollback to previous deployment" action.
  This reverts code only; it does not revert a database migration.
- **Bad migration**: `alembic downgrade -1` reverts the most recent migration
  (run via `railway run --service api alembic downgrade -1`, or locally
  against the production `DATABASE_URL` if you're comfortable doing so
  directly — prefer running it through Railway so it uses the same network
  path/credentials the app does). Every migration in `backend/alembic/versions/`
  has a corresponding `downgrade()`; verify it against a copy of production
  data before relying on it under pressure.
- **Bad config (env var)**: revert the variable in the platform dashboard and
  redeploy — both platforms redeploy automatically on variable changes to the
  active deployment in most configurations; confirm in each platform's
  current UI since this occasionally changes.

## Monitoring

At minimum, point an external uptime monitor (e.g. a free tier of
UptimeRobot, Better Uptime, or similar — pick one you're already comfortable
with) at `https://<api-domain>/ready` and `https://<frontend-domain>/login`.
`/ready` returning non-200 means DB or Redis is down; a worker that's stopped
polling won't fail `/ready` (DB/Redis can be fine while the worker is dead) —
also monitor `https://<api-domain>/metrics` for a per-instrument
`last_tick_ts` that stops advancing, which is the actual signal that the
worker died.

## Secrets checklist before going live

- [ ] `APP_API_TOKEN` set to a real generated secret (not the placeholder)
- [ ] `ALLOWED_ORIGINS` set to your actual frontend domain (not blank, not `*`)
- [ ] `NEXT_PUBLIC_APP_API_TOKEN` matches `APP_API_TOKEN` exactly
- [ ] `LIVE_TRADING_ENABLED=false` (confirm explicitly — don't assume the
      platform default matches this app's default)
- [ ] No `.env` file committed to the repo (`git status` clean, `.gitignore`
      covers it — verified already in this repo, re-verify in your fork)
- [ ] Broker credentials (if configured) are Railway environment variables,
      never in code or committed config
