# 07. Real-time Data Design

## Pipeline

`BrokerAdapter.stream_prices()` (worker process) → in-memory candle builder → Redis
pub/sub (`ticks:{instrument}`, `candles:{instrument}:{granularity}`) → FastAPI
WebSocket endpoint (API process) → browser.

## Candle building

For each instrument, an in-memory `CandleBuilder` per granularity holds the
currently-forming candle (open/high/low/close/volume, open_time). On each tick:

1. Determine the bucket `open_time = floor(tick.ts, granularity)`.
2. If bucket unchanged: update H/L/C of the in-progress candle in place, publish a
   `candle_update` (same open_time, non-final) event so the chart's last bar updates
   live.
3. If bucket changed: finalize the previous candle (persist to `candles`, publish
   `candle_close`), start a new candle from the tick.

This means the frontend chart never re-fetches history on every tick — it only ever
receives either a same-bar update (mutate last candle) or a new-bar close (append).

## Frontend consumption

`useLiveCandles(symbol, granularity)` hook:
- Initial REST fetch of the last N candles.
- Opens (or reuses, via a shared WebSocket provider) the `/ws/prices` connection.
- On `candle_update` / `candle_close` for a matching symbol/granularity, calls
  `series.update(candle)` (lightweight-charts' incremental API) — O(1), no
  re-render of the whole chart, no re-fetch.

Dashboard tiles (bid/ask/spread/day range) subscribe to the raw `tick` events and use
`useSyncExternalStore` to update just the affected tile's DOM, not the page.

## Backpressure / reconnect

- Backend: if `stream_prices()` raises `BrokerConnectionError`, the worker logs a
  `system_events` row, sets `system:broker_connected=0` in Redis, and retries with
  exponential backoff (2s → 60s cap). `GET /system/status` and the System page
  surface this immediately.
- Frontend (`src/lib/priceSocket.ts`): a single shared WebSocket connection
  auto-reconnects with backoff (1s → 30s cap) when dropped. **Real bug found and
  fixed during the production-readiness review**: instruments subscribed while the
  socket was still mid-handshake (`readyState === CONNECTING`) had their
  `{type:"subscribe"}` message silently dropped — the old code only sent it if the
  socket was already `OPEN` at that exact synchronous moment, with nothing to catch
  the race. Since React mounts multiple watchlist rows in the same tick, only the
  very first instrument (baked into the initial `?instruments=` query param) ever
  actually streamed; every other row silently never subscribed. Fixed by flushing
  the full subscribed-instrument set on every `ws.onopen`, verified by taking a
  before/after screenshot of the Markets page (before: only the first row showed
  LIVE; after: all rows do).
- `src/hooks/useLivePriceStatus.ts` derives a `live` / `stale` / `disconnected` /
  `connecting` status per instrument from (a) whether the shared socket is actually
  `OPEN` and (b) how long ago the last tick for that instrument arrived
  (`STALE_AFTER_MS`, matching the backend's `PRICE_STALE_SECONDS`). Surfaced via
  `<PriceStatusBadge>` on the Markets table and Dashboard watchlist — **a stale
  price is never allowed to keep displaying as if it were live**.

## Price data quality (`app/services/price_quality.py`)

Every tick is validated by `validate_tick()` before it's published to Redis,
persisted, or fed into a candle builder — a bad tick must never reach the signal
engine or an order fill price. Rejected ticks are dropped (not "corrected") and
logged as a `system_events` row (`category="price_quality"`) rather than silently
swallowed. Checks:

- Non-positive bid/ask.
- `bid >= ask` (crossed or zero-width quote).
- Spread wider than `MAX_SPREAD_FRACTION` (2%) of mid — real FX spreads are a small
  fraction of a percent even during volatility; this catches feed glitches, not
  real market stress.
- Timestamp not strictly after the previous accepted tick for that instrument
  (catches both exact duplicates and out-of-order delivery).
- Single-tick price jump larger than `MAX_JUMP_FRACTION` (3%) of the previous mid.

`MarketDataService` tracks the last *accepted* tick per instrument (not the last
*received* one) as the comparison baseline, so a burst of bad ticks can't shift the
baseline and mask a real anomaly.

## Polling fallback

`MockAdapter` and (initially) `GmoCoinAdapter`/REST-only sources implement
`stream_prices()` as an async generator wrapping a polling loop
(`GET current price every POLL_INTERVAL_MS`) with per-instrument jitter, so from the
worker's perspective every adapter looks like a stream regardless of transport.
