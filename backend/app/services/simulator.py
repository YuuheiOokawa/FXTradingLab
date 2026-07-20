"""What-if trade simulator (docs/01_REQUIREMENTS.md FR-8): "if I had bought here,
what would have happened". State is kept in an in-process dict — this is
intentionally ephemeral practice/exploration data, not a durable trading record
(unlike paper/live orders, which always go through OrderOrchestrator + DB), so a v1
single-process in-memory store is an acceptable simplification (documented in
docs/14_IMPLEMENTATION_PLAN.md).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Direction = Literal["BUY", "SELL"]


@dataclass
class SimulationState:
    id: str
    instrument: str
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float
    created_at: datetime
    status: Literal["open", "closed_tp", "closed_sl", "closed_manual"] = "open"
    max_favorable: float = 0.0
    max_adverse: float = 0.0
    current_price: float = 0.0
    current_pnl: float = 0.0
    closed_price: float | None = None
    closed_at: datetime | None = None

    @property
    def risk_reward_ratio(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return round(reward / risk, 3) if risk > 0 else 0.0


_STORE: dict[str, SimulationState] = {}


def create_simulation(
    instrument: str, direction: Direction, entry_price: float, stop_loss: float, take_profit: float, size: float
) -> SimulationState:
    sim_id = str(uuid.uuid4())
    sim = SimulationState(
        id=sim_id,
        instrument=instrument,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        size=size,
        created_at=datetime.now(UTC),
        current_price=entry_price,
    )
    _STORE[sim_id] = sim
    return sim


def get_simulation(sim_id: str) -> SimulationState | None:
    return _STORE.get(sim_id)


def update_with_price(sim: SimulationState, bid: float, ask: float) -> SimulationState:
    if sim.status != "open":
        return sim
    price = bid if sim.direction == "BUY" else ask  # exit-side price
    diff = (price - sim.entry_price) if sim.direction == "BUY" else (sim.entry_price - price)
    pnl = diff * sim.size

    sim.current_price = price
    sim.current_pnl = pnl
    sim.max_favorable = max(sim.max_favorable, pnl)
    sim.max_adverse = min(sim.max_adverse, pnl)

    hit_tp = (price >= sim.take_profit) if sim.direction == "BUY" else (price <= sim.take_profit)
    hit_sl = (price <= sim.stop_loss) if sim.direction == "BUY" else (price >= sim.stop_loss)
    if hit_sl:
        sim.status, sim.closed_price, sim.closed_at = "closed_sl", sim.stop_loss, datetime.now(UTC)
    elif hit_tp:
        sim.status, sim.closed_price, sim.closed_at = "closed_tp", sim.take_profit, datetime.now(UTC)
    return sim


def close_simulation(sim: SimulationState) -> SimulationState:
    if sim.status == "open":
        sim.status = "closed_manual"
        sim.closed_price = sim.current_price
        sim.closed_at = datetime.now(UTC)
    return sim
