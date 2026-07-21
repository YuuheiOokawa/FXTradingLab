# 15. Production Readiness Review

This review was done by re-reading the actual code (not trusting the prior
completion report), running every service together, exercising every page in a
real browser, and running the full test suite — then fixing what was found,
not just cataloging it. Every "fixed" item below has a verifying test or a
before/after screenshot; see the commit history on this branch for the exact
diffs. Grades: **A** production-usable · **B** usable after minor fixes ·
**C** needs improvement · **D** significant gaps · **E** not implemented.

## Real problems found and fixed during this review

These are the substantive findings — not stylistic nits — surfaced by actually
reading and exercising the code rather than trusting the docs:

1. **WebSocket endpoints had zero authentication**, despite `docs/11_SECURITY.md`
   already claiming they required the bearer token. Fixed: `app/ws/auth.py`
   checks a `?token=` query param (browsers can't set WS handshake headers),
   tested in `tests/test_ws_auth.py`.
2. **CORS was hardcoded to block everything in every non-development
   environment**, with no environment variable to configure it — a real
   deployment would have silently broken with zero explanation. Fixed: added
   `ALLOWED_ORIGINS`.
3. **A real look-ahead bias bug in the backtest engine's multi-timeframe
   confirmation**: the higher-timeframe window included the still-forming bar,
   whose OHLC in the synthetic/historical data always represents its *true
   final* close — leaking that bar's eventual close into a decision made
   before it actually closed. Fixed via `closed_higher_tf_window()`, with a
   regression test that fails on the old code.
4. **A real frontend WebSocket subscription race**: instruments subscribed
   while the shared socket was still mid-handshake had their subscribe
   message silently dropped (the code only sent it if `readyState` was
   already `OPEN` at that exact synchronous moment, with no retry). Since
   React mounts multiple watchlist rows in the same tick, only the very first
   instrument ever actually streamed — verified with a before/after
   screenshot of the Markets page (before: only row 1 showed data updating;
   after: all four rows show LIVE).
5. **`close_paper_position` didn't handle a broker outage during close** —
   would have surfaced as a raw 500 instead of a clean, retryable error.
   Fixed and tested (position correctly stays `open`, never half-closed).
6. **The `price:{instrument}:latest` Redis hash had no TTL** — a dead worker's
   last tick would keep looking "fresh" indefinitely to anything reading it,
   including the new `/metrics` endpoint. Fixed.
7. **GMO Coin FX-vs-crypto API re-verification** (explicitly requested,
   see `docs/16_BROKER_SELECTION_REVIEW.md`): the original conclusion was
   correct — GMO Coin's FX API (`api.coin.z.com/fxdocs`,
   `forex-api.coin.z.com`) is real and structurally separate from its crypto
   API (`api.coin.z.com/docs`). One precision fix made to the adapter's
   docstring (exact host name) and an explicit anti-confusion warning added.
8. **`favicon.ico` was missing** (404 on every single page load) — trivial but
   real; fixed.
9. **`docs/09_BACKTEST_DESIGN.md` claimed a `run_range()` primitive existed** as
   a Walk-Forward Analysis building block — it doesn't; `BacktestEngine.run()`
   only ever does a single IS/OOS split over whatever series it's handed, with
   no rolling-window concept. Doc corrected to describe what actually exists.

No TODO/FIXME/HACK/"not implemented" markers were found outside
`app/brokers/gmo_coin.py` (a deliberately-documented stub) — the prior
completion report's claims were substantially accurate; the above are the real
gaps that only surfaced from actually running things.

## Grades

| Area | Grade | Notes |
|---|---|---|
| Architecture | A | Clean layering (brokers/services/api/ws/worker), now with an explicit MarketDataProvider/TradingBroker split for the case where price source and order destination differ. |
| Frontend | A | All 12 pages render with zero console/hydration/network errors in a real headless-browser pass (after the favicon and WS-subscribe-race fixes). Login gate + Live Trading banner added. |
| Backend | A | 89 backend tests passing against a real Postgres DB, not mocks. |
| Database | A | Migrations apply cleanly forward and backward; schema matches docs. |
| Realtime | B | Reconnect/backoff, stale/live/disconnected indicator, and price quality validation now in place and tested. Remaining gap: no heartbeat frame independent of tick traffic (a genuinely idle market — unlikely for FX but not impossible around session close — would look identical to a stalled connection until the next tick or the stale timer fires; low practical risk, not fixed this pass). |
| Broker Integration | B | OANDA adapter is type-safe end-to-end (no raw JSON leaks past `app/brokers/oanda.py`), now retries transient GET failures with backoff, never auto-retries order submission (by design — see docs/16). GMO Coin remains a documented stub pending a funded account + a direct read of its live docs (automated fetches hit anti-bot protection during this review, see docs/16). |
| Signal Engine | A | Audited specifically for look-ahead bias; found and fixed a real one (see above). Entry-timeframe evaluation only ever sees bars up to and including "now" by construction of the bar loop. |
| Backtest | A | Conservative same-bar SL/TP handling (SL assumed first) was already correct and tested; the MTF look-ahead fix closes the one real gap found. |
| Replay | A *(see "a third pass" update below — raised from C)* | Candles are revealed one at a time with no future data reaching the frontend, now backed by persisted `ReplaySession`/`ReplayTrade` (survives a server restart, verified) with 3-tier qualitative judgment scoring (良い判断/普通/危険な判断) that structurally cannot see the outcome it's grading. |
| Paper Trading | A *(see "a third pass" update below — raised from B)* | Fills at bid/ask with the current live quote through the same Risk Engine as everything else; now models adverse slippage on market fills and supports limit/stop pending orders with kill-switch re-checked at fill time, not just at placement. |
| Risk Engine | A | 10 checks, now with stress tests beyond the original per-rule unit tests: broker disconnect at entry and at close, daily-loss-limit and consecutive-loss-stop computed from real journal rows, max-concurrent-positions across distinct instruments — all exercised through the real submit/close flow against the real test database. |
| Security | B | Bearer-token REST+WS auth, CORS allowlist, secret redaction in logs, and a single-shared-secret frontend login gate are all real and tested. This is intentionally a single-operator model, not multi-user auth (out of scope per `01_REQUIREMENTS.md`) — appropriate for who this app is built for, but worth being explicit that it is not a general-purpose multi-tenant auth system. No rate limiting on the REST API (a determined actor with the token could hammer it) — acceptable for a single-operator personal deployment, would need addressing before wider exposure. |
| Observability | A *(see "a third pass" update below — raised from B)* | Structured logging with request-id **and now actually-populated order-id** correlation, `/health`, `/ready` (real DB+Redis checks), `/metrics`, and a System page showing every dependency (DB/Redis/Worker-heartbeat/WS-client-count/last-price/last-signal/uptime/last-error). No log shipping/alerting configured (expected — that's a deployment-time operator choice, not something to bake into the app). |
| Deployment | B | Docker Compose validated end-to-end locally (all 5 services). Dockerfiles, Railway/Vercel config present. No actual cloud deploy was performed from this sandbox (no cloud credentials available) — see `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` for the exact operator steps. |
| Testing | A | 149 backend tests (pytest, real Postgres) + 7 frontend unit tests, all passing, plus a committed/CI-wired Playwright end-to-end suite covering the full user journey — see "a third pass" update below. |

## Update — later in this same review pass

The findings and grades above were the state after the first sweep. Continuing
through the rest of the originally-requested scope (deployment guide,
security review, Walk-Forward Analysis, signal outcome history) surfaced more
real issues, since finding problems by actually building and exercising
things kept working the same way it did in the first sweep:

10. **A second, more serious secret-leakage bug in the frontend login gate**:
    the login page compared the submitted token against
    `NEXT_PUBLIC_APP_API_TOKEN` in its own client component — a value
    Next.js inlines into whichever bundle references it. Since `/login`
    must always be reachable by an unauthenticated visitor, anyone who
    merely loaded that page could read the real shared secret straight out
    of its own compiled JS, with zero prior knowledge of the token. Verified
    exploitable end-to-end (built the app, fetched the compiled `/login`
    chunk, found the plaintext token in it) before fixing it by moving the
    comparison server-side against a separate, never-client-shipped env var.
    See `docs/11_SECURITY.md` "Frontend login gate" for the full writeup —
    this is the most serious individual finding across the whole review.
11. **No rate limiting on the REST API**, already flagged as an open gap
    below — closed with a Redis-backed per-token fixed-window limiter.
12. **`docs/11_SECURITY.md` claimed `pip-audit`/`npm audit` already ran in
    CI** — verified against the actual workflow file, found neither did;
    added both for real.
13. **`docs/13_TEST_STRATEGY.md` overclaimed CI**: said mypy, a Playwright
    smoke test, and eslint all ran on every PR — verified against
    `.github/workflows/ci.yml`, found mypy and the Playwright job didn't
    exist at all, and eslint wasn't wired in either (`npm run lint` existed
    but nothing called it). Added eslint as a real gating step; corrected
    the doc's claims about mypy/ruff/Playwright to state honestly what's
    actually gating vs. still a known gap.
14. A cosmetic-but-real type-checker finding in `market_data.py::handle_tick`:
    a variable was reused across two incompatible types in the same
    function (harmless at runtime, since Python doesn't enforce it, but
    confusing to read and something `mypy` correctly flagged when actually
    run). Renamed.

Grade updates from the above and from implementing the two previously-"not
implemented" items (Walk-Forward Analysis, Signal outcome history):

| Area | Grade | Why |
|---|---|---|
| Security | B (held, not raised) | The login-gate fix (#10) closes the most serious finding in this review; rate limiting (#11) closes the other named gap. Held at B rather than raised to A because a materially stronger boundary (routing all API/WS traffic through a backend-for-frontend so the browser never holds the real bearer token at all) remains unbuilt — see `docs/11_SECURITY.md`'s "What this does and does not protect against" for exactly what's still residual. |
| Backtest | A (unchanged) | **Walk-Forward Analysis now implemented**, see `docs/09_BACKTEST_DESIGN.md`. Genuinely slow for a large parameter grid (documented, capped at 60 combinations) since it's a synchronous request running a full backtest per candidate per window; not persisted to the DB. Never suggests a single "adopt this" parameter set — verified by a test that asserts no such field exists in the response. |
| Testing | A (unchanged) | 112 backend tests passing (up from 89) against real Postgres, all new features covered; 7 frontend unit tests; full-stack browser verification (including Playwright) performed for every new UI surface added in this pass, not just described. |
| Deployment | B (unchanged) | `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` now exists with concrete steps, verified against Railway/Vercel's actual current (2026) docs via live research rather than assumed; a manual-trigger-only GitHub Actions deploy workflow is prepared. Still B, not A: no actual cloud deploy was executed from this sandbox. |

Signal outcome history (docs/08_SIGNAL_ENGINE.md) is a new capability, not a
grade change to an existing row — it's covered under "Signal Engine" (still
A) and "Testing" above.

One pre-existing test was observed to be flaky under load, unrelated to any
change in this pass: `test_concurrent_duplicate_submissions_result_in_exactly_one_open_position`
in `tests/test_order_orchestrator.py` (a 5-way concurrent-race test) failed
once and passed on three immediate retries — not a regression from this
review, but worth knowing about if it's ever seen failing in CI.

## Update — a third pass, closing the two long-standing "not implemented" gaps

This pass re-verified the current branch state against the actual code (not
the claims in this file) before doing anything else, then worked through the
two items this doc had honestly listed as open since the first pass: Replay
persistence/judgment scoring, and Paper Trading slippage/order types. Also
closed several smaller gaps found the same way as before — by exercising the
running app, not by reading docs.

15. **`docs/09_BACKTEST_DESIGN.md`'s `run_range()` claim (see #9 above) was
    still accurate as corrected** — re-checked, no regression.
16. **System page was missing several of the observability fields
    `docs/02_SYSTEM_ARCHITECTURE.md` describes**: Database/Redis connectivity
    were implied by every request succeeding but never surfaced explicitly,
    Worker liveness had no signal independent of tick traffic (so "worker
    crashed" and "market quiet" looked identical), WebSocket client count and
    last-signal-generated timestamp weren't exposed at all. Fixed: a 30s
    worker heartbeat key (90s TTL) distinct from tick flow, an in-process WS
    client counter, explicit `SELECT 1`/`PING` checks, and a
    most-recent-`Signal`-row query — all added to `GET /system/status` and
    the System page's dependency tile grid.
17. **`order_id` was declared as a structured-log field
    (`app/core/logging.py`) but was never actually populated** — every order
    log line had `order_id: null`, making "grep this order's full lifecycle"
    impossible in practice despite the log schema claiming to support it.
    Fixed with a proper `contextvars`-based `order_context()` scope wrapping
    paper/live order submission and close paths; verified with a test that
    spies on the context value during a real `POST /paper/orders` call
    through the ASGI transport (not just a unit test of the context manager
    in isolation).
18. **No mobile navigation at all** — the sidebar was `hidden` below the `md`
    breakpoint with no replacement, so the app was unusable on a phone/tablet
    despite `docs/01_REQUIREMENTS.md` listing mobile access as in scope.
    Fixed with a hamburger + slide-in drawer.
19. **Dashboard had no loading or error state** — on a cold load (or a
    backend hiccup) it silently rendered with `undefined` data feeding
    every child component instead of showing anything explicit. Fixed.
20. **Replay had no persistence** (the #1 remaining item from the first
    pass): an in-progress session lived only in a process-local dict, so an
    API restart silently lost it — verified by actually killing and
    restarting the backend mid-session in a browser test and confirming the
    session survived. Fixed with `ReplaySession`/`ReplayTrade` tables
    (migration `0af22da3af76`).
21. **Replay scoring was profit/loss only** (the other half of the #1 item):
    grading a decision by whether it happened to be followed by a favorable
    move rewards outcome, not process, which is explicitly the wrong thing
    to train on (a good decision can still lose; a bad one can still win).
    Fixed with `judge_decision()` — a pure function that only ever looks at
    information available *at decision time* (direction/score alignment,
    risk-reward, a decided SKIP's rationale) and never takes a P&L or
    outcome argument at all, structurally guaranteeing it can't leak
    hindsight into the verdict. Produces a 3-tier 良い判断/普通/危険な判断
    verdict with a per-criterion breakdown shown in the UI.
22. **Paper Trading filled every order instantly at the exact current
    price with no slippage and no order types** (the #2 remaining item):
    unrealistic versus a real broker, and blocked ever testing a limit/stop
    strategy in Paper mode. Fixed: market orders now fill with
    `PAPER_SLIPPAGE_PIPS` adverse slippage (ask+slip for BUY, bid-slip for
    SELL); limit/stop orders create a pending order with no position until a
    10s worker poll sees the trigger price crossed, re-checking the kill
    switch at fill time (not just at placement time, which would otherwise
    let a kill-switch activation after placement still fill later).
23. **No automated end-to-end coverage of the actual user journey** — every
    verification in this review (and the prior one) was an ad hoc Playwright
    script that ran once and left no trace. Fixed:
    `frontend/e2e/full-flow.spec.ts`, a committed Playwright suite that
    drives a real browser through Dashboard → Markets → Chart → Signals →
    Replay (decide + judgment) → Simulation → Backtest → Paper order (fill +
    close) → Trade journal → Analytics → Kill Switch (armed then disarmed).
    Wired into CI as an advisory (non-blocking) job — see
    `docs/18_E2E_TESTING.md` for why it isn't a required gate.

Grade updates from this pass:

| Area | Grade | Why |
|---|---|---|
| Replay | **A (up from C)** | Both reasons it was held at C are now closed: DB-backed persistence (verified by an actual process-restart test, not just a claim) and non-outcome-based 3-tier judgment scoring. |
| Paper Trading | **A (up from B)** | Slippage modeling and limit/stop pending orders (with kill-switch re-check at fill time) close the gap noted in the first pass. Partial fills remain out of scope, same as real small-account retail execution. |
| Observability | **A (up from B)** | The System page now surfaces every dependency `02_SYSTEM_ARCHITECTURE.md` describes (DB/Redis/Worker/WS-clients/last-price/last-signal), and the `order_id` structured-log field is now actually populated instead of silently always null. |
| Testing | **A (unchanged, but substantively broader)** | 149 backend tests (up from 112), 7 frontend unit tests, plus a committed and CI-wired end-to-end suite covering the full user journey in one real-browser run — not just ad hoc verification during development. |

One thing worth recording precisely because it wasted time during this
pass: running `npm run build` (production build) while a `next dev` server
for the same project is still running corrupts the dev server's `.next/`
output and makes it serve broken pages until restarted — not a bug in this
app, a general Next.js gotcha, but it produced a confusing false "Broker
disconnected" reading on the Dashboard mid-review that had nothing to do
with the broker. Restarting the dev server resolved it immediately; noted
here so it isn't mistaken for a real regression if seen again.

## Update — a fourth pass: cloud migration readiness (P1–P6)

This pass had a different mandate than the first three: not "is the app
correct," but "is the app safe to actually run continuously in the cloud."
Six priorities (P1–P6), worked in sequence, each following
現状確認→脆弱性確認→設計→実装→Migration→Test→E2E→障害試験→ドキュメント更新
(current-state check → vulnerability check → design → implementation →
migration → test → E2E → failure testing → doc update) rather than design
docs alone. Full detail lives in the docs cited per section; this is the
consolidated finding+grade record.

**P1 — Backend-for-Frontend migration.** The browser no longer holds any
backend secret. `frontend/src/app/api/backend/[...path]/route.ts` proxies
every REST call same-origin, attaching the real bearer token server-side;
`frontend/src/app/api/ws-ticket/route.ts` mints a short-lived (45s),
single-use WebSocket ticket (`app/ws/tickets.py`, Redis `GETDEL` — atomic
read+delete, structurally un-replayable) in place of the old long-lived
shared token the browser used to hold directly. Browser session auth is a
signed, stateless HMAC-SHA256 cookie (`frontend/src/lib/session.ts`, Web
Crypto so it runs in Edge middleware) — `HttpOnly`/`sameSite=strict`/
`Secure` outside dev — decoupled from the login password itself (leaking
the cookie doesn't hand over the password or vice versa). WS handshakes
also now check `Origin` explicitly (`app/ws/auth.py`), since Starlette's
WS routes don't run through `CORSMiddleware`. Verified live end-to-end
(curl + a real WebSocket + a full Playwright login→dashboard→logout
run), not just designed. See `docs/11_SECURITY.md` "BFF migration".

**P2 — Staging environment.** `deploy.yml` now requires an explicit
`environment` input (`staging`/`production`, no default) so a bad manual
trigger can't accidentally target production; Railway Environments and a
separate Vercel project are documented as the isolation mechanism
(`docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` "6. Staging environment").
Staging gets its own boot guard: `APP_ENV=staging` with
`LIVE_TRADING_ENABLED=true` now refuses to start at all
(`app/main.py`, `backend/tests/test_boot_guards.py`) — staging can never
place a real order even by misconfiguration.

**P3 — Deployment manifest verification.** Found and fixed a real bug:
`NEXT_PUBLIC_WS_URL` was declared in `docker-compose.yml`'s
runtime-only `environment:` block, which Next.js's build-time inlining
never sees — the Dockerfile now takes it as a build `ARG`. Also
identified (and explicitly flagged as unverified, not silently assumed)
a Railway config-precedence risk: `railway.toml`'s `[deploy]` block may
override a dashboard-set worker Start Command, since the worker shares
the API's root directory; `docs/17` now tells the operator exactly what
log line proves which is actually running. Vercel Preview deployments are
now documented as locked to Mock/Staging only, never Production
resources.

**P4 — Long-running and chaos testing.** Built and actually ran (not just
designed) `backend/scripts/soak_test.py` and `backend/scripts/chaos_test.py`
against the live local stack: 120,000 simulated ticks at ~549/sec with
+0.4MB RSS growth (no leak) and a stable DB pool; 12/12 chaos checks
passed (Redis down, Postgres down, a 1000-tick abnormal-price flood, rate
limiting, worker kill, API kill) — each with the actual detection/recovery
behavior recorded, not assumed. See `docs/19_LONG_RUNNING_AND_CHAOS_TESTING.md`
for the full dated results and an honest "what this does not confirm"
section (no full-stack broker-disconnect chaos, no real multi-day soak).

**P5 — Fail-closed trading safety audit.** Found and fixed two real
fail-open bugs: `submit_paper_order`'s `price_stale` flag was computed as
`not broker_connected` (a broker call returning HTTP 200 with a stale
cached quote was never flagged), and `OandaAdapter.get_current_price()`
stamped quotes with local receive-time instead of OANDA's own quote
timestamp — both fixed with regression tests
(`docs/10_RISK_MANAGEMENT.md` "Fail-closed audit findings"). Added
`GET /live/preflight` (independent auth/account/per-instrument checks,
never places an order) and `POST /live/orders/preview` (runs the real
Risk Engine + broker account/price/position lookup, but contains no call
to `BrokerAdapter.create_order` anywhere in its body — a structural
guarantee, tested with a broker double whose `create_order` raises if
ever invoked). Implemented and unit-tested a GMO Coin Private API request
signer (`app/brokers/gmo_coin.py::generate_private_api_signature`) while
being explicit that it has not been verified against a real funded
account or the live official docs (blocked by anti-bot protection both
this pass and the prior one, per `docs/16_BROKER_SELECTION_REVIEW.md`).

**P6 — Audit log and operations documentation.** A new `audit_logs` table
and `app/services/audit.write_audit_log()` record a closed, named set of
sensitive actions (login/logout, kill switch on/off, risk setting
changes with before/after diffs, LIVE trading admin enable/disable, LIVE
order preview/reject) — surfaced on the System page, verified live by
toggling the Kill Switch in a real browser and confirming both entries
appeared with correct diffs. Found and fixed a second real bug in the
process: `deactivate_kill_switch` (and part of `activate_kill_switch`)
committed the DB session *before* adding a `SystemEvent` log row, and
`get_db()` does not auto-commit on session close — that log row was
silently never persisted; the same bug would have dropped the new audit
entries too if not caught. Backup/restore was verified for real (not just
documented): `pg_dump` the live dev DB → `pg_restore` into a disposable
database → row counts and exact `audit_logs` content confirmed identical
via `diff`. New docs: `docs/20_DISASTER_RECOVERY.md` (per-failure-mode
automatic-vs-manual procedures), `docs/21_OPERATIONS_RUNBOOK.md`
(daily/weekly/monthly operator checks), `docs/22_PRODUCTION_CHECKLIST.md`
(pre-deploy checkboxes), and `backend/scripts/deploy_smoke_test.py` (a
real post-deploy smoke test — login through the BFF, REST through the
proxy, WS ticket mint, and a live WebSocket tick — driven by
`STAGING_BASE_URL`/`STAGING_WS_URL`/`STAGING_LOGIN_TOKEN`; verified for
real against a local staging-config backend+frontend pair, 9/9 checks
passing, including finding and fixing a real bug in the script itself —
the WS routes are mounted without the `/api/v1` prefix REST routes use).

Grade updates from this pass:

| Area | Grade | Why |
|---|---|---|
| Security | A (raised from B) | The one named residual gap from the third pass — "a materially stronger boundary (BFF) so the browser never holds the real bearer token at all" — is now closed and verified live. WS auth is short-lived/single-use instead of a long-lived shared token. Session cookie is signed and decoupled from the login password. |
| Deployment | B (unchanged) | Staging separation, deployment-manifest verification, and a real deploy smoke test are all now in place — but still B, not A: no actual cloud deploy was executed from this sandbox (no cloud credentials available here), and the Railway worker config-precedence question remains unverified against the real platform (documented as an explicit operator verification step rather than resolved). |
| Broker Integration | B (unchanged) | GMO Coin's Private API signer is now implemented and unit-tested, narrowing the stub from "not started" to "implemented, unverified against a live account" — still needs a funded account to close out fully. OANDA path gained a real fail-open fix (quote timestamp source). |
| Testing | A (unchanged) | 189 backend tests (up from 149), 12 frontend unit tests, 12/12 Playwright E2E, plus two new categories of testing this pass didn't have before: a real soak test (120k ticks) and a real chaos test (12 fault-injection scenarios) — both executable on demand, not one-off manual runs. |
| Observability | A (unchanged) | Audit log is a new, distinct capability from the existing structured logging / `/health` / `/ready` / `/metrics` — covered under Security above, not a grade change to this row. Metrics remain JSON-only (no Prometheus exposition format) and the specific counters requested this pass (`price_updates_total`, `orders_rejected_total`, etc.) were not added — see "Honest list of what's still open" below. |

New real bugs found and fixed this pass, beyond the two already-graded
areas above: the `NEXT_PUBLIC_WS_URL` Docker build-arg gap (P3) and the
`deactivate_kill_switch` commit-ordering bug (P6) — bringing this
project's total count of real, verified, fixed findings (not just
theoretical concerns) across all four review passes to date well past a
dozen, consistent with this review's established pattern of finding
problems by actually building and exercising things rather than reading
code and assuming it's correct.

**Not reached this pass** (§33–36 of the requesting instruction — see
"Honest list of what's still open" below for the specific items):
Metrics additions beyond what already exists, a dedicated Performance
Test (concurrent WS/price-update-rate load), Backtest Resource Control
(so a heavy backtest can't degrade the realtime path), and a formal
consolidated Production Preflight v2 tool that reports PASS/WARN/FAIL and
can refuse startup/deployment on FAIL (`/live/preflight` and the
`app/main.py` boot guards cover pieces of this today, but not as one
consolidated tool).

## What "A" does and doesn't mean here

An **A** means: the code does what it claims, is covered by a test that would
fail if it regressed, and was independently exercised (not just read) during
this review. It does **not** mean "battle-tested in a real funded live
account" — nothing in this app has traded real money, by design (LIVE stays
disabled by default; see `10_RISK_MANAGEMENT.md`). Treat every grade here as
"correct as built and verified," not as a guarantee about real-market
behavior once a live broker account is eventually connected.

## Honest list of what's still open after this pass

See `docs/14_IMPLEMENTATION_PLAN.md` for the full running list; the delta
this pass didn't close:

- `GmoCoinAdapter` still a stub (needs a funded account) — re-confirmed this
  pass that GMO Coin's FX API is real and distinct from its crypto API (see
  `docs/16_BROKER_SELECTION_REVIEW.md`), so the stub is a "needs an account
  to finish, not a wrong-API mistake" gap, not a design problem.
- Paper Trading partial fills — a limit/stop order fills entirely-or-not at
  the current poll tick; no partial-fill simulation. Documented as an
  extension point in `order_orchestrator.py`, not built.
- ~~A materially stronger security boundary (routing all API/WS traffic
  through a backend-for-frontend so the browser never holds the real bearer
  token)~~ — implemented this pass (P1); see "a fourth pass" update above
  and `docs/11_SECURITY.md` "BFF migration".
- Realtime heartbeat frame independent of tick traffic — noted in the first
  pass, still not built (low practical risk for FX, see the Realtime row
  above).
- No actual cloud deployment executed from this environment (no cloud
  credentials available in this sandbox) — `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md`
  has the exact steps for the operator to run themselves; this pass adds a
  real smoke test (`backend/scripts/deploy_smoke_test.py`) to run
  immediately after that deploy actually happens.
- Metrics counters beyond what `/metrics` already exposes
  (`price_updates_total`, `price_stale_total`, `signals_generated_total`,
  `orders_requested_total`, `orders_rejected_total`,
  `paper_orders_filled_total`, `broker_errors_total`,
  `websocket_connections`, `worker_heartbeat_age`, `db_pool_usage`) — not
  added this pass; `/metrics` today is JSON with uptime/broker-connected/
  per-instrument last-tick only.
- A dedicated Performance Test (50 concurrent WS connections, ~100
  price updates/sec, multi-pair load, large history rendering, concurrent
  Backtest execution) — not run this pass. The soak test (P4) covers
  sustained single-stream throughput and leak detection, which is a
  different question from concurrent-load performance.
- Backtest Resource Control (queue/concurrency limit/timeout/cancel so a
  heavy Backtest run can't degrade the realtime Worker/API/WebSocket path)
  — not built this pass; Backtest still runs synchronously in-process on
  the same event loop as everything else (`docs/05_API_DESIGN.md`
  "Backtest").
- A consolidated Production Preflight v2 tool reporting PASS/WARN/FAIL and
  able to refuse startup/deployment on FAIL — not built as one tool this
  pass. The individual pieces exist and are real (`GET /live/preflight`,
  the `app/main.py` boot guards for missing tokens and staging+LIVE
  misconfiguration, `GET /ready`), but nothing consolidates them into a
  single pass/warn/fail report an operator or CI step can gate on.
- ~~Signal outcome history tracking (did a BUY 80+ signal actually work out?)
  and the corresponding Analytics score-bucket accuracy view~~ — implemented
  in a later pass; see `docs/08_SIGNAL_ENGINE.md` "Signal outcome history".
- ~~Walk-Forward Analysis (designed, not implemented)~~ — implemented in a
  later pass; see `docs/09_BACKTEST_DESIGN.md` "Walk-Forward Analysis".
- ~~Replay session/trade persistence + qualitative judgment scoring~~ —
  implemented this pass; see "a third pass" update above.
- ~~Paper trading slippage model and limit/stop order types~~ — implemented
  this pass; see "a third pass" update above.
