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
3. **Check the Config-as-Code file path for this service** (Settings →
   Config-as-Code). Since both services share the same `backend` root
   directory, this service may auto-discover `backend/railway.toml` the
   same way the "api" service intentionally does — and that file's
   `[deploy]` block (`startCommand`, `healthcheckPath`) is documented by
   Railway to take precedence over dashboard settings when a config file
   applies. Unverified from this sandbox exactly how Railway resolves this
   for a second same-root-directory service specifically (Railway's own
   docs were unreachable to confirm precisely during this review) — **treat
   step 5's log check below as the actual verification**, not this
   paragraph's reasoning. If the worker's logs show `uvicorn` output
   instead of `worker starting: ...`, the file-based Start Command won.
   Fix by clearing/disabling this service's Config-as-Code file path so it
   falls back to the dashboard-only Start Command from step 2.
4. Same environment variables as the "api" service (copy them over, or use
   Railway's shared/project-level variables so both services stay in sync).
5. No healthcheck path applies (it's not an HTTP service) — use Railway's
   process-restart-on-crash default instead. If step 3's concern turns out
   to apply, this service could otherwise inherit the api service's
   `healthcheckPath = "/health"`, which the worker can never satisfy (it
   serves no HTTP endpoint at all) — Railway would then likely mark every
   worker deployment unhealthy. This is exactly what to look for if the
   worker service shows deployments failing/restarting in a loop despite
   the process itself logging cleanly.
6. Deploy. **Check the worker's logs for `worker starting:
   market_data_provider=...`** (not `Uvicorn running on...`) and confirm no
   repeated `BrokerConnectionError` lines — this log line is the actual
   proof the Start Command override took effect, independent of whichever
   way step 3 resolves.

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
2. Environment variables (Project Settings → Environment Variables) — see
   `docs/11_SECURITY.md` "BFF migration" for what each of these is actually
   for; **Environment** column matters (below) since these must differ
   between Vercel's Production and Preview environments:
   ```
   NEXT_PUBLIC_WS_URL=wss://<your-railway-api-domain>
   BACKEND_INTERNAL_URL=https://<your-railway-api-domain>
   BACKEND_API_TOKEN=<same token as the backend's APP_API_TOKEN>
   APP_API_TOKEN=<the /login password — same value as above for the simplest setup>
   SESSION_SECRET=<a second generated secret, e.g. the same python3 -c "..." command from Prerequisites>
   ```
   Set all five to Vercel's **Production** environment only, scoped to the
   Production deployment — do NOT also enable them for Preview
   deployments. See "Locking down Preview deployments" below for why: a
   Preview deploy that could reach the real production backend (or, if
   using Railway private networking, one that can't reach it at all and
   fails confusingly) is exactly the kind of gap `docs/15_PRODUCTION_
   READINESS_REVIEW.md`'s BFF-migration pass was checking for.

   `BACKEND_INTERNAL_URL` may instead point at a Railway **private
   networking** hostname (`<service>.railway.internal`) rather than the
   public `*.up.railway.app` domain, if the Vercel deployment reaches
   Railway over a mechanism that supports it (e.g. a Railway-hosted proxy,
   or if you later move the frontend itself onto Railway) — this is
   strictly better when available, since it means the backend never needs a
   publicly routable HTTP listener for REST at all, only for the WebSocket
   the browser still connects to directly. Vercel serverless functions
   reaching a Railway private-network hostname directly is not supported as
   of this writing (they run outside Railway's network) — verify current
   Railway/Vercel networking docs before assuming otherwise; the public
   Railway domain is the default, working path from Vercel today.
3. Deploy. Once live, go back to the Railway "api" service and set
   `ALLOWED_ORIGINS` to the real `https://<project>.vercel.app` domain (or
   your custom domain once attached) — the app is designed to fail closed
   (block all cross-origin requests) until this is set correctly in any
   non-development environment. This now matters specifically for the
   WebSocket handshake's Origin check (`app/ws/auth.py`), since REST no
   longer crosses origins at all (the browser only ever calls the Vercel
   deployment's own `/api/backend/*`).

### Locking down Preview deployments

Vercel creates a Preview deployment for every branch/PR by default, each
getting its own auto-generated URL. If that Preview deployment's environment
variables point at the real production `BACKEND_INTERNAL_URL`/
`BACKEND_API_TOKEN`, a Preview URL — often unauthenticated in front-end
terms until this app's own `/login` gate, and sometimes shared casually for
review — would have full BFF-proxied access to the production backend. Set
Preview-scoped copies of the five variables above pointing at a **staging**
backend instead (see `docs/15_PRODUCTION_READINESS_REVIEW.md` "Staging
environment separation"), or leave them unset entirely for Preview so a
Preview build fails closed (the BFF proxy returns 502s, per `route.ts`'s
`BACKEND_UNREACHABLE` handling) rather than silently reaching production.

### Optional: deploy via GitHub Actions instead of the CLI

`.github/workflows/deploy.yml` is a prepared, manual-trigger deploy workflow
(`workflow_dispatch` only — it never fires automatically on push or merge).
Once you've done steps 1-3 above manually the first time (so the Railway
services and Vercel project exist), you can re-deploy either side later via
the Actions tab → "Deploy (manual)" → "Run workflow" instead of the CLI
commands above — it now asks for **both** which environment (`staging` or
`production`, no default — see "6. Staging environment" below) and what to
deploy. Requires four repo secrets per GitHub Environment first:
`RAILWAY_TOKEN`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` — see
the comment at the top of that workflow file for where to get each one.
Consider adding required reviewers to the `production` GitHub Environment
(Settings → Environments) for a second confirmation step before any
production deploy runs.

## 4. Verify the deployment

1. Visit the Vercel URL — you should land on `/login` (since `APP_API_TOKEN`
   is set); log in with the password.
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

## 6. Staging environment

Recommended before ever pointing production at a real broker account (even
practice/OANDA), and definitely before `LIVE_TRADING_ENABLED=true` is ever
considered: a staging deployment that exercises the exact same code path
against real market data, fully isolated from production's database, Redis,
secrets, and domain. `app/main.py`'s boot guard refuses to even start if
`APP_ENV=staging` and `LIVE_TRADING_ENABLED=true` are both set — staging
exists specifically to validate with Paper/Practice trading, never a real
order — so this is enforced at the process level, not just by convention.

### Railway: a second Environment, not a second project

Railway's own "Environments" feature (distinct from this app's `APP_ENV`
setting, though they should match) is the right fit here — same project,
same services, a separate variable set and, critically, **separate database
instances that are never copied from production**:

1. Railway dashboard → your project → **Environments** → **New Environment**
   → name it `staging`, "Fork from Production" (this copies the *service
   structure* — api, worker — not any data).
2. Add a **new** Postgres and Redis service to the `staging` environment
   specifically (New → Database, same as step 1 of the production
   walkthrough above, but while the `staging` environment is selected in the
   environment switcher) — do not point staging at production's Postgres/
   Redis instances under any circumstances.
3. Set the `staging` environment's variables (Variables tab, with `staging`
   selected):
   ```
   APP_ENV=staging
   APP_API_TOKEN=<a DIFFERENT generated secret from production's>
   ALLOWED_ORIGINS=https://<your-staging-vercel-domain>
   DATABASE_URL=<staging Postgres, from step 2 above, +asyncpg>
   REDIS_URL=<staging Redis, from step 2 above>
   BROKER_PROVIDER=mock              # or oanda with OANDA_ENVIRONMENT=practice
   LIVE_TRADING_ENABLED=false        # the app refuses to boot in staging otherwise
   ```
4. Deploy with `railway up --service api --environment staging --detach`
   (and the same for `worker`), or via the GitHub Actions workflow below.
5. Run the initial migration against staging specifically:
   `railway run --service api --environment staging alembic upgrade head`.

### Vercel: a separate project, not a Preview deployment

Don't rely on Vercel's automatic PR Preview deployments as "staging" — a
Preview deployment's environment variables are easy to accidentally leave
pointed at production (see "Locking down Preview deployments" above), and a
Preview URL is meant to be short-lived/per-PR, not a stable environment you
return to regularly. Instead:

1. Import the same GitHub repo into Vercel a **second time** as a new
   project (e.g. `fxlab-staging`), Root Directory `frontend`, same as the
   production import in step 3 above.
2. Set this project's **Production** environment variables (Vercel's own
   per-project environment concept — this is that project's live/main
   deployment, which is what you'll actually visit as "staging"):
   ```
   NEXT_PUBLIC_WS_URL=wss://<your-staging-railway-api-domain>
   BACKEND_INTERNAL_URL=https://<your-staging-railway-api-domain>
   BACKEND_API_TOKEN=<same value as staging's APP_API_TOKEN above>
   APP_API_TOKEN=<the staging /login password — can equal BACKEND_API_TOKEN>
   SESSION_SECRET=<yet another distinct generated secret>
   ```
   None of these should be shared with the production Vercel project — a
   fully separate project means a fully separate variable set by
   construction, which is the whole point.
3. Deploy. Go back to the staging Railway `api` service and confirm
   `ALLOWED_ORIGINS` matches this new project's actual domain exactly.

### Deploying staging via GitHub Actions

`.github/workflows/deploy.yml` takes an `environment: [staging, production]`
input alongside the existing `target` input — select `staging` explicitly
every time (there is no default, by design, so a misclick can't land on
production). One-time setup: create a `staging` GitHub Environment
(Settings → Environments) with its own `RAILWAY_TOKEN`, `VERCEL_TOKEN`,
`VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` secrets (same names as `production`'s,
different values — `VERCEL_PROJECT_ID` in particular MUST point at the
separate staging Vercel project from above).

### What must differ between staging and production (checklist)

| | Staging | Production |
|---|---|---|
| Railway environment | `staging` (forked, separate DB/Redis) | `production` |
| Vercel project | separate project | separate project |
| `APP_API_TOKEN` (backend) | distinct value | distinct value |
| `SESSION_SECRET` (frontend) | distinct value | distinct value |
| `ALLOWED_ORIGINS` | staging Vercel domain only | production Vercel domain only |
| `DATABASE_URL` / `REDIS_URL` | staging instances, never copied from prod | production instances |
| `BROKER_PROVIDER` | `mock` or `oanda` w/ `OANDA_ENVIRONMENT=practice` | whatever you've deliberately configured |
| `LIVE_TRADING_ENABLED` | always `false` (enforced by a boot guard) | `false` until you deliberately change it |
| Session cookie | issued by, and only valid against, the staging frontend's own `SESSION_SECRET` — logging into staging never grants access to production or vice versa | — |

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

- [ ] Backend `APP_API_TOKEN` set to a real generated secret (not the placeholder)
- [ ] `ALLOWED_ORIGINS` set to your actual frontend domain (not blank, not `*`)
- [ ] Frontend `BACKEND_API_TOKEN` matches the backend's `APP_API_TOKEN` exactly
- [ ] Frontend `SESSION_SECRET` is set to its own distinct generated secret
- [ ] Frontend `APP_API_TOKEN`, `SESSION_SECRET`, `BACKEND_API_TOKEN` are
      scoped to Vercel's **Production** environment only — not also enabled
      for Preview deployments (see "Locking down Preview deployments" above)
- [ ] `LIVE_TRADING_ENABLED=false` (confirm explicitly — don't assume the
      platform default matches this app's default)
- [ ] No `.env` file committed to the repo (`git status` clean, `.gitignore`
      covers it — verified already in this repo, re-verify in your fork)
- [ ] Broker credentials (if configured) are Railway environment variables,
      never in code or committed config
