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
  `system_events` row, marks the instrument `stale` in Redis (`price:{instrument}:stale=1`)
  and retries with exponential backoff (2s → 60s cap). `GET /system/status` and the
  System page surface this immediately.
- Frontend: WebSocket client auto-reconnects with backoff and marks affected tiles
  "stale" (dimmed, "reconnecting…" badge) rather than freezing on last-known values
  silently.

## Polling fallback

`MockAdapter` and (initially) `GmoCoinAdapter`/REST-only sources implement
`stream_prices()` as an async generator wrapping a polling loop
(`GET current price every POLL_INTERVAL_MS`) with per-instrument jitter, so from the
worker's perspective every adapter looks like a stream regardless of transport.
