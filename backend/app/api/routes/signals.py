from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends

from app.api.deps import get_broker
from app.brokers.base import BrokerAdapter
from app.brokers.schemas import Granularity
from app.services.signal_engine import evaluate

router = APIRouter(prefix="/signals", tags=["signals"])

HIGHER_TIMEFRAMES: dict[Granularity, dict[str, Granularity]] = {
    Granularity.M15: {"H1": Granularity.H1, "H4": Granularity.H4},
    Granularity.H1: {"H4": Granularity.H4, "D": Granularity.D},
    Granularity.M5: {"M15": Granularity.M15, "H1": Granularity.H1},
    Granularity.M1: {"M15": Granularity.M15, "H1": Granularity.H1},
}


def _to_df(candles) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": [c.open_time for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )


@router.get("/{symbol}")
async def get_signal(
    symbol: str,
    granularity: Granularity = Granularity.M15,
    broker: BrokerAdapter = Depends(get_broker),
) -> dict:
    entry_candles = await broker.get_candles(symbol, granularity, 300)
    higher_tf = {}
    for label, gran in HIGHER_TIMEFRAMES.get(granularity, {}).items():
        candles = await broker.get_candles(symbol, gran, 300)
        higher_tf[label] = _to_df(candles)

    signal = evaluate(_to_df(entry_candles), higher_tf)
    return {
        "instrument": symbol,
        "granularity": granularity.value,
        "direction": signal.direction,
        "score": signal.score,
        "buy_score": signal.buy_score,
        "sell_score": signal.sell_score,
        "label": signal.label,
        "regime": {
            "trend": signal.regime.trend,
            "volatility": signal.regime.volatility,
        },
        "reasons": [{"status": r.status, "text": r.text, "points": r.points} for r in signal.reasons],
    }
