# 20. Disaster Recovery

Concrete "this happened, now what" procedures. Where a failure mode is
already exercised by `backend/scripts/chaos_test.py` (docs/19), that's
cited directly rather than re-described — this doc is about the cases the
chaos script can't safely automate (secret leakage, misplaced orders) or
the human-decision steps around an automated one.

## Database (Postgres) down

**Automatic**: `/ready` reports `checks.database: false` immediately;
`GET /system/status` and the System page reflect it. The API itself stays
up and DB-backed endpoints fail with a clean `5xx`, not a hang (verified —
`docs/19_LONG_RUNNING_AND_CHAOS_TESTING.md`). Once Postgres comes back,
the API reconnects on its own (`pool_pre_ping=True`) — **no API restart
needed**, verified the same way.

**Manual steps if it doesn't recover on its own**:
1. Check the managed Postgres service's own status page/dashboard
   (Railway: Postgres service → Metrics/Logs).
2. If the instance itself is gone (not just unreachable), restore the most
   recent backup — see "Restore" in `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md`
   "Database backup / restore / retention", verified as a real working
   procedure during this review (a full pg_dump → fresh-database restore
   round-trip, row-for-row identical afterward — see docs/15 for the dated
   result).
3. After restore, run `alembic upgrade head` against the restored database
   before resuming traffic — a backup taken before the latest migration
   will be missing recent schema.

## Redis down

**Automatic**: `/ready` reports `checks.redis: false`; the REST API keeps
serving requests (rate limiting fails open by design — verified under a
real Redis outage, docs/19). WebSocket price delivery stops (Redis
pub/sub is the only transport) — the frontend's LIVE/STALE/DISCONNECTED
indicator reflects this within `PRICE_STALE_SECONDS`. Once Redis comes
back, **no API/worker restart needed** — verified.

**Manual steps if it doesn't recover on its own**: Redis in this app holds
no data that must survive a restart by design (ticks/candles persist to
Postgres; Redis is a cache + pub/sub bus) — a fresh empty Redis instance is
always an acceptable recovery, no restore procedure needed. If using a
managed Redis, just restart/recreate the instance and point `REDIS_URL` at
it.

## Broker (market data or trading) unreachable

**Automatic**: `system:broker_connected` flips to `0`; the System page and
`/system/status` reflect it; `RiskContext.broker_connected=False` makes
the Risk Engine reject new orders (fail-closed, not fail-open —
`docs/10_RISK_MANAGEMENT.md` "Fail-closed audit findings"). The worker
retries the price stream with exponential backoff on its own
(`app/services/market_data.py::run`).

**Manual steps**:
1. `GET /api/v1/live/preflight` — checks auth, account access, and
   per-instrument price access independently, so "the token expired" is
   distinguishable from "this instrument was delisted" from "the broker's
   API is down entirely" (docs/10_RISK_MANAGEMENT.md "Broker Credential
   Validation").
2. If it's the broker's own outage (not a config issue), there's nothing
   to do but wait — the app already degrades safely (no new orders, stale
   price indicator visible) and self-heals once the broker recovers.
3. If it's a credential issue (rotated/expired token), update
   `OANDA_API_TOKEN`/`GMO_COIN_API_KEY`+`_SECRET` and redeploy — see
   `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` "5. Connecting a real broker".

## API process down (crashed, OOM, etc.)

**Automatic in production**: Railway's `restartPolicyType = "ON_FAILURE"`
(`backend/railway.toml`) restarts it. **Not automatic in a bare local run**
(`uvicorn app.main:app` with no supervisor) — verified the difference
explicitly in the chaos test (docs/19).

**Manual steps** (self-hosted/local only): restart the process. Verify
`/health` returns 200, then `/ready`, then check the System page's
dependency grid before assuming everything recovered.

## Frontend down

Vercel's own platform handles process-level recovery (serverless — there's
no long-running frontend process to crash the way the API/worker are).
If the Vercel deployment itself is broken (bad build, misconfigured env
var): roll back to the previous deployment from the Vercel dashboard
("Rollback to previous deployment") — this is a few-second operation, not
a rebuild. Check the same rollback exists on the Railway side for the API
if a bad backend deploy is the actual root cause.

## Secret leakage (a token/password ends up somewhere it shouldn't)

1. **Rotate it immediately** — generate a new value
   (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`),
   update it everywhere it's configured (backend `APP_API_TOKEN` and,
   separately, frontend `BACKEND_API_TOKEN`/`APP_API_TOKEN`/
   `SESSION_SECRET` — see `docs/11_SECURITY.md` "BFF migration" for which
   is which), redeploy both services.
2. Rotating `SESSION_SECRET` specifically invalidates every existing
   session cookie at once (they fail signature verification against the
   new secret) — this is the fastest available way to force every open
   session to re-authenticate, useful if a session cookie itself (not the
   password) is what leaked.
3. Check `GET /audit-log` for `login` entries around the suspected leak
   window — an unexpected login is the concrete evidence a leaked
   credential was actually used, not just potentially exposed.
4. If a broker credential leaked: revoke/regenerate it directly on the
   broker's own dashboard (OANDA: Manage API Access; GMO Coin: API
   settings) — rotating this app's own tokens does nothing to a leaked
   broker credential, since the broker doesn't know or care about them.
5. If a real (non-practice) broker credential leaked while LIVE trading
   was armed: activate the Kill Switch immediately
   (`POST /live/kill-switch`, or the System page button) before doing
   anything else — this is deliberately the fastest action available,
   independent of every other gate.

## Suspected unauthorized access

1. Check `GET /audit-log` for `login` entries you don't recognize, and
   for any `kill_switch_*`/`risk_setting_change`/`live_trading_admin_*`
   entries around the same time — these are exactly the actions worth a
   human review, and the audit log's `before`/`after` fields show
   precisely what changed (`docs/15_PRODUCTION_READINESS_REVIEW.md`
   "Audit Log").
2. Rotate `APP_API_TOKEN` and `SESSION_SECRET` regardless of whether
   anything looks tampered with — see "Secret leakage" above; unauthorized
   access implies the credential is compromised even if nothing was
   changed yet.
3. Review `RiskSettings` (`GET /settings/risk`) against what you expect —
   an attacker with access could have widened risk limits before the
   audit log entry catches your eye.

## A trade may have been placed in error (misclick, wrong size, wrong direction)

1. Paper trading: close the position immediately from the Paper Trading
   page — no real money is at risk, but a wrong entry still pollutes the
   journal/analytics if left open.
2. LIVE (once implemented and ever used for real — see
   `docs/10_RISK_MANAGEMENT.md`): close the position via the broker's own
   web/app interface if this app's own close flow is itself in question,
   don't wait. Then activate the Kill Switch to prevent a second mistake
   while you investigate what happened.
3. Check `GET /audit-log` for the `live_order_preview`/`live_order_reject`
   trail around the time in question — the preview endpoint
   (`POST /live/orders/preview`) logs exactly what the Risk Engine saw and
   decided, which is the fastest way to answer "why did this get approved"
   after the fact.

## Suspected duplicate order

The Order Orchestrator's idempotency-key check
(`docs/10_RISK_MANAGEMENT.md`) is designed to make this structurally
impossible for orders that reuse the same key (a replayed/duplicated
request returns the original result, never creates a second position) —
verified by `tests/test_order_orchestrator.py`'s concurrent-duplicate-
submission test. If two *different* idempotency keys nonetheless produced
what looks like a duplicate real-world position:
1. Check `GET /api/v1/journal/trades` and (for paper) `GET /paper/positions`
   for both entries' `idempotency_key`/timestamps to confirm they really
   are two distinct submissions, not one being displayed twice.
2. Close the extra position the same way as "a trade may have been placed
   in error" above.

## Order result unknown (broker call timed out / connection dropped mid-request)

This is the one broker-integration case the app cannot fully resolve on
its own — an order request that reaches the broker but whose response
never reaches this app leaves genuine ambiguity about whether it filled.
1. Check the broker's own account/positions directly (their web interface
   or `GET /live/positions`, which reads live from the broker, not a local
   cache) — this is the authoritative source, not anything this app has
   stored locally.
2. Reconcile against what this app's journal shows; if they disagree,
   trust the broker's own account state and manually correct the local
   journal entry (or just note the discrepancy — the broker's own records
   are what matter financially).
3. Activate the Kill Switch while reconciling if there's any doubt about
   whether more orders might compound the confusion.
