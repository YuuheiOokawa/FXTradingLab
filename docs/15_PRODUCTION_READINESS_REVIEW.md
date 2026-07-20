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
| Replay | C | Functionally correct (candles are revealed one at a time, no future data reaches the frontend) but state is in-process/in-memory only, not persisted — a server restart loses an in-progress session. `ReplaySession`/`ReplayTrade` DB persistence and the requested 3-tier qualitative judgment scoring (良い判断/普通/危険な判断, vs. raw P&L) are designed but not implemented this pass — see `14_IMPLEMENTATION_PLAN.md`. |
| Paper Trading | B | Already fills at bid/ask (not mid) with the current live quote, already goes through the same Risk Engine as everything else, already rejects with a clear typed error. Gap: no explicit slippage model (backtest has one, paper trading doesn't) and only market orders are modeled (no limit/stop pending-order book) — both documented as extension points, not implemented this pass. |
| Risk Engine | A | 10 checks, now with stress tests beyond the original per-rule unit tests: broker disconnect at entry and at close, daily-loss-limit and consecutive-loss-stop computed from real journal rows, max-concurrent-positions across distinct instruments — all exercised through the real submit/close flow against the real test database. |
| Security | B | Bearer-token REST+WS auth, CORS allowlist, secret redaction in logs, and a single-shared-secret frontend login gate are all real and tested. This is intentionally a single-operator model, not multi-user auth (out of scope per `01_REQUIREMENTS.md`) — appropriate for who this app is built for, but worth being explicit that it is not a general-purpose multi-tenant auth system. No rate limiting on the REST API (a determined actor with the token could hammer it) — acceptable for a single-operator personal deployment, would need addressing before wider exposure. |
| Observability | B | Structured logging with request-id correlation, `/health`, `/ready` (real DB+Redis checks), `/metrics`, and a System page showing uptime/last-error, all added and tested this pass. No log shipping/alerting configured (expected — that's a deployment-time operator choice, not something to bake into the app). |
| Deployment | B | Docker Compose validated end-to-end locally (all 5 services). Dockerfiles, Railway/Vercel config present. No actual cloud deploy was performed from this sandbox (no cloud credentials available) — see `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md` for the exact operator steps. |
| Testing | A | 89 backend tests (pytest, real Postgres) + 7 frontend unit tests, all passing; full-stack browser verification performed repeatedly throughout this review, not just once at the end. |

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

- `GmoCoinAdapter` still a stub (needs a funded account).
- Replay session/trade persistence + qualitative judgment scoring.
- ~~Signal outcome history tracking (did a BUY 80+ signal actually work out?)
  and the corresponding Analytics score-bucket accuracy view~~ — implemented
  in a later pass; see `docs/08_SIGNAL_ENGINE.md` "Signal outcome history".
- ~~Walk-Forward Analysis (designed, not implemented)~~ — implemented in a
  later pass; see `docs/09_BACKTEST_DESIGN.md` "Walk-Forward Analysis".
- Paper trading slippage model and limit/stop order types.
- No actual cloud deployment executed from this environment.
