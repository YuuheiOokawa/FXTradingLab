# 01. Requirements

## Functional requirements

### Market monitoring
- FR-1: Continuously monitor Bid/Ask/Mid/Spread for a user-configurable watchlist,
  defaulting to USD/JPY, EUR/JPY, GBP/JPY, EUR/USD.
- FR-2: Maintain OHLC candles at 1m/5m/15m/1h/4h/1D, built from streamed/polled ticks.
- FR-3: Push price/candle updates to the browser without full-page reload (WebSocket).

### Analysis
- FR-4: Compute EMA(20/50/200), SMA, Bollinger Bands, RSI(14), MACD(12/26/9), ATR(14),
  ADX(14) per instrument/timeframe.
- FR-5: Classify market regime: UPTREND, DOWNTREND, RANGE, HIGH_VOLATILITY,
  LOW_VOLATILITY, UNKNOWN.
- FR-6: Multi-timeframe confirmation (4H → 1H → entry timeframe) that penalizes
  signals that disagree with the higher-timeframe trend.
- FR-7: Produce a 0-100 BUY/SELL score per instrument with itemized reason list
  (✓ met / △ partial / ✗ failed), and a 5-level label (強い買い/買い/様子見/売り/強い売り).

### Simulation & training
- FR-8: Manual "what-if" trade simulator: user defines entry/SL/TP/size, app replays
  subsequent price action against it and reports live P/L, MFE/MAE, RR.
- FR-9: Replay mode: step through historical candles one at a time (or 1x/5x/10x/50x
  autoplay), user commits to BUY/SELL/skip, outcome + rule-based explanation recorded.
  TRAINING ON/OFF toggle controls whether the rule breakdown is shown before the
  decision.

### Backtesting
- FR-10: Configurable backtest (pair, period, timeframe, capital, size, risk%, spread,
  slippage, commission, strategy, SL/TP/trailing) over stored historical candles.
- FR-11: Report total P/L, return %, trade count, win rate, avg win/loss, profit
  factor, Sharpe ratio, max drawdown, max consecutive wins/losses.
- FR-12: Equity curve chart + entry/exit markers on price chart; click a trade to see
  entry/exit rationale.
- FR-13: In-sample / out-of-sample split is mandatory in the backtest form.

### Trading modes
- FR-14: BACKTEST, PAPER_LIVE, DEMO, LIVE modes, switchable, with LIVE disabled unless
  three independent conditions are all true (env var, admin setting, explicit
  confirmation dialog).
- FR-15: MANUAL / SEMI_AUTO / FULL_AUTO execution modes. FULL_AUTO always pipes through
  Risk Engine → Signal Engine → Order Validator → Broker API in that order.

### Risk & safety
- FR-16: Risk Engine rejects orders that violate: per-trade max risk, daily max loss,
  max drawdown, max concurrent positions, duplicate-symbol exposure, consecutive-loss
  stop, abnormal spread, stale/absent price feed, broker disconnect.
- FR-17: Kill Switch: one action blocks new orders + auto-trading immediately, with an
  option to flatten existing positions. Evaluated before any other order logic.
- FR-18: Idempotency keys on all order submissions to prevent duplicate execution on
  retry.

### Journal & analytics
- FR-19: Every simulated/paper/live trade is persisted with full context (entry/exit,
  size, SL/TP, P/L, rationale, signal score, strategy, market regime).
- FR-20: Win-rate breakdowns by hour, weekday, pair, direction, market regime, and
  signal-score bucket.

### Notifications
- FR-21: In-app notification center for strong signals, SL/TP hits, daily loss limit,
  API disconnects, abnormal spread. Pluggable channel interface for Discord/LINE/email.

## Non-functional requirements

- NFR-1: No broker API secret ever reaches the browser; all broker calls happen
  server-side only.
- NFR-2: Secrets only via environment variables, never committed.
- NFR-3: `LIVE_TRADING_ENABLED=false` by default in every environment, including
  `production`. Environment name must never implicitly select a live broker account.
- NFR-4: Tick storage must not grow unbounded — retention + aggregation + deletion
  policy (see `04_DATABASE_DESIGN.md`).
- NFR-5: Broker outages/reconnects must not crash the app or corrupt open-position
  state; must be observable in the System page.
- NFR-6: The app must remain usable (backtest, paper trading, replay, journal,
  analytics) with zero broker credentials configured, using the Mock adapter.
- NFR-7: Automated test coverage for Signal Engine, Risk Engine, Backtest engine, and
  Broker adapter contract.

## Out of scope (v1)

- Multi-broker simultaneous execution, portfolio margining across brokers, tax
  reporting/export, mobile native apps, options/futures instruments.
