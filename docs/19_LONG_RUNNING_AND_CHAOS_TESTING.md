# 19. Long-Running / Soak / Chaos Testing

Two scripts under `backend/scripts/`, both actually run against a live local
stack during this review (not just written and assumed to work) — real
results from those runs are included below, dated, so this doc doesn't
silently go stale relative to what was actually verified.

## `soak_test.py` — volume / leak detection

Drives `MarketDataService.handle_tick()` — the exact code path the worker's
real price-poll loop calls — through a large number of synthetic ticks as
fast as the event loop and I/O allow, rather than waiting for real wall-clock
hours to accumulate real ticks (the worker's default 2s poll interval would
need ~14 hours to reach 100,000 ticks across 4 instruments). Reports
ticks/sec, RSS memory, SQLAlchemy connection pool usage, and asyncio task
count at regular intervals, so a leak shows up as a trend across the run,
not just a before/after snapshot.

```bash
cd backend && source .venv/bin/activate
DATABASE_URL=postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab_test \
REDIS_URL=redis://localhost:6379/1 \
python -m scripts.soak_test --ticks 100000
```

Creates and, by default, cleans up its own synthetic instruments
(`SOAK_USDJPY` etc.) — pass `--no-cleanup` to inspect the resulting rows
afterward. Run against a disposable database, not one you care about.

### Actual result (this review, 2026-07)

120,000 ticks, 4 instruments, real Postgres + Redis:

| Metric | Result |
|---|---|
| Throughput | 548.9 ticks/sec average, stable across the whole run (no slowdown trend) |
| RSS memory | 81.0MB → 81.4MB (**+0.4MB** over 120k ticks — flat, no leak) |
| DB connection pool | `checked_out=0` at every sample point (connections released correctly) |
| Asyncio tasks | 1 → 1 (**no task leak**) |
| Rejected ticks | 0 / 120,000 (expected — the mock broker's random walk stays within `validate_tick`'s bounds by construction) |
| `MarketTick` rows written | 176 (correctly throttled to ~1/5s/instrument, not 1/tick — confirms the throttle in `_maybe_persist_tick` behaves correctly under sustained load) |

No leak of any kind observed at this volume. This is real evidence for this
run, not a guarantee for all time — re-run after any change to
`MarketDataService`, `CandleBuilder`, or the Redis/DB client wrapper code.

## `chaos_test.py` — fault injection

Spawns its own API + worker subprocesses (so it can kill/restart them
directly) and controls the system Postgres/Redis services, then runs through
a fixed sequence of failure scenarios, checking both that the failure is
*visible* (not silently swallowed) and, separately, whether recovery is
automatic or needs a human.

**This stops and restarts system-wide Postgres/Redis services** — run only
against a disposable local/dev environment, never anything shared, and only
with `--i-understand-this-stops-postgres-and-redis` (required, not a
default-yes flag, so it can't run by accident):

```bash
cd backend && source .venv/bin/activate
DATABASE_URL=postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab_test \
REDIS_URL=redis://localhost:6379/1 \
python -m scripts.chaos_test --i-understand-this-stops-postgres-and-redis
```

### Actual result (this review, 2026-07): 12/12 checks passed

| Scenario | Detected correctly? | Recovery |
|---|---|---|
| Redis stopped | `/ready` → 503, `checks.redis: false` within the poll window | **Automatic** — `redis.asyncio` reconnected on its own once Redis came back; no API/worker restart needed |
| Redis down — rate limiter | REST API kept serving requests (200s) the whole time | N/A — confirms the *documented* fail-open behavior (`docs/11_SECURITY.md` "Rate limiting") is real, not just claimed |
| Postgres stopped | `/ready` → 503, `checks.database: false`; a DB-backed endpoint (`/journal/trades`) returned `500` in 0.1s — a clean failure, not a hang | **Automatic** — `pool_pre_ping=True` reconnected on its own once Postgres came back; no API restart needed |
| Flood of 1,000 abnormal ticks (non-positive price, bid≥ask, spread blowout, price-jump anomaly) | All 1,000 rejected by `validate_tick`; the service's last-known-good tick was unchanged afterward | N/A — nothing to recover from, this *is* the recovery mechanism working |
| Rate limit (tested at a lowered 10/min threshold for a fast check) | First `429` arrived at request #11 — the limit trips at essentially the configured threshold, not late or never | N/A |
| Worker process killed | `worker_alive` in `/system/status` correctly flipped to `false` once the 90s heartbeat TTL expired (not immediately — this is expected: it's the difference between "worker crashed" and "worker momentarily quiet" the heartbeat design is for) | **Manual** (process-level) in this local test — restarting the bare process brought it back. In an actual Railway deployment, `restartPolicyType = "ON_FAILURE"` (`backend/railway.toml`) does this automatically; a `python -m app.worker.main` left running locally has no supervisor of its own, which is exactly why this local chaos test had to restart it itself |
| API process killed | Became unreachable immediately (`/health` failed) | **Manual** (process-level) locally, same Railway-automatic caveat as above |

### What this confirms vs. what it doesn't

Confirms, with real evidence from this run, not just design intent:
- The app's dependency-health reporting (`/ready`, `/system/status`) is
  accurate during an actual outage, not just when everything is fine.
- Redis and Postgres outages are genuinely transparent to recover from —
  no manual restart of the API needed for either, which matters a lot for
  an unattended personal deployment.
- The rate limiter's fail-open behavior under a Redis outage is real.
- Price-quality validation actually holds under a deliberate flood of
  garbage input, not just the one-at-a-time cases the unit tests cover.

Does **not** confirm (out of scope for this pass, noted honestly):
- Broker disconnect/reconnect at the full-stack level — the mock broker has
  no built-in "simulate a disconnect" toggle, and OANDA/GMO Coin aren't
  available to test against in this sandbox. This failure mode *is* covered,
  but at the unit/integration level against a test double
  (`tests/test_risk_engine.py`, `tests/test_order_orchestrator.py` — broker
  disconnect at order-entry and at position-close), not by this chaos
  script driving a real running stack.
- WebSocket client reconnect behavior specifically — implicitly exercised
  (existing connections drop when the API process is killed above), but not
  asserted on directly; the frontend's reconnect-with-backoff logic
  (`frontend/src/lib/priceSocket.ts`) has its own test coverage via the
  Playwright E2E suite reconnecting cleanly across page loads, not a
  dedicated mid-connection-kill assertion.
- Real multi-day soak duration — the volume test substitutes tick *count*
  for elapsed *time* (see `soak_test.py`'s docstring for why), which
  exercises the same code paths under the same call volume but does not
  by itself rule out a slow leak that only manifests over real days (e.g.
  OS-level file descriptor accumulation, log file growth). Recommended
  before a real-money deployment: leave the actual worker+API running
  for several real days in staging and periodically re-check RSS/pool/task
  counts by hand — `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md`'s staging
  environment is the right place to do this.
