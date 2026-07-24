from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_db
from app.brokers.base import BrokerAdapter
from app.brokers.schemas import Granularity
from app.core.config import get_settings
from app.db.models.market import Candle as CandleModel
from app.db.models.market import Instrument
from app.services.calibration import MIN_BARS_FOR_CALIBRATION, calibrate, to_dict
from app.services.market_data import DEFAULT_INSTRUMENT_META, ensure_instruments
from app.services.playbook import config_for

router = APIRouter(prefix="/instruments", tags=["market"])


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    display_name: str
    pip_size: float
    price_precision: int
    is_watched: bool


class AddInstrumentIn(BaseModel):
    symbol: str


@router.get("", response_model=list[InstrumentOut])
async def list_instruments(session: AsyncSession = Depends(get_db)) -> list[Instrument]:
    result = await session.execute(select(Instrument).where(Instrument.is_watched == True))  # noqa: E712
    rows = list(result.scalars().all())
    if not rows:
        settings = get_settings()
        await ensure_instruments(settings.watchlist)
        result = await session.execute(select(Instrument).where(Instrument.is_watched == True))  # noqa: E712
        rows = list(result.scalars().all())
    return rows


@router.post("", response_model=InstrumentOut)
async def add_instrument(body: AddInstrumentIn, session: AsyncSession = Depends(get_db)) -> Instrument:
    result = await session.execute(select(Instrument).where(Instrument.symbol == body.symbol))
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_watched = True
        await session.commit()
        await session.refresh(existing)
        return existing
    meta = DEFAULT_INSTRUMENT_META.get(body.symbol, {"display_name": body.symbol, "pip_size": 0.01, "price_precision": 3})
    instrument = Instrument(symbol=body.symbol, is_watched=True, **meta)
    session.add(instrument)
    await session.commit()
    await session.refresh(instrument)
    return instrument


@router.delete("/{symbol}")
async def remove_instrument(symbol: str, session: AsyncSession = Depends(get_db)) -> dict:
    result = await session.execute(select(Instrument).where(Instrument.symbol == symbol))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, "instrument not found")
    instrument.is_watched = False
    await session.commit()
    return {"symbol": symbol, "is_watched": False}


@router.get("/{symbol}/price")
async def get_price(symbol: str, broker: BrokerAdapter = Depends(get_broker)) -> dict:
    quote = await broker.get_current_price(symbol)
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    day_candles = await broker.get_candles(symbol, Granularity.M15, 100)
    todays = [c for c in day_candles if c.open_time >= day_start] or day_candles[-1:]
    day_high = max(c.high for c in todays)
    day_low = min(c.low for c in todays)
    prev_close = day_candles[0].open if day_candles else quote.mid
    change = quote.mid - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    return {
        "instrument": symbol,
        "bid": quote.bid,
        "ask": quote.ask,
        "mid": quote.mid,
        "spread": quote.spread,
        "day_high": day_high,
        "day_low": day_low,
        "change": round(change, 6),
        "change_pct": round(change_pct, 4),
        "ts": quote.ts.isoformat(),
    }


@router.get("/{symbol}/candles")
async def get_candles(
    symbol: str,
    granularity: Granularity = Granularity.M15,
    count: int = 300,
    broker: BrokerAdapter = Depends(get_broker),
) -> list[dict]:
    count = max(1, min(count, 5000))
    candles = await broker.get_candles(symbol, granularity, count)
    return [c.model_dump(mode="json") for c in candles]


@router.get("/{symbol}/calibration")
async def instrument_calibration(
    symbol: str,
    bars: int = 1500,
    broker: BrokerAdapter = Depends(get_broker),
) -> dict:
    """Measure this instrument's character and recommend a playbook style.

    Reproduces the analysis behind the shipped per-pair book
    (app/services/playbook.py) so a newly added pair can be classified from its
    own history instead of inheriting whichever rule happened to be written
    first — the mistake that cost -12,926 pips over 23 years when one trend rule
    was applied to all four pairs.

    Read-only, and explicitly a hypothesis: the response carries the confidence
    level, any warnings, and the instruction to backtest before enabling.
    """
    bars = max(MIN_BARS_FOR_CALIBRATION, min(bars, 5000))
    candles = await broker.get_candles(symbol, Granularity.D, bars)
    closed = [c for c in candles if getattr(c, "is_final", True)]
    if len(closed) < MIN_BARS_FOR_CALIBRATION:
        raise HTTPException(
            status_code=422,
            detail=(
                f"only {len(closed)} closed daily bars available for {symbol}; "
                f"{MIN_BARS_FOR_CALIBRATION} are needed to measure its character"
            ),
        )

    df = pd.DataFrame(
        {
            "open": [c.open for c in closed],
            "high": [c.high for c in closed],
            "low": [c.low for c in closed],
            "close": [c.close for c in closed],
        }
    )
    result = calibrate(symbol, df)
    if result is None:
        raise HTTPException(status_code=422, detail=f"could not calibrate {symbol}")

    payload = to_dict(result)
    current = config_for(symbol)
    if current is None:
        payload["current_playbook"] = None
    else:
        matches = current.style == result.recommended_style
        payload["current_playbook"] = {
            "style": current.style,
            "enabled": current.enabled,
            "adx_min": current.adx_min,
            "adx_max": current.adx_max,
            "matches_recommendation": matches,
            # A disagreement is expected and is not a bug: the configured style
            # was chosen by backtesting every family on this pair, which beats a
            # single statistic. On USD/JPY and GBP/JPY the measured character
            # points one way and the validated result went the other.
            "note": (
                "configured style matches the measured character"
                if matches
                else (
                    "configured style differs from the statistical recommendation — the "
                    "configured one was selected by full backtest, which takes precedence"
                )
            ),
        }
    return payload
