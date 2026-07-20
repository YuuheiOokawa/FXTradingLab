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
  `/api/v1/*` and `/ws/*` requests when `APP_ENV != development`. Local dev skips this
  for convenience (documented, not silently different in prod — enforced by a startup
  assertion that refuses to boot with auth disabled while `APP_ENV=production`).
- The `users` table exists for future multi-operator support but is not wired to a
  login flow in v1 — this is called out explicitly as a non-goal in `01_REQUIREMENTS.md`.

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
