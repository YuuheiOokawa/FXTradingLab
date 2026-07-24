"""Verify a real OANDA connection end-to-end, before trusting it with anything.

Checks, in order, the things that actually break when swapping the built-in
simulator for a live feed:

1. credentials work at all (account summary),
2. live prices arrive with a sane spread,
3. DAILY candles come back with enough history for the playbook (EMA200 needs
   ~260 bars), and the still-forming bar is correctly flagged `complete: false`
   — the playbook's look-ahead guard depends on that flag,
4. the playbook actually evaluates on that real data.

Read-only: it never places an order. Run it with OANDA credentials in the
environment (or backend/.env):

    OANDA_API_TOKEN=... OANDA_ACCOUNT_ID=... BROKER_PROVIDER=oanda \
        python -m scripts.check_oanda
"""
from __future__ import annotations

import asyncio
import sys

from app.brokers.factory import get_market_data_provider
from app.brokers.schemas import Granularity
from app.core.config import get_settings
from app.services import playbook
from app.services.auto_trader import _drop_forming_candle, candles_to_df

OK, BAD, WARN = "  OK  ", " FAIL ", " WARN "


def line(status: str, msg: str) -> None:
    print(f"[{status}] {msg}")


async def main() -> int:
    settings = get_settings()
    print(f"broker_provider = {settings.broker_provider}")
    print(f"environment     = {settings.oanda_environment}")
    print(f"watchlist       = {settings.watchlist}\n")

    if settings.broker_provider != "oanda":
        line(WARN, "BROKER_PROVIDER is not 'oanda' — this will exercise the built-in simulator, not a real feed.")

    broker = get_market_data_provider()
    failures = 0

    # 1. credentials
    try:
        account = await broker.get_account()
        line(OK, f"account {account.account_id}: balance {account.balance:,.0f} {account.currency}")
    except Exception as exc:
        line(BAD, f"account lookup failed: {type(exc).__name__}: {exc}")
        return 1  # nothing else can work without this

    for symbol in settings.watchlist:
        print(f"\n--- {symbol} ---")

        # 2. live price
        try:
            q = await broker.get_current_price(symbol)
            spread = q.ask - q.bid
            line(OK, f"price bid={q.bid} ask={q.ask} spread={spread:.5f}")
            if spread <= 0:
                line(BAD, "non-positive spread — the feed is wrong")
                failures += 1
        except Exception as exc:
            line(BAD, f"price failed: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        # 3. daily history depth + forming-bar flag
        try:
            candles = await broker.get_candles(symbol, Granularity.D, 400)
            closed = _drop_forming_candle(candles)
            dropped = len(candles) - len(closed)
            line(OK, f"daily candles: {len(candles)} returned, {dropped} still forming, {len(closed)} closed")
            if len(closed) < playbook.MIN_BARS:
                line(BAD, f"only {len(closed)} closed bars; the playbook needs {playbook.MIN_BARS} (EMA200)")
                failures += 1
            if dropped == 0:
                line(
                    WARN,
                    "no candle was flagged as still forming. Real OANDA marks today's bar "
                    "complete=false; if this persists during market hours the look-ahead "
                    "guard is not protecting anything.",
                )
        except Exception as exc:
            line(BAD, f"candles failed: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        # 4. does the playbook run on this data?
        cfg = playbook.config_for(symbol)
        if cfg is None:
            line(WARN, "no playbook entry for this instrument — the auto-trader will skip it")
            continue
        if not cfg.enabled:
            line(WARN, f"playbook style '{cfg.style}' is disabled for this pair — auto-trader will skip it")
            continue
        try:
            sig = playbook.evaluate(symbol, candles_to_df(closed))
            if sig is None:
                line(OK, f"playbook '{cfg.style}' evaluated cleanly (no entry today)")
            else:
                line(OK, f"playbook '{cfg.style}' -> {sig.direction} @ {sig.price} | {sig.reason}")
        except Exception as exc:
            line(BAD, f"playbook evaluation failed: {type(exc).__name__}: {exc}")
            failures += 1

    print()
    if failures:
        line(BAD, f"{failures} check(s) failed — do not run the auto-trader against this configuration yet.")
        return 1
    line(OK, "all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
