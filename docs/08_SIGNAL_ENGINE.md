# 08. Signal Engine

## Principles

- Signals are **descriptive, not predictive**: "the configured rule-based strategy
  currently scores 82/100 for BUY," never "price will go up."
- Every signal carries an itemized reason list so a beginner can see *why*.
- No booleans — every dimension contributes points to a 0-100 score, and the score
  maps to one of five labels.

## Strategy 1 — Trend Follow (EMA stack)

Base direction filter, not a standalone trigger:
- BUY bias: `EMA20 > EMA50 > EMA200` and `price > EMA20`.
- SELL bias: `EMA20 < EMA50 < EMA200` and `price < EMA20`.
- A partial stack (e.g. `EMA20 > EMA50` but `EMA50 < EMA200`) contributes partial
  points, never a full trigger — matches the requirement "don't enter on EMA alone."

## Strategy 2 — RSI confirmation
- BUY boost: RSI(14) crossed up through 30 within the last N bars (was ≤30, now >30
  and rising).
- SELL boost: RSI(14) crossed down through 70.
- Neutral/no-signal RSI still contributes a smaller "no overheating" partial score.

## Strategy 3 — MACD confirmation
- BUY boost: MACD line crosses above signal line (golden cross) while histogram is
  rising.
- SELL boost: MACD line crosses below signal line (dead cross).

## Strategy 4 — Bollinger Bands (regime-dependent)
- In `RANGE` regime: mean-reversion use — price touching/exceeding the lower band is
  a BUY factor, upper band a SELL factor.
- In `UPTREND`/`DOWNTREND` regime: trend use — price riding the upper band (in an
  uptrend) is a *continuation* factor, not a reversal signal; band-touch logic is
  suppressed to avoid contradicting the trend strategy. This is the explicit
  regime-dependent switch requested in the spec ("don't confuse mean-reversion and
  trend use").

## Market regime classification (`app/services/regime.py`)

Inputs: ADX(14), ATR(14) (current vs its own rolling average), EMA50 vs EMA200 slope.

```
ADX >= 25 and EMA50 slope > 0        -> UPTREND
ADX >= 25 and EMA50 slope < 0        -> DOWNTREND
ADX <  20                             -> RANGE
ATR > 1.5 * ATR_avg(50)               -> HIGH_VOLATILITY   (evaluated in combination
ATR < 0.5 * ATR_avg(50)               -> LOW_VOLATILITY     with the above, see code)
else                                   -> UNKNOWN
```
Volatility state is tracked alongside trend state (a market can be `UPTREND` +
`HIGH_VOLATILITY` simultaneously) — `regime.py` returns a small struct
`{trend, volatility}` rather than a single enum, and the score-breakdown UI reads both.

## Multi-timeframe confirmation

For an entry timeframe `T` (e.g. M15), the engine also evaluates trend direction on
the two higher timeframes in the chain `H4 → H1 → T` (configurable per strategy
config). Agreement/disagreement affects the "上位足との一致" score component:

- Both higher timeframes agree with the entry-timeframe bias: full 20 points.
- One agrees, one neutral/range: partial points.
- Either higher timeframe actively disagrees (opposite trend): heavy penalty — this
  implements the spec's example ("4H down, 1H up, 15M BUY → score reduced").

## Scoring breakdown (sums to 100)

| Component | Points | Source |
|---|---|---|
| Trend direction (EMA stack strength) | 30 | Strategy 1 |
| Higher-timeframe agreement | 20 | Multi-timeframe |
| RSI | 15 | Strategy 2 |
| MACD | 15 | Strategy 3 |
| Bollinger Bands (regime-aware) | 10 | Strategy 4 |
| Volatility suitability | 10 | Regime (ATR) |

`app/services/signal_engine.py::SignalEngine.evaluate()` returns:

```python
SignalResult(
    direction: Literal["BUY", "SELL"],
    score: int,                     # 0-100
    label: Literal["強い買い","買い","様子見","売り","強い売り"],
    regime: RegimeResult,
    reasons: list[Reason],          # each: {status: "met"|"partial"|"failed", text}
)
```
Label thresholds: ≥75 強い{buy/sell}, ≥55 {buy/sell}, else 様子見 (for the weaker
side), symmetric for SELL. Score is computed independently for BUY and SELL bias;
whichever is higher (and above the 様子見 floor) is reported, otherwise 様子見.

## Signal outcome history

`GET /signals/{symbol}` and the FULL_AUTO evaluation loop
(`app/services/auto_trader.py`) both compute signals on demand — neither
persists them. Two independent worker jobs build a historical record purely
for analytics, unrelated to whether anyone actually traded a given signal:

- `app/worker/jobs/signal_capture.py` (every 5 min): evaluates the
  entry-timeframe (M15) signal for every watched instrument and persists a
  `Signal` row (`app/db/models/strategy.py`) whenever the score crosses
  `MIN_SCORE_THRESHOLD` (55, same floor `BacktestConfig` uses). Deduplicated
  by `(instrument, granularity, candle open_time)` — a real DB unique
  constraint, not just an application-level check — so repeated runs against
  the same still-current candle are a no-op.
- `app/worker/jobs/signal_outcome.py` (every 20 min): for each captured
  signal whose `OUTCOME_HORIZON_MINUTES` (4h) has actually elapsed *and*
  enough subsequent candle history exists in the DB to cover the full
  window, computes from the DB's own candle history (never re-fetched from
  the broker — purely retrospective): `max_favorable_pips` /
  `max_adverse_pips` (the best and worst the price moved in the horizon,
  relative to the signal's direction), `price_after_horizon_pips` (net move
  in the signal's favor by the end of the window), and `tp_reached` /
  `sl_reached` against an assumed 30/60-pip SL/TP distance (same defaults
  `BacktestConfig` uses) — **deliberately not a trade simulation**: unlike
  Backtest/Paper Trading, `tp_reached` and `sl_reached` are each independently
  "did price touch this level at any point in the window", with no
  same-bar-conflict ordering applied, so both can be `true` for the same
  signal. This is intentionally a looser statistic — "does a high-score
  signal usually move favorably afterward" — not a claim about what a real
  trade following that signal would have made.

`GET /analytics/signal-outcomes?pair=USD_JPY` (docs/05_API_DESIGN.md)
aggregates completed outcomes into the score bands 80+/70-79/60-69/<60,
reporting each bucket's outcome count, a "favorable move win rate" (the
share of signals where `max_favorable_pips > max_adverse_pips`), average
favorable/adverse excursion, average price-after-horizon move, and TP/SL
touch rates — plus a separate `pending_outcome_count` per bucket, since a
freshly-deployed instance won't have any completed outcomes for the first
few hours (the horizon has to actually elapse first). Surfaced on the
Analytics page as a score-bucket breakdown table.

## AI's role here

The AI layer (`app/services/ai_explain.py`) never computes the score or direction —
it only takes the already-computed `SignalResult` / `BacktestResult` / trade-journal
data and produces natural-language summaries ("today's trading in one paragraph",
"why did this trade lose"). If no AI API key is configured, these endpoints return the
structured data with a templated (non-LLM) text summary instead of failing — see
`01_REQUIREMENTS.md` NFR-6.
