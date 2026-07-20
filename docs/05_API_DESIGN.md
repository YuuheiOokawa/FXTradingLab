# 05. API Design

Base URL: `/api/v1`. All responses JSON. Auth: single-operator bearer token
(`APP_API_TOKEN`) checked by middleware in non-dev environments (see `11_SECURITY.md`);
disabled in local dev for convenience.

## REST endpoints (implemented unless marked planned)

### Market
- `GET /instruments` — watchlist + metadata.
- `POST /instruments` / `DELETE /instruments/{symbol}` — add/remove watched pair.
- `GET /instruments/{symbol}/price` — latest bid/ask/mid/spread/day high-low/change.
- `GET /instruments/{symbol}/candles?granularity=H1&count=300` — OHLC series.

### Signals
- `GET /signals/{symbol}?granularity=M15` — latest score + reason breakdown for a pair.
- `GET /signals/{symbol}/history` — recent signal snapshots (for the chart markers).

### Simulation
- `POST /simulate` — start a manual what-if trade simulation.
- `GET /simulate/{id}` — current state (live P/L, MFE/MAE, RR) as it plays forward.
- `POST /simulate/{id}/close` — manual close.

### Replay
- `POST /replay/sessions` — create a replay session (pair, timeframe, start point).
- `POST /replay/sessions/{id}/step` — advance one candle.
- `POST /replay/sessions/{id}/decide` — submit BUY/SELL/skip.
- `GET /replay/sessions/{id}` — current state + (if TRAINING_ON or after a decision)
  rule breakdown.

### Backtest
- `POST /backtests` — submit a backtest job (runs synchronously for v1 given typical
  single-pair/single-year data volumes; long-running jobs are a documented upgrade to
  a queued worker job).
- `GET /backtests/{id}` — summary stats + equity curve.
- `GET /backtests/{id}/trades` — trade list; `GET /backtests/{id}/trades/{trade_id}`
  for the entry/exit rationale.

### Paper trading
- `GET /paper/account` — virtual balance/equity.
- `GET /paper/positions`
- `POST /paper/orders` — place a paper order (goes through Risk Engine).
- `POST /paper/positions/{id}/close`

### Live trading (planned — scaffolded, execution path disabled; see `10_RISK_MANAGEMENT.md`)
- `GET /live/account`, `GET /live/positions`
- `POST /live/orders` — returns `403` unless all three LIVE gates are satisfied.
- `POST /live/kill-switch` — highest-priority endpoint, bypasses normal request queueing
  concerns; always available regardless of other gate state.

### Journal & analytics
- `GET /journal/trades?source=paper&pair=USD_JPY`
- `GET /analytics/win-rate?dimension=hour|weekday|pair|direction|regime|score_bucket`

### System
- `GET /system/status` (under `/api/v1`, bearer-token protected) — broker
  connectivity, market-data/trading provider split warning, kill switch state,
  current mode, API process uptime, most recent error.
- `GET /settings/risk` / `PUT /settings/risk`
- `GET /notifications`, `POST /notifications/{id}/read`

### Health / readiness / metrics (top-level, NOT under `/api/v1`, unauthenticated —
these are meant to be hit by an uptime monitor/load balancer/orchestrator, not a
logged-in operator; see docs/15_PRODUCTION_READINESS_REVIEW.md "Observability")
- `GET /health` — process liveness only, no dependency checks. Always 200 if the
  process is up at all.
- `GET /ready` — checks DB (`SELECT 1`) and Redis (`PING`); 200 if both are up, 503
  otherwise, with a per-dependency breakdown in the body either way. A market-data
  broker outage is reported but does **not** flip this to 503 — broker issues are
  common/transient and the app's non-trading features stay usable through them.
- `GET /metrics` — plain JSON (not Prometheus exposition format): uptime,
  broker-connected flag, and per-watchlist-instrument last-tick timestamp/price.

Every response (all routers, not just these three) carries an `X-Request-ID`
header — echoes an inbound one if present, mints a UUID otherwise — and that same
ID is attached to every structured log line emitted while handling the request
(`app/core/request_context.py`), so "why did this order fail" is one grep away.

### AI explanations (docs/08_SIGNAL_ENGINE.md "AI's role" — explanation only, never
decides direction; templated fallback when `AI_API_KEY` is unset)
- `GET /ai/explain/signal/{symbol}?granularity=M15` — natural-language explanation of
  the current signal.
- `GET /ai/explain/trade/{trade_id}` — why a specific journaled trade likely won/lost.
- `GET /ai/daily-summary` — today's trading in a few sentences.
- `GET /ai/explain/backtest/{backtest_id}` — plain-language backtest readout,
  flagging IS/OOS gaps as a possible overfitting signal.

## WebSocket

- `WS /ws/prices?instruments=USD_JPY,EUR_JPY` — server pushes
  `{type: "tick", instrument, bid, ask, mid, ts}` and
  `{type: "candle_close", instrument, granularity, candle}` frames. Client sends only
  `{type: "subscribe"/"unsubscribe", instruments: [...]}` control frames.
- `WS /ws/system` — pushes `system_events`/`notifications` as they occur.

Frontend never polls REST for live price ticks — only WebSocket. REST is used for
initial load and historical candle backfill.

## Error shape

```json
{ "error": { "code": "RISK_LIMIT_EXCEEDED", "message": "...", "details": {} } }
```

Machine-checkable `code` values are documented per-endpoint in the OpenAPI schema
(FastAPI auto-generates `/docs` and `/openapi.json`).
