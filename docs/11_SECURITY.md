# 11. Security

## Security Review

Explicit review pass across the dimensions requested for this app's
production-readiness check, done by reading and exercising the real code
(not assuming from the design) — see `docs/15_PRODUCTION_READINESS_REVIEW.md`
for the broader review this was part of.

| Dimension | Status | Notes |
|---|---|---|
| CORS | Fixed this pass | `ALLOWED_ORIGINS` allowlist, safe-by-default (blocks all cross-origin traffic when unset outside dev) — see "CORS" below. |
| CSRF | Low risk by construction | The backend never uses a cookie for its own auth decision — `require_auth` only accepts an `Authorization: Bearer` header, which a cross-site page cannot attach to a request it forges (unlike a cookie, headers aren't auto-sent by the browser). The frontend's own `fxlab_token` cookie is `sameSite: strict`, so it isn't sent on cross-site requests either. No CSRF token scheme is implemented because there's no cookie-based session for the API to protect against forged requests in the first place. |
| XSS | No app-specific finding | React escapes all rendered data by default; no `dangerouslySetInnerHTML` / raw HTML injection anywhere in the frontend (verified by search). The AI explanation text (`docs/08_SIGNAL_ENGINE.md`) is rendered as plain text, not HTML. Standard residual risk: a dependency-introduced XSS would still be able to read `NEXT_PUBLIC_APP_API_TOKEN` out of the page's own JS — see "Frontend login gate" below for why that's an inherent property of this architecture, not something a CSP alone fixes. |
| SQL injection | Not applicable | SQLAlchemy ORM / parameterized queries exclusively; no raw string-interpolated SQL anywhere in the codebase (verified by search for `.execute(f"` / `% (` patterns — none found). |
| Secret leakage | Fixed this pass (real vuln found) | A real, exploitable secret-leakage bug was found and fixed in the frontend login gate — the shared token was readable by anyone who merely visited the (necessarily public) `/login` page, without ever needing to know it first. See "Frontend login gate" below for the full writeup. Log redaction (`app/core/logging.py`) was already in place and re-verified. |
| Dependency vulnerabilities | Fixed this pass | `pip-audit` (backend) and `npm audit` (frontend) are now real CI steps (`.github/workflows/ci.yml`), not just documented as intended — previously this doc claimed they were already wired in when they weren't (verified against the actual workflow file, found the gap, fixed it). Both are advisory (non-blocking) for the same reason `ruff` is — see "Dependency & CI hygiene" below. |
| API authentication | Pass | Bearer token required on every `/api/v1/*` route outside development (`require_auth`), tested. |
| Rate limiting | Fixed this pass (real gap found) | `docs/15_PRODUCTION_READINESS_REVIEW.md` explicitly flagged "no rate limiting on the REST API" as an open gap. Closed this pass: `app/api/rate_limit.py`, a Redis-backed fixed-window limit (120 req/min/identity by default, `RATE_LIMIT_PER_MINUTE`), keyed by bearer token (falling back to client IP only when auth is disabled), fails open on a Redis outage, skipped in development. Tested in `tests/test_rate_limit.py`. WebSocket connection *attempts* are not separately rate-limited (a gap, not fixed this pass — lower priority since each one still requires the same valid token). |
| WebSocket authentication | Pass (fixed in the prior review pass) | `?token=` query-param check before `accept()`, tested — see "AuthN/Z" below. |
| Admin operations | N/A by design | This app has no separate "admin" role or admin-only endpoint surface distinct from the single operator's own bearer token — every authenticated request is already the one operator. The closest analogue, the kill switch (`POST /live/kill-switch`), requires the same bearer token as everything else and is documented as always available regardless of other gate state (`docs/10_RISK_MANAGEMENT.md`). |
| LIVE trading operations | Pass | Three independent gates required before any real order can be submitted (`LIVE_TRADING_ENABLED=true` env var, `BROKER_ENVIRONMENT=live`, explicit UI confirmation) — see `docs/10_RISK_MANAGEMENT.md`. The frontend shows a persistent red warning banner (`components/layout/live-trading-banner.tsx`) whenever `live_trading_enabled_env` is true, sourced from `GET /system/status`, so LIVE-armed state is never silently invisible in the UI. |

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
  the browser handshake, so they instead require the same token as a `?token=`
  query param, checked by `app/ws/auth.py::check_ws_auth` before `accept()` — this
  was found to be **only documented, not actually implemented**, during the
  production-readiness review (`docs/15_PRODUCTION_READINESS_REVIEW.md`) and has
  since been fixed and covered by `tests/test_ws_auth.py`. Local dev skips both for
  convenience (documented, not silently different in prod — enforced by a startup
  assertion that refuses to boot with REST auth disabled while `APP_ENV=production`).
- The frontend sends this same token in two ways: `Authorization: Bearer` for REST
  (`frontend/src/lib/api.ts`) and `?token=` for WebSocket (`wsUrl()` in the same
  file) — both read from `NEXT_PUBLIC_APP_API_TOKEN`. See "Frontend login gate"
  below for how an operator actually gets that token into the browser.
- The `users` table exists for future multi-operator support but is not wired to a
  login flow in v1 — this is called out explicitly as a non-goal in `01_REQUIREMENTS.md`.
  What v1 *does* have (added in the production-readiness pass) is a lightweight
  password-style gate in front of the whole frontend — see below — which is enough
  to satisfy "don't expose an internet-facing personal app with zero auth prompt"
  without building real multi-user accounts.

## Frontend login gate

`frontend/src/app/login/page.tsx` prompts for the same value as the backend's
`APP_API_TOKEN`; `frontend/src/middleware.ts` redirects every other route to
`/login` if a matching `fxlab_token` cookie isn't present. This is not a real
multi-user auth system — it's a single shared secret, appropriate for the
single-operator model this app targets — but it means the app is never
reachable by an anonymous visitor who just finds the URL. Skipped entirely in
development (`APP_API_TOKEN` unset ⇒ middleware no-ops) so local iteration
doesn't require logging in every time.

**Real vulnerability found and fixed during the security review requested
alongside `docs/15_PRODUCTION_READINESS_REVIEW.md`**: the original
implementation compared the submitted token against
`NEXT_PUBLIC_APP_API_TOKEN` directly inside `login/page.tsx`'s own client
component. `NEXT_PUBLIC_`-prefixed env vars are inlined verbatim into
whichever client JS bundle references them — that's what the prefix means in
Next.js, not a bug, but it made the *comparison value* itself part of the
`/login` page's own downloadable JavaScript. Since `/login` must always be
reachable by a not-yet-authenticated visitor (that's the entire point of a
login page), anyone — with no prior knowledge of the token — could load
`/login`, view its script tag, fetch that one JS file, and read the real
shared secret straight out of it in plaintext. Verified exploitable
end-to-end during this review (built the app, fetched `/login`'s compiled
chunk, grepped the token out of it) before fixing it — this was not a
theoretical concern.

Fixed by moving the comparison server-side:
- `frontend/src/app/api/session-login/route.ts` (new) — a Route Handler that
  runs only on the server and compares the submitted value against
  `APP_API_TOKEN`, a **separate, server-only** env var with no
  `NEXT_PUBLIC_` prefix, so it is never inlined into any client-shipped file.
  On a match it sets `fxlab_token` as an `httpOnly` cookie (page JS,
  including a hypothetical XSS payload, cannot read it) via the response
  header only — its value never appears as a literal in any file the
  browser downloads.
- `login/page.tsx` no longer contains any comparison logic or the expected
  token value at all; it just POSTs the entered value to that endpoint.
- `middleware.ts` now checks the cookie against the same server-only
  `APP_API_TOKEN` instead of the `NEXT_PUBLIC_` copy.
- `middleware.ts`'s `PUBLIC_PATHS` had to explicitly add
  `/api/session-login` itself (in addition to `/login`) — otherwise the
  login endpoint would redirect-loop against its own gate, since nothing
  could ever obtain the cookie the middleware requires.

Verified post-fix (built the production bundle with a real token value and
inspected the output directly, not just read the diff): the token string no
longer appears anywhere under `.next/static/chunks/app/login/`. It still
appears in the bundles for pages *behind* the login gate (`dashboard`,
`markets`, etc.), because `lib/api.ts` still needs the real token client-side
to call the backend API/WebSocket directly — that remains unavoidable in
this frontend-directly-calls-backend architecture (see "What this does NOT
protect against" below), but those bundle files are named with an
unguessable content hash and are only ever referenced by HTML that is itself
gated, so an unauthenticated visitor has no path to their filename. The one
concretely exploitable path — the always-public `/login` page leaking the
secret through its own bundle — is what's fixed.

**What this does and does not protect against**: this remains a shared
static secret, not a cryptographic credential — anyone who already knows the
token (i.e., anyone who has legitimately logged in once) can always read it
back out of their own browser's downloaded JS for the pages behind the gate,
same as they could read back any password they typed into a form they
control. That is expected and not a new disclosure. What the fix above
closes is specifically the ability for someone who does **not** already know
the token to obtain it just by visiting the site. For a deployment where
even that residual "a logged-in user's own browser holds the real bearer
token in cross-origin-callable form" risk matters (e.g. a shared/borrowed
device, or genuine concern about a targeted attacker rather than an
opportunistic scanner), the real fix is architectural — route all API/WebSocket
traffic through the frontend's own origin with the backend token attached
server-side only, so the browser never needs to hold the real secret at all.
That is a substantially larger change (effectively a backend-for-frontend
proxy, complicated further by this app's WebSocket price stream — see
`docs/12_DEPLOYMENT.md`'s note on why Vercel Functions aren't a good home for
long-lived WebSocket connections) and was not built this pass; for a
personal, not-publicly-advertised deployment the fix above is judged
sufficient. An operator who wants a materially stronger boundary today,
without an app-level rewrite, should put a platform-level access control in
front of the whole deployment — e.g. Vercel's Deployment Protection /
password protection (Pro-plan "Advanced Deployment Protection" add-on or
Enterprise; not available on Hobby as of this writing — verify current
availability at
[vercel.com/docs/deployment-protection](https://vercel.com/docs/deployment-protection)
before relying on this), a Cloudflare Access application, or a VPN/Tailscale
in front of both the frontend and backend domains.

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
