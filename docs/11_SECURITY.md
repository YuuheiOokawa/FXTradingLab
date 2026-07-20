# 11. Security

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

`frontend/src/app/login/page.tsx` prompts for the same `APP_API_TOKEN` value the
backend expects, stores it in a cookie (`fxlab_token`, `httpOnly: false` since
client-side JS needs to attach it to `fetch`/WebSocket calls, `sameSite: strict`),
and `frontend/src/middleware.ts` redirects every other route to `/login` if that
cookie is missing. This is not a real multi-user auth system — it's a single
shared secret, appropriate for the single-operator model this app targets — but it
means the app is never reachable by an anonymous visitor who just finds the URL.
Skipped entirely in development (`NEXT_PUBLIC_APP_API_TOKEN` unset ⇒ middleware
no-ops) so local iteration doesn't require logging in every time.

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

- `pip-audit` / `npm audit` runnable locally and wired as a CI step
  (`.github/workflows/ci.yml`) — advisory (non-blocking) in v1 given a single-operator
  project, upgradeable to blocking later.

## Data at rest

- No plaintext password storage in v1 (no login flow yet). If/when multi-user auth is
  added, this doc's update must specify `bcrypt`/`argon2` hashing before that ships.
- Trade journal and account data are financial but not PII-heavy; DB access itself is
  restricted at the network level by the hosting platform (no public Postgres port).
