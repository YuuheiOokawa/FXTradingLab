# 11. Security

## Security Review

Explicit review pass across the dimensions requested for this app's
production-readiness check, done by reading and exercising the real code
(not assuming from the design) — see `docs/15_PRODUCTION_READINESS_REVIEW.md`
for the broader review this was part of.

| Dimension | Status | Notes |
|---|---|---|
| CORS | Fixed | `ALLOWED_ORIGINS` allowlist, safe-by-default (blocks all cross-origin traffic when unset outside dev) — see "CORS" below. Largely moot for REST now that the browser only ever calls this app's own origin (see "BFF migration"); still enforced for the WS handshake's Origin header. |
| CSRF | Low risk by construction | The backend's own auth (`require_auth`) never uses a cookie — only a bearer header, which a cross-site page cannot forge (headers aren't auto-attached the way cookies are). The frontend's session cookie is `sameSite: strict`, so it isn't sent on cross-site requests either, and it authenticates the browser to the *frontend*, not directly to the backend (see "BFF migration"). No CSRF token scheme is implemented because neither layer relies on an auto-attached credential a forged cross-site request could exploit. |
| XSS | No app-specific finding | React escapes all rendered data by default; no `dangerouslySetInnerHTML` / raw HTML injection anywhere in the frontend (verified by search). The AI explanation text (`docs/08_SIGNAL_ENGINE.md`) is rendered as plain text, not HTML. **Materially reduced residual risk from the BFF migration**: the backend bearer token no longer reaches the browser in any form — it lived only in `NEXT_PUBLIC_APP_API_TOKEN` before, readable by any script running in the page; now it exists only in server-only env vars a browser-side XSS payload has no path to at all. A successful XSS can still ride the session cookie's ambient auth for as long as that page is open (same as any cookie-authenticated app), but it can no longer exfiltrate a durable backend credential to replay later. |
| SQL injection | Not applicable | SQLAlchemy ORM / parameterized queries exclusively; no raw string-interpolated SQL anywhere in the codebase (verified by search for `.execute(f"` / `% (` patterns — none found). |
| Secret leakage | Fixed (two real vulns found across two review passes) | (1) The original frontend login gate leaked the shared token to anyone who merely visited the always-public `/login` page (fixed by moving the comparison server-side — see "BFF migration" for the current, further-hardened state). (2) The backend bearer token itself was, by architecture, held directly by the browser (`NEXT_PUBLIC_APP_API_TOKEN`, sent as `Authorization: Bearer` and a WS `?token=` param) — not a bug exactly, since that's what `NEXT_PUBLIC_` vars are for, but it meant any XSS or malicious browser extension had a direct path to a long-lived credential. Closed by the BFF migration below: the browser now holds neither the backend token nor the raw login password, only a signed, time-limited session cookie. Log redaction (`app/core/logging.py`) was already in place and re-verified. |
| Dependency vulnerabilities | Fixed | `pip-audit` (backend) and `npm audit` (frontend) run as real CI steps (`.github/workflows/ci.yml`). Both are advisory (non-blocking) for the same reason `ruff` is — see "Dependency & CI hygiene" below. |
| API authentication | Pass | Bearer token required on every `/api/v1/*` route outside development (`require_auth`), tested. Since the BFF migration, only the frontend's own server ever sends this header — see "BFF migration". |
| Rate limiting | Pass | `app/api/rate_limit.py`, a Redis-backed fixed-window limit (120 req/min/identity by default, `RATE_LIMIT_PER_MINUTE`), keyed by bearer token (falling back to client IP only when auth is disabled), fails open on a Redis outage, skipped in development. Tested in `tests/test_rate_limit.py`. WebSocket connection *attempts* are not separately rate-limited (a gap, not fixed this pass — lower priority since each one still requires a freshly minted, per-request-authenticated ticket). |
| WebSocket authentication | Fixed (hardened this pass) | Previously a long-lived shared bearer token as `?token=` — replaced with a short-lived (45s), single-use ticket (`app/ws/tickets.py`) plus an Origin-header allowlist check, both tested (`tests/test_ws_auth.py`). See "BFF migration". |
| Admin operations | N/A by design | This app has no separate "admin" role or admin-only endpoint surface distinct from the single operator's own bearer token — every authenticated request is already the one operator. The closest analogue, the kill switch (`POST /live/kill-switch`), requires the same bearer token as everything else and is documented as always available regardless of other gate state (`docs/10_RISK_MANAGEMENT.md`). |
| LIVE trading operations | Pass | Three independent gates required before any real order can be submitted (`LIVE_TRADING_ENABLED=true` env var, `BROKER_ENVIRONMENT=live`, explicit UI confirmation) — see `docs/10_RISK_MANAGEMENT.md`. The frontend shows a persistent red warning banner (`components/layout/live-trading-banner.tsx`) whenever `live_trading_enabled_env` is true, sourced from `GET /system/status`, so LIVE-armed state is never silently invisible in the UI. `APP_ENV=staging` additionally refuses to boot at all if `LIVE_TRADING_ENABLED=true` (`app/main.py` lifespan guard) — see `docs/15_PRODUCTION_READINESS_REVIEW.md` "Staging environment". |

## Secrets

- All credentials (`BROKER_API_TOKEN`, `BROKER_ACCOUNT_ID`, `DATABASE_URL`,
  `REDIS_URL`, `AI_API_KEY`, `APP_API_TOKEN`) are read only from environment
  variables via `app/core/config.py` (pydantic-settings). None are hardcoded, none are
  committed — `.env` is gitignored, `.env.example` documents every variable with a
  placeholder value.
- Broker tokens are never sent to, or requested from, the browser. Every broker call
  originates in the backend; the frontend only ever talks to `/api/v1/*` and `/ws/*`
  on this app's own backend.
- `app/core/logging.py` installs a redaction filter that masks any string matching
  known token/secret env var values (and common patterns like `Bearer <token>`)
  before it reaches a log sink, so even an accidental `logger.debug(request)` can't
  leak a token.

## AuthN/Z

- Single-operator model: `APP_API_TOKEN` is a bearer token required on all
  `/api/v1/*` requests when `APP_ENV != development` (`app/api/deps.py::require_auth`).
  WebSocket endpoints (`/ws/prices`, `/ws/system`) can't carry a request header on
  the browser handshake, so they instead require a short-lived, single-use ticket
  as a `?ticket=` query param, checked by `app/ws/auth.py::check_ws_auth` before
  `accept()` (`app/ws/tickets.py`) — see "BFF migration" below for why this
  replaced an earlier design that used the same long-lived shared token WS did.
  Local dev skips both for convenience (documented, not silently different in a
  real environment — enforced by a startup assertion that refuses to boot with
  auth disabled while `APP_ENV` is `staging` or `production`).
- **Since the BFF migration below, the browser never holds `APP_API_TOKEN` (or
  any equivalent backend credential) in any form.** It authenticates to the
  *frontend's own server* with a signed session cookie; the frontend's server
  is the only thing that ever sends `Authorization: Bearer` to the backend.
- The `users` table exists for future multi-operator support but is not wired to a
  login flow in v1 — this is called out explicitly as a non-goal in `01_REQUIREMENTS.md`.
  What v1 *does* have is a lightweight password-style gate in front of the whole
  frontend (below), enough to satisfy "don't expose an internet-facing personal
  app with zero auth prompt" without building real multi-user accounts.

## BFF migration

Originally (through the first two production-readiness review passes) the
frontend called the FastAPI backend **directly** from the browser: `lib/api.ts`
read a `NEXT_PUBLIC_APP_API_TOKEN` env var — inlined verbatim into the client
JS bundle, since that's what the `NEXT_PUBLIC_` prefix means in Next.js — and
sent it as `Authorization: Bearer` on every REST call and `?token=` on every
WebSocket connection. That is a real, durable backend credential sitting in
browser-reachable JavaScript: readable by any XSS (however unlikely given no
`dangerouslySetInnerHTML` exists in this app), a malicious browser extension,
or simply anyone who opens devtools. Section "Frontend login gate" below
covers a *related* but distinct bug found and fixed earlier — this section
covers removing the underlying architecture that made the token
browser-reachable at all, not just patching one leak of it.

**The fix**: Next.js now sits between the browser and FastAPI as a real
backend-for-frontend, not just a static site that happens to also host a
login page.

```
Browser  →  Next.js server (this app's own origin)  →  FastAPI
```

- **REST**: every call `lib/api.ts` makes goes to this app's own
  `/api/backend/*` (same-origin, so the browser's session cookie is sent
  automatically) instead of the backend's URL directly.
  `app/api/backend/[...path]/route.ts` (a Route Handler, i.e. server-side
  code) forwards it to FastAPI, attaching `Authorization: Bearer
  ${BACKEND_API_TOKEN}` — a server-only env var — itself. The browser never
  constructs this header and the token never appears in any file it
  downloads. Reachability of `/api/backend/*` is gated by `middleware.ts`
  exactly like every other page (see "Frontend login gate"), so an
  unauthenticated request never reaches the proxy at all.
- **WebSocket**: proxying binary WS frames through an HTTP layer wasn't
  judged worth the added latency/complexity for a price-tick stream, so the
  browser still connects **directly** to FastAPI's `/ws/prices` — but with a
  short-lived (45s), single-use ticket instead of the old long-lived shared
  token. The browser `POST`s to this app's own `/api/ws-ticket` (session-cookie
  gated, same as `/api/backend/*`); that Route Handler calls FastAPI's
  `POST /api/v1/system/ws-ticket` (bearer-token gated — only the frontend
  server can call it) to mint one, and hands only the resulting ticket back
  to the browser. A ticket is consumed (deleted from Redis) the instant a
  connection uses it — see `app/ws/tickets.py` — so even though it does
  travel in a URL (browser history, a proxy access log), it's worthless
  within seconds and can never be replayed. `frontend/src/lib/priceSocket.ts`
  fetches a fresh ticket on every (re)connection attempt, since each is
  single-use. The WS handshake's `Origin` header is also checked against
  `ALLOWED_ORIGINS` (`app/ws/auth.py`) — a check that didn't exist before,
  since Starlette's WS routes don't run through `CORSMiddleware`.
- **Session cookie**: also hardened as part of this migration, not left as
  it was. See "Frontend login gate" for the full detail — in short, the
  cookie is now a signed, expiring token (`frontend/src/lib/session.ts`),
  not the literal password, `secure` outside local dev, and there's a real
  logout endpoint (`/api/session-logout`) that didn't exist before.

**What an operator must configure differently as a result** (see
`frontend/.env.local.example` for the authoritative list): `NEXT_PUBLIC_API_URL`
and `NEXT_PUBLIC_APP_API_TOKEN` are gone. In their place: `NEXT_PUBLIC_WS_URL`
(public, not a secret — just the browser-reachable WS hostname),
`BACKEND_API_TOKEN` + `BACKEND_INTERNAL_URL` (server-only — the frontend
server's own credential/address for reaching FastAPI, which can point at a
private-network hostname unreachable from the public internet at all, e.g.
Railway private networking — see `docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md`),
and `SESSION_SECRET` (server-only — signs the session cookie).

**What this still does not protect against**: this is still a single shared
password, not per-user cryptographic credentials — anyone who legitimately
knows the login password can always log in, same as before. What changed is
what a *browser-side* compromise (XSS, a malicious extension, physical access
to an unlocked logged-in device) can obtain: previously, a durable backend
bearer token usable indefinitely from anywhere; now, at most the session
cookie's ambient auth for the remainder of that session's validity window
(sessions are stateless-signed, see `lib/session.ts`'s docstring for why
pre-expiry revocation isn't built — logout clears the browser's copy but
can't invalidate one already exfiltrated). For a deployment where even that
residual risk matters, add a platform-level access control in front of the
whole deployment — e.g. Vercel's Deployment Protection / password protection
(Pro-plan "Advanced Deployment Protection" add-on or Enterprise; not
available on Hobby as of this writing — verify current availability at
[vercel.com/docs/deployment-protection](https://vercel.com/docs/deployment-protection)
before relying on this), a Cloudflare Access application, or a VPN/Tailscale
in front of the frontend domain.

## Frontend login gate

`frontend/src/app/login/page.tsx` prompts for the operator's login password
(`APP_API_TOKEN`, read server-side); `frontend/src/middleware.ts` redirects
every other route to `/login` if a valid, unexpired `fxlab_session` cookie
isn't present. This is not a real multi-user auth system — it's a single
shared password, appropriate for the single-operator model this app targets
— but it means the app is never reachable by an anonymous visitor who just
finds the URL. Skipped entirely in development (`APP_API_TOKEN` unset ⇒
middleware no-ops) so local iteration doesn't require logging in every time.

**Real vulnerability found and fixed during an earlier security review**: the
original implementation compared the submitted token against
`NEXT_PUBLIC_APP_API_TOKEN` directly inside `login/page.tsx`'s own client
component — inlined into that always-public page's own JS bundle, readable
by anyone who merely visited `/login` with zero prior knowledge of the
password. Verified exploitable end-to-end at the time (built the app,
fetched `/login`'s compiled chunk, grepped the token out of it) before fixing
it by moving the comparison server-side into
`frontend/src/app/api/session-login/route.ts`, which compares against the
server-only `APP_API_TOKEN` (no `NEXT_PUBLIC_` prefix) instead.

**Hardened further during the BFF migration above** — the session artifact
itself changed, not just where the comparison happens:
- On a successful login, the cookie set is now a **signed, expiring token**
  (`frontend/src/lib/session.ts`: an HMAC-SHA256-signed
  `{issued-at, expiry}` payload, keyed by `SESSION_SECRET`) — not the literal
  password, as it was before. Knowing the cookie's value no longer tells you
  the login password.
- The cookie (`fxlab_session`) is `httpOnly`, `sameSite: strict`, and now
  also `secure` outside local development (it wasn't marked `secure`
  before — a real gap, since without it the cookie could theoretically be
  sent over a plain-HTTP connection if one ever existed in the request path).
- `POST /api/session-logout` (new) actually clears the cookie — no logout
  endpoint existed before this pass at all.
- `middleware.ts`'s `PUBLIC_PATHS` includes both `/api/session-login` and
  `/api/session-logout` — gating either would make login/logout impossible,
  since nothing could ever obtain or clear the cookie the middleware itself
  requires.

Verified post-fix (built the production bundle with a real password value and
inspected the output directly, not just read the diff): the password string
appears nowhere under `.next/static/` at all now — not even behind the login
gate — since no client code needs it anymore (the old architecture's
`lib/api.ts` needed the *backend* token client-side to call the API
directly; the new one needs nothing).

## CORS

- `ALLOWED_ORIGINS` (comma-separated) controls which browser origins may call the
  API in non-development environments; unset means CORS blocks every cross-origin
  request (safe-by-default), not a wildcard. Same-origin deployments (frontend and
  backend behind one reverse-proxy domain) don't need this set at all. Development
  allows `*` for convenience. See `app/main.py`.

## Transport

- Backend behind HTTPS in every deployed environment (TLS terminated by the
  platform — Railway/Fly/Vercel all provide this by default); local dev is plain HTTP
  on localhost only.
- WebSocket upgrades over the same TLS connection (`wss://`).

## Input validation

- All request bodies are Pydantic models with explicit types/bounds (e.g. position
  size, risk_pct ranges) — FastAPI rejects malformed input before it reaches business
  logic.
- SQLAlchemy ORM / parameterized queries only — no raw string-interpolated SQL.

## Dependency & CI hygiene

- `pip-audit` (backend) / `npm audit` (frontend) run on every push/PR as real
  CI steps (`.github/workflows/ci.yml`) — advisory (non-blocking, `|| true`)
  in v1 given a single-operator project, upgradeable to blocking later.
  **Correction from an earlier version of this doc**: this was previously
  described as already wired in when it wasn't — verified against the actual
  workflow file during the security review above, found neither ran, and
  added both for real rather than just fixing the doc's wording.
- `ruff` (backend) and `eslint` (frontend) also run every PR; `ruff` remains
  advisory pending cleanup of ~39 pre-existing findings (see
  `docs/13_TEST_STRATEGY.md`), `eslint` is gating (added this pass, currently
  clean).

## Data at rest

- No plaintext password storage in v1 (no login flow yet). If/when multi-user auth is
  added, this doc's update must specify `bcrypt`/`argon2` hashing before that ships.
- Trade journal and account data are financial but not PII-heavy; DB access itself is
  restricted at the network level by the hosting platform (no public Postgres port).
