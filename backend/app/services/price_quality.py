"""Tick quality validation (docs/15_PRODUCTION_READINESS_REVIEW.md "Price Data
Quality"). A bad tick must never reach the candle builder, the signal engine, or
an order fill price — this is the single choke point that keeps it out.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.brokers.schemas import PriceQuote

# A single-tick jump larger than this fraction of the previous mid is treated as
# a data error, not a real market move — even the most violent FX flash moves
# don't jump 3% between two consecutive ticks (which arrive every ~2s).
MAX_JUMP_FRACTION = 0.03
# A spread wider than this fraction of mid is treated as a data/feed error
# rather than real market stress — real FX spreads are a small fraction of a
# percent even during volatility; 2% would be catastrophic and almost
# certainly means the feed glitched rather than the market actually doing this.
MAX_SPREAD_FRACTION = 0.02


@dataclass
class TickValidationResult:
    valid: bool
    reason: str | None = None


def validate_tick(tick: PriceQuote, previous: PriceQuote | None) -> TickValidationResult:
    if tick.bid <= 0 or tick.ask <= 0:
        return TickValidationResult(False, f"non-positive price (bid={tick.bid}, ask={tick.ask})")
    if tick.bid >= tick.ask:
        return TickValidationResult(False, f"bid >= ask (bid={tick.bid}, ask={tick.ask})")
    if tick.spread / tick.mid > MAX_SPREAD_FRACTION:
        return TickValidationResult(False, f"spread anomaly ({tick.spread:.5f} / mid {tick.mid:.5f})")

    if previous is not None:
        if tick.ts <= previous.ts:
            return TickValidationResult(False, f"timestamp not after previous tick ({tick.ts} <= {previous.ts})")
        jump = abs(tick.mid - previous.mid) / previous.mid
        if jump > MAX_JUMP_FRACTION:
            return TickValidationResult(False, f"price jump anomaly ({jump:.2%} from {previous.mid} to {tick.mid})")

    return TickValidationResult(True)
