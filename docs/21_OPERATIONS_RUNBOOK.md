# 21. Operations Runbook

Routine operator checks for a running deployment — what to look at, how
often, and what a bad reading means. This is the "nothing's on fire, but am
I sure?" companion to `docs/20_DISASTER_RECOVERY.md` ("something's on
fire, now what?"). Every check below points at a concrete endpoint, page,
or command that already exists — nothing here requires new tooling.

## Daily

1. **System page** (`/system`) — glance at the dependency grid (Broker /
   Database / Redis / Worker / WebSocket clients / Signal Engine) and the
   Kill Switch state. All green, Kill Switch state matches what you expect
   (normally OFF unless you deliberately tripped it).
2. **`GET /audit-log?limit=20`** — skim for anything you didn't do
   yourself: an unexpected `login`, a `risk_setting_change` you don't
   recognize, any `live_trading_admin_enable`/`kill_switch_*` entry. See
   `docs/20_DISASTER_RECOVERY.md` "Suspected unauthorized access" if
   something doesn't match.
3. **`GET /system/status`** → `last_error` — a non-null recent error worth
   a quick read even if everything else looks fine; catches problems that
   self-recovered before you'd have noticed them on the dependency grid.
4. **Worker heartbeat** — `worker_alive` on the System page (backed by the
   30s heartbeat / 90s TTL key, `app/worker/jobs/heartbeat.py`). If this is
   ever `false` on a check, the worker process needs a manual restart in a
   bare/local deployment (Railway's `restartPolicyType = "ON_FAILURE"`
   handles it automatically there — see `docs/20`).

## Weekly

1. **Backup verification** — take a `pg_dump` per
   `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` "Database backup / restore /
   retention". Periodically (monthly is enough, see below) actually
   restore it into a scratch database rather than trusting the dump file
   exists and is non-empty — a backup that can't restore isn't a backup.
2. **Broker connection check** — `GET /api/v1/live/preflight`. Confirms
   auth, account access, and per-watchlist-instrument price access
   independently, so a partial failure (one delisted instrument, say)
   doesn't read as "everything's broken." Worth running even while LIVE
   trading stays disabled, since it's also how you'd notice a market-data
   provider credential quietly expiring.
3. **Paper Trading performance review** — Paper Trading page + `GET
   /analytics/win-rate?dimension=pair` (and `dimension=regime`,
   `dimension=score_bucket`). Sanity-check that recent paper performance
   still looks like what you expected from backtesting — a large,
   sustained divergence is worth investigating before ever considering
   LIVE trading (`docs/10_RISK_MANAGEMENT.md` "Recommended rollout
   sequence").
4. **Signal accuracy check** — `GET
   /analytics/signal-outcomes?pair=<pair>` (Analytics page). Compares
   score-bucket win rates against what the signal engine implies a score
   means (docs/08_SIGNAL_ENGINE.md "Signal outcome history") — this is
   the ongoing "is the signal engine still doing what it claims"
   check, independent of whether you're actually trading it.
5. **Log review** — skim recent structured logs (Railway: service → Logs)
   for repeated warnings/errors that never made it to a `SystemEvent` or
   the audit log — those two only capture specific known event types, not
   everything. `X-Request-ID` (docs/05_API_DESIGN.md) makes any one
   incident easy to grep once you spot it.

## Monthly

1. **Full restore drill** — actually restore a recent backup into a fresh,
   disposable database and spot-check row counts / key tables (Users,
   RiskSettings, TradeJournalEntry, AuditLog) match what you expect,
   exactly as verified once already during this production-readiness
   review (`docs/15_PRODUCTION_READINESS_REVIEW.md`). Drop the scratch
   database afterward. This is the check that actually proves backups are
   usable, not just that they're being taken.
2. **Kill Switch check** — deliberately trip it (`POST
   /live/kill-switch` or the System page button) and confirm: new paper
   orders are rejected while it's active, `GET /audit-log` shows a
   `kill_switch_on` entry, then deactivate and confirm the matching
   `kill_switch_off` entry appears too. Exercising the emergency stop
   occasionally is the only way to be sure it still works when you need
   it for real.
3. **Dependency / secret hygiene** — check for outstanding `npm audit` /
   `pip`-equivalent advisories on direct dependencies; confirm no secret
   has been sitting unrotated indefinitely (there's no fixed mandatory
   rotation cadence for a single-operator app, but "have I ever rotated
   this" is worth asking periodically — see `docs/20_DISASTER_RECOVERY.md`
   "Secret leakage" for the rotation procedure itself).
4. **Chaos/soak re-run** (optional, recommended after any dependency
   upgrade or infrastructure change) — re-run `backend/scripts/soak_test.py`
   and `backend/scripts/chaos_test.py` (docs/19) against a non-production
   environment to confirm the app still degrades and recovers the way
   `docs/20_DISASTER_RECOVERY.md` describes; a framework/library upgrade
   is exactly the kind of change that can silently break a recovery path
   nothing else exercises.

## Incident response (when a daily/weekly/monthly check turns something up)

1. Identify which `docs/20_DISASTER_RECOVERY.md` section matches (Database
   down, Redis down, Broker unreachable, secret leakage, unauthorized
   access, etc.) and follow its manual steps.
2. If nothing in `docs/20` matches, use `GET /system/status` and `GET
   /audit-log` together to establish a timeline before acting — most of
   this app's failure modes are visible in one or the other.
3. If the incident involved LIVE trading in any way (even just
   `live_trading_admin_enabled` being on at the time), activate the Kill
   Switch first, investigate second — this mirrors `docs/20`'s "trade
   placed in error" and "secret leakage" guidance: the Kill Switch is the
   fastest, most independent action available and costs nothing to trip
   speculatively.
4. Record what happened and what you did about it somewhere durable
   outside the app itself (the audit log captures the app's own state
   transitions, not your own narrative of "why") — even a plain text note
   is enough for a single-operator deployment; the point is being able to
   answer "has this happened before" next time.
