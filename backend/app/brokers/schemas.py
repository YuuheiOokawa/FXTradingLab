from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, computed_field


class Granularity(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D = "D"


GRANULARITY_SECONDS: dict[Granularity, int] = {
    Granularity.M1: 60,
    Granularity.M5: 300,
    Granularity.M15: 900,
    Granularity.H1: 3600,
    Granularity.H4: 14400,
    Granularity.D: 86400,
}

Direction = Literal["BUY", "SELL"]


class PriceQuote(BaseModel):
    instrument: str
    bid: float
    ask: float
    ts: datetime

    @computed_field
    @property
    def mid(self) -> float:
        return round((self.bid + self.ask) / 2, 6)

    @computed_field
    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 6)


class Candle(BaseModel):
    instrument: str
    granularity: Granularity
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    is_final: bool = True


class AccountSummary(BaseModel):
    account_id: str
    balance: float
    equity: float
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    currency: str = "JPY"


class BrokerPosition(BaseModel):
    instrument: str
    direction: Direction
    size: float
    entry_price: float
    unrealized_pnl: float
    stop_loss: float | None = None
    take_profit: float | None = None
    trade_id: str


class OrderRequest(BaseModel):
    instrument: str
    direction: Direction
    size: float
    order_type: Literal["market"] = "market"
    stop_loss: float | None = None
    take_profit: float | None = None
    idempotency_key: str


class OrderResult(BaseModel):
    success: bool
    broker_order_id: str | None = None
    trade_id: str | None = None
    filled_price: float | None = None
    status: Literal["filled", "rejected", "pending"]
    reject_reason: str | None = None
