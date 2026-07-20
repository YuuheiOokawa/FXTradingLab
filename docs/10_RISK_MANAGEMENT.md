# 10. Risk Management

## The rule

**No order reaches `BrokerAdapter.create_order()` without first passing
`RiskEngine.validate()`.** This is enforced structurally: `OrderOrchestrator` is the
only caller of any adapter's `create_order`, and it calls `RiskEngine.validate()`
unconditionally as its first step, raising `RiskRejected` (never silently downgrading
the order) on any failed check. This invariant is covered by
`backend/tests/test_risk_engine.py` and `backend/tests/test_order_orchestrator.py`
(the latter asserts the mock broker's `create_order` was never called for a rejected
order).

## Checks (in order, first failure wins)

1. **Kill switch active** — reject everything immediately, before any other check.
2. **Broker connectivity** — reject if `system:broker_connected` is false or the price
   feed for the instrument is stale (no tick within `PRICE_STALE_SECONDS`, default 10s).
3. **Spread anomaly** — reject if current spread > `max_spread_pips` for the instrument
   (configurable per instrument; default scales with typical spread).
4. **Per-trade risk** — reject if `(entry - stop_loss) * size` implies risking more
   than `risk_settings.max_risk_per_trade_pct` of current equity.
5. **Daily loss limit** — reject new risk-increasing orders if today's realized +
   open unrealized loss already exceeds `max_daily_loss_pct`.
6. **Max drawdown** — reject if current drawdown from equity high-water-mark exceeds
   `max_drawdown_pct`.
7. **Max concurrent positions** — reject if open position count ≥
   `max_concurrent_positions`.
8. **Duplicate-symbol exposure** — reject a same-direction add to an already-open
   position on the same instrument beyond `max_same_symbol_positions` (default 1).
9. **Consecutive-loss stop** — reject new entries after
   `consecutive_loss_stop_count` losing trades in a row, until manually reset.
10. **Idempotency** — reject (dedupe, return the original result) if the same
    `idempotency_key` was already submitted successfully.

Every rejection writes a `system_events` row and, for SEMI_AUTO/FULL_AUTO, a
notification, so the user always knows *why* an order didn't go through.

## Kill Switch

`POST /live/kill-switch {activate: bool, flatten_positions: bool}`

- Sets `risk_settings.kill_switch_active` (checked as step 1 above, so it takes
  priority over every other in-flight request path — including FULL_AUTO's automatic
  loop, which polls this flag before every evaluation cycle).
- If `flatten_positions` is true, immediately calls `close_position()` for every open
  paper/live position via the Order Orchestrator's close path (close orders are
  exempt from the *entry* risk checks above, but still go through broker-connectivity
  and idempotency checks).
- Deactivating the kill switch requires an explicit second call — it never
  auto-clears.

## LIVE mode gating (three independent conditions, all required)

1. **Environment variable**: `LIVE_TRADING_ENABLED=true` (default `false` in every
   environment, including `production` — set explicitly, never inferred from
   `APP_ENV`).
2. **Admin setting**: `risk_settings.live_trading_admin_enabled=true`, toggled from
   the Settings page (`components/settings/live-trading-gates.tsx`) — enabling (not
   disabling) requires typing an exact confirmation phrase into a text field before
   the button becomes clickable, a deliberate speed bump against a misclick.
3. **Per-session final confirmation**: each individual LIVE order additionally
   requires `confirm_live: true` in the request body — enforced by
   `OrderOrchestrator.submit_live_order()`/`check_live_gates()` and tested. **No
   frontend page sends this yet** — `POST /live/orders` and the gate-status
   endpoints exist and are correct, but there's no order-submission UI (with the
   "show size/entry/SL/TP/estimated max loss before confirming" modal this
   paragraph used to claim existed) to actually call it from a browser. This is a
   deliberate gap, not an oversight: it's the highest-stakes surface in the app,
   `GmoCoinAdapter` is still a stub, and shipping order-submission UI with no
   funded account to test it against would be a bigger risk than the missing
   feature. See `docs/14_IMPLEMENTATION_PLAN.md`.

`POST /live/orders` checks all three and returns `403 LIVE_TRADING_DISABLED` with
which condition(s) failed if any is missing. This mirrors the requirement that
`production` deployment must never itself imply a live account.

## FULL_AUTO pipeline order (fixed, not configurable)

```
RiskEngine.validate() -> SignalEngine.evaluate() -> OrderValidator (shape/limits) -> BrokerAdapter.create_order()
```
Note: Risk Engine gating happens even before the signal is (re-)evaluated for
freshness, so a stale or invalid system state can never reach signal evaluation with
stale data and produce an order — see `app/services/order_orchestrator.py`.
