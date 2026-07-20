from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_broker
from app.brokers.base import BrokerAdapter
from app.services.simulator import close_simulation, create_simulation, get_simulation, update_with_price

router = APIRouter(prefix="/simulate", tags=["simulate"])


class SimulateIn(BaseModel):
    instrument: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float


def _serialize(sim) -> dict:
    return {
        "id": sim.id,
        "instrument": sim.instrument,
        "direction": sim.direction,
        "entry_price": sim.entry_price,
        "stop_loss": sim.stop_loss,
        "take_profit": sim.take_profit,
        "size": sim.size,
        "status": sim.status,
        "current_price": sim.current_price,
        "current_pnl": round(sim.current_pnl, 2),
        "max_favorable": round(sim.max_favorable, 2),
        "max_adverse": round(sim.max_adverse, 2),
        "risk_reward_ratio": sim.risk_reward_ratio,
        "closed_price": sim.closed_price,
    }


@router.post("")
async def start_simulation(body: SimulateIn) -> dict:
    sim = create_simulation(body.instrument, body.direction, body.entry_price, body.stop_loss, body.take_profit, body.size)
    return _serialize(sim)


@router.get("/{sim_id}")
async def get_simulation_state(sim_id: str, broker: BrokerAdapter = Depends(get_broker)) -> dict:
    sim = get_simulation(sim_id)
    if sim is None:
        raise HTTPException(404, "simulation not found")
    quote = await broker.get_current_price(sim.instrument)
    sim = update_with_price(sim, quote.bid, quote.ask)
    return _serialize(sim)


@router.post("/{sim_id}/close")
async def close_simulation_route(sim_id: str) -> dict:
    sim = get_simulation(sim_id)
    if sim is None:
        raise HTTPException(404, "simulation not found")
    sim = close_simulation(sim)
    return _serialize(sim)
