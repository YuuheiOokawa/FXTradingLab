# 04. Database Design (PostgreSQL)

Full column-level definitions live in the SQLAlchemy models under
`backend/app/db/models/`; this document covers the schema's shape and rationale.
See `backend/alembic/versions/` for the migration history (initial schema is
`3974ddc6a822_initial_schema.py` — alembic generates hash-based revision IDs,
not sequential numbers; this doc previously referenced a nonexistent
`0001_initial.py`, corrected during the production-readiness re-review).

## Entity groups

### Identity / accounts
- **users** — single-operator today; kept normalized for future multi-user.
- **broker_accounts** — one row per configured broker connection (`provider`,
  `environment` = practice/live, masked account id — never the secret token, which
  lives only in env vars).

### Reference data
- **instruments** — tradable pairs (`USD_JPY`, …), pip size, margin rate, display
  precision, `is_watched` flag for the user's dashboard watchlist.

### Market data
- **candles** — OHLCV, PK `(instrument_id, granularity, open_time)`. Populated for
  both live monitoring and backtests (historical bulk load).
- **market_ticks** — raw bid/ask ticks, retained short-term only (see Retention below).

### Strategy / signals
- **strategies** — code name + description of a rule-based strategy implementation.
- **strategy_configs** — per-strategy tunable parameters (JSONB) so the same strategy
  class can run multiple parameter sets (e.g. different EMA periods) without new code.
- **signals** — a computed signal snapshot: instrument, timeframe, strategy_config,
  direction, score (0-100), regime, JSONB `reasons` (the ✓/△/✗ breakdown), timestamp.
  Also carries outcome-tracking columns (`entry_price`, `outcome_computed_at`,
  `max_favorable_pips`, `max_adverse_pips`, `price_after_horizon_pips`,
  `tp_reached`, `sl_reached`) populated by `app/worker/jobs/signal_capture.py` /
  `signal_outcome.py` — see `docs/08_SIGNAL_ENGINE.md` "Signal outcome history".
  A unique constraint on `(instrument_id, granularity, ts)` is the dedup key for
  repeated capture-job runs against the same still-current candle.

### Backtesting
- **backtests** — one row per backtest run: config (JSONB) + summary stats.
- **backtest_trades** — individual simulated trades belonging to a backtest, with
  entry/exit reason text and the signal snapshot that triggered them.

### Paper trading
- **paper_accounts** — virtual balance, starts at ¥1,000,000, one per user (v1).
- **paper_positions**, **paper_orders** — mirror the shape of `live_*` tables so the
  Order Orchestrator and journal code can treat paper/live symmetrically.

### Live trading
- **live_orders**, **live_positions** — real broker-side state mirrored locally,
  keyed by broker order/trade id, with an `idempotency_key` unique constraint.

### Journal & risk
- **trade_journals** — the unified, denormalized record of every closed trade
  (backtest/paper/demo/live) used by the analytics queries — see below.
- **risk_settings** — singleton-per-user row: max per-trade risk %, daily loss limit,
  max drawdown %, max concurrent positions, max consecutive losses, kill switch state.

### Operational
- **system_events** — structured log of connect/disconnect/error/kill-switch events,
  surfaced on the System page.
- **notifications** — in-app notification feed; `channel` column (`in_app`, `discord`,
  `line`, `email`) is future-ready even though only `in_app` is implemented in v1.

## Why `trade_journals` is denormalized instead of a view over 4 trade tables

Analytics (win rate by hour/weekday/pair/direction/regime/score-bucket) needs to query
across backtest, paper, demo, and (eventually) live trades uniformly and cheaply. A
`UNION ALL` view across four structurally-different tables works but is harder to index
and slower for repeated ad-hoc aggregation. Instead, every trade-closing code path
writes one row into `trade_journals` (source enum: `backtest`/`paper`/`demo`/`live`)
in addition to its source-specific table. `backtest_trades` etc. remain the source of
truth for their own domain (e.g. re-running analysis on a specific backtest);
`trade_journals` is the analytics-optimized read model.

## Tick retention & aggregation

Raw ticks are high-volume and only needed briefly (candle formation, spread
monitoring). Policy, enforced by a worker job (`app/worker/jobs/retention.py`):

1. Every incoming tick updates the in-progress in-memory candle for every timeframe
   (no DB write required for this).
2. Ticks are persisted to `market_ticks` at a down-sampled rate (default: 1 row per
   instrument per 5 seconds) — enough for spread-anomaly detection and audit, not
   full tick-by-tick history.
3. A nightly job deletes `market_ticks` rows older than `TICK_RETENTION_DAYS`
   (default 7).
4. Only `M1` candles are ever bulk-deleted, once older than
   `CANDLE_1M_RETENTION_DAYS` (default 90) — a straight age-based delete
   (`app/worker/jobs/retention.py`), not cross-checked against whether 5m/15m
   candles exist for the same period first. This doc previously claimed an
   "aggregated confirmation check" step that doesn't exist in the code;
   corrected during the production-readiness re-review rather than built,
   since M1 data is the least valuable for backtesting (higher timeframes are
   what strategies actually run against) and a confirmation check would add
   real complexity for low practical benefit at this app's scale — if this
   matters to you, treat it as a documented extension point, not a promise.
   Higher timeframes (5m+) are kept indefinitely (low volume, high value for
   backtesting).

## Indexing notes

- `candles (instrument_id, granularity, open_time DESC)` — the hot path for chart
  loads and backtests.
- `market_ticks (instrument_id, ts DESC)` partial-purged by retention job instead of
  partitioned in v1 (partitioning is a documented upgrade path once tick volume
  justifies it).
- `trade_journals (source, closed_at)`, `(pair, direction)`, `(signal_score)` —
  supports the analytics breakdowns directly.
