# 22. Production Deployment Checklist

Checkbox-format pre-flight for a real deployment (first deploy, or any
deploy where secrets/environment/broker config changed). This is the
"about to actually do it" companion to `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md`
(the how-to) and `docs/15_PRODUCTION_READINESS_REVIEW.md` (the evidence
behind each item). Nothing here is new tooling — every item points at an
existing endpoint, env var, or script.

## Secrets

- [ ] `APP_API_TOKEN` set to a fresh random value
      (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`),
      not a value ever used in local dev or staging.
- [ ] `SESSION_SECRET` set to a separate fresh random value (never equal to
      `APP_API_TOKEN`, never reused from staging).
- [ ] Frontend's `BACKEND_API_TOKEN` matches the backend's `APP_API_TOKEN`
      exactly (mismatch = every proxied request 401s — verify with the
      smoke test below, not just by eyeballing the values).
- [ ] No secret appears in `NEXT_PUBLIC_*` — grep the built frontend bundle
      if unsure (`grep -r "APP_API_TOKEN\|SESSION_SECRET" frontend/.next/`
      should find nothing outside comments/source maps you're not shipping).
- [ ] `OANDA_API_TOKEN`/`GMO_COIN_API_KEY`+`_SECRET` (if set) are the
      correct environment's credentials — practice vs live, not swapped.

## Authentication

- [ ] Non-development `APP_ENV` (`staging`/`production`) — confirm the
      boot guard actually refuses to start without `APP_API_TOKEN` (try
      booting with it unset in a scratch environment once, expect a
      `RuntimeError`, `backend/tests/test_boot_guards.py`).
- [ ] `/login` reachable, wrong password rejected (401), correct password
      sets a cookie that is NOT the raw password (inspect the cookie value
      directly).
- [ ] Logout clears the cookie and re-gates every page.

## CORS

- [ ] `ALLOWED_ORIGINS` set to the exact production frontend origin(s),
      comma-separated, no wildcard.
- [ ] A request from a non-listed `Origin` is rejected — CORS preflight
      for REST, and the WebSocket route's own `Origin` check
      (`backend/app/ws/auth.py`) for `/ws/prices` and `/ws/system`.

## CSRF

- [ ] Session cookie is `SameSite=Strict` (frontend/src/lib/session.ts) —
      confirm in browser devtools on the real deployed cookie, not just in
      source.
- [ ] All state-changing backend routes require the bearer token (not just
      the cookie) — the cookie only gates the frontend's own pages; the
      backend itself never trusts a cookie.

## Cookie

- [ ] `Secure` flag set (only true when `NODE_ENV=production` — confirm
      the deployed frontend actually has that env var set, since a missed
      `NODE_ENV` silently ships an insecure cookie over HTTPS anyway but
      without the browser enforcing it).
- [ ] `HttpOnly` set (not readable from `document.cookie` — check in
      devtools).
- [ ] Cookie domain/path scoped correctly if frontend and backend share a
      parent domain; not shared between staging and production.

## Database

- [ ] `DATABASE_URL` points at the production instance, not staging/dev.
- [ ] `GET /ready` reports `checks.database: true`.
- [ ] Connection pool sized reasonably for the deployment
      (`docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md`) — not the local-dev
      default if traffic is expected to be non-trivial.

## Redis

- [ ] `REDIS_URL` points at the production instance.
- [ ] `GET /ready` reports `checks.redis: true`.
- [ ] Confirmed this Redis instance is NOT shared with staging (separate
      instance per `docs/17`'s staging-separation guidance — a shared
      Redis would leak WS tickets and rate-limit counters across
      environments).

## Migration

- [ ] `alembic upgrade head` run against production BEFORE traffic is
      routed to the new deploy (not after) — see `docs/17`'s
      "Migration" section for the deploy-order rationale.
- [ ] Migration is backward-compatible with the currently-running
      previous version if this is a rolling/zero-downtime deploy (no
      column drops/renames in the same release that also removes the old
      code path reading them).
- [ ] A fresh backup exists from immediately before the migration ran
      (see "Backup" below) — taken BEFORE, not after.

## Backup

- [ ] A `pg_dump` taken within the last 24h, per
      `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` "Database backup / restore
      / retention".
- [ ] Restore procedure has been exercised at least once against this
      exact database schema version (not just "in general, once, a while
      ago") — see `docs/21_OPERATIONS_RUNBOOK.md` "Monthly — Full restore
      drill".

## Worker

- [ ] Worker service deployed and its logs show `worker starting: ...`
      (NOT `Uvicorn running on...` — the config-precedence risk flagged in
      `docs/17`'s "Service worker" section; if you see the Uvicorn line,
      the worker's start command was silently overridden).
- [ ] `GET /system/status` → `worker_alive: true` within 90s of the
      worker's own startup (heartbeat TTL).
- [ ] Restart policy configured (Railway: `restartPolicyType =
      "ON_FAILURE"` in `backend/railway.toml`) — confirm it's actually
      applied to the worker service specifically, not just the API
      service.

## Broker

- [ ] `BROKER_PROVIDER` (and `MARKET_DATA_PROVIDER` if split) set to the
      intended real provider, not `mock`.
- [ ] `GET /api/v1/live/preflight` returns `all_ok: true` — auth, account
      access, AND per-watchlist-instrument price access, checked
      independently.
- [ ] `BROKER_ENVIRONMENT` confirmed as `practice` unless this deployment
      is deliberately, consciously going live (see "LIVE Trading OFF"
      below — practice should be the default for every new deployment).

## Market Data

- [ ] Watchlist instruments (`DEFAULT_WATCHLIST`) resolve on the chosen
      provider — a symbol-mapping gap here shows up as a per-instrument
      failure in `/live/preflight`, not a generic error.
- [ ] Live ticks visible on the dashboard within a few seconds of
      deployment (confirms the WebSocket path end-to-end, not just the
      REST preflight).

## LIVE Trading OFF

- [ ] `LIVE_TRADING_ENABLED=false` in this deployment's env vars — the
      first of three required gates, confirmed explicitly, not assumed
      from a template default.
- [ ] `live_trading_admin_enabled` is `false` in `GET /settings/risk` (the
      second gate — an admin-panel toggle, independent of the env var).
- [ ] `POST /live/orders` returns `403` (confirms both gates are actually
      enforced together, not just individually true).
- [ ] Staging specifically: confirm the boot guard that refuses to start
      if `APP_ENV=staging` AND `LIVE_TRADING_ENABLED=true`
      (`backend/app/main.py`, `backend/tests/test_boot_guards.py`) is in
      place — staging must never be able to place real orders even by
      misconfiguration.

## Kill Switch

- [ ] `kill_switch_active: false` at deploy time (unless intentionally
      deploying with it engaged).
- [ ] Exercised once post-deploy — trip it, confirm new paper orders are
      rejected and an audit entry appears, then deactivate (see
      `docs/21_OPERATIONS_RUNBOOK.md` "Monthly — Kill Switch check"; worth
      doing once on first deploy too, not just monthly thereafter).

## Alerts

- [ ] In-app notifications (`GET /notifications`, System page) confirmed
      reachable post-deploy.
- [ ] Operator knows to check the System page / audit log on the cadence
      in `docs/21_OPERATIONS_RUNBOOK.md` — external push notification
      channels (Discord/LINE) remain unimplemented placeholders
      (`DISCORD_WEBHOOK_URL`/`LINE_NOTIFY_TOKEN` in `.env.example`); until
      one is wired up, in-app + manual checks are the only alerting that
      actually exists — do not assume a webhook fires.

## Health / Ready

- [ ] `GET /health` returns 200.
- [ ] `GET /ready` returns 200 with both `database` and `redis` true.
- [ ] Both are reachable from whatever's used as the deploy platform's
      health-check target (Railway service health check config) — a
      health check pointed at the wrong path/port silently never catches
      a bad deploy.

## Smoke Test

- [ ] `backend/scripts/deploy_smoke_test.py` run against the deployed
      URLs (`STAGING_BASE_URL=... STAGING_WS_URL=... python3
      backend/scripts/deploy_smoke_test.py`) and passes — covers
      login, markets, chart data, WebSocket ticks, replay, paper trading,
      and system status end-to-end against the real deployment, not just
      individually-checked boxes above.
