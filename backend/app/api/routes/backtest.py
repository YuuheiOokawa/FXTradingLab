from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_db
from app.brokers.base import BrokerAdapter
from app.brokers.schemas import Granularity
from app.db.models.trading import Backtest, BacktestTrade
from app.services.backtest.engine import BacktestConfig, BacktestEngine
from app.services.backtest.walk_forward import ParamGrid, WalkForwardConfig, run_walk_forward

router = APIRouter(prefix="/backtests", tags=["backtest"])


class BacktestRequestIn(BaseModel):
    pair: str
    timeframe: Granularity = Granularity.M15
    candle_count: int = Field(default=1500, ge=300, le=5000)
    initial_capital: float = 1_000_000.0
    risk_pct: float = 1.0
    spread_pips: float = 1.5
    slippage_pips: float = 0.3
    commission_per_lot: float = 0.0
    stop_loss_pips: float = 30.0
    take_profit_pips: float = 60.0
    trailing_stop_pips: float | None = None
    in_sample_ratio: float = Field(default=0.7, ge=0.3, le=0.9)


HIGHER_TF: dict[Granularity, dict[str, Granularity]] = {
    Granularity.M15: {"H1": Granularity.H1, "H4": Granularity.H4},
    Granularity.H1: {"H4": Granularity.H4},
}


@router.post("")
async def run_backtest(
    body: BacktestRequestIn,
    broker: BrokerAdapter = Depends(get_broker),
    session: AsyncSession = Depends(get_db),
) -> dict:
    candles = await broker.get_candles(body.pair, body.timeframe, body.candle_count)
    higher_tf_candles = {}
    for label, gran in HIGHER_TF.get(body.timeframe, {}).items():
        higher_tf_candles[label] = await broker.get_candles(body.pair, gran, body.candle_count)

    config = BacktestConfig(
        pair=body.pair,
        timeframe=body.timeframe,
        initial_capital=body.initial_capital,
        risk_pct=body.risk_pct,
        spread_pips=body.spread_pips,
        slippage_pips=body.slippage_pips,
        commission_per_lot=body.commission_per_lot,
        stop_loss_pips=body.stop_loss_pips,
        take_profit_pips=body.take_profit_pips,
        trailing_stop_pips=body.trailing_stop_pips,
        in_sample_ratio=body.in_sample_ratio,
    )
    result = BacktestEngine(config).run(candles, higher_tf_candles)

    from app.services.market_data import ensure_instruments
    from app.services.repo import get_instrument_by_symbol

    await ensure_instruments([body.pair])
    instrument = await get_instrument_by_symbol(session, body.pair)

    from app.db.models.strategy import Strategy, StrategyConfig

    strategy_result = await session.execute(select(Strategy).where(Strategy.code == "trend_follow_v1"))
    strategy = strategy_result.scalar_one_or_none()
    if strategy is None:
        strategy = Strategy(code="trend_follow_v1", name="EMA/RSI/MACD/BB scored strategy")
        session.add(strategy)
        await session.flush()
    config_result = await session.execute(
        select(StrategyConfig).where(StrategyConfig.strategy_id == strategy.id)
    )
    strategy_config = config_result.scalars().first()
    if strategy_config is None:
        strategy_config = StrategyConfig(strategy_id=strategy.id, name="default", params=body.model_dump(mode="json"))
        session.add(strategy_config)
        await session.flush()

    backtest_row = Backtest(
        instrument_id=instrument.id,
        strategy_config_id=strategy_config.id,
        config=body.model_dump(mode="json"),
        status="completed",
        summary=result.summary,
        equity_curve=result.equity_curve,
    )
    session.add(backtest_row)
    await session.flush()

    for t in result.trades:
        session.add(
            BacktestTrade(
                backtest_id=backtest_row.id,
                segment=t.segment,
                direction=t.direction,
                entry_time=t.entry_time,
                entry_price=t.entry_price,
                exit_time=t.exit_time,
                exit_price=t.exit_price,
                size=t.size,
                stop_loss=t.stop_loss,
                take_profit=t.take_profit,
                pnl=t.pnl,
                entry_reasons=[{"status": r.status, "text": r.text, "points": r.points} for r in t.entry_reasons],
                exit_reason=t.exit_reason,
            )
        )
    await session.commit()
    await session.refresh(backtest_row)

    return {
        "id": str(backtest_row.id),
        "summary": result.summary,
        "equity_curve": result.equity_curve,
        "trade_count": len(result.trades),
    }


class ParamGridIn(BaseModel):
    # Deliberately small by default — each combination runs a full backtest
    # per window (see MAX_GRID_CANDIDATES below); this is a synchronous
    # request (docs/09_BACKTEST_DESIGN.md's rationale for POST /backtests
    # applies here too, more so). Widen the grid explicitly if you want a
    # deeper search and are prepared to wait longer.
    stop_loss_pips: list[float] = Field(default_factory=lambda: [20.0, 30.0])
    take_profit_pips: list[float] = Field(default_factory=lambda: [40.0, 60.0])
    min_score_threshold: list[int] = Field(default_factory=lambda: [60])


class WalkForwardRequestIn(BaseModel):
    pair: str
    timeframe: Granularity = Granularity.M15
    candle_count: int = Field(default=1200, ge=700, le=5000)
    train_bars: int = Field(default=400, ge=100)
    test_bars: int = Field(default=120, ge=30)
    step_bars: int | None = Field(default=None, ge=1)
    initial_capital: float = 1_000_000.0
    risk_pct: float = 1.0
    spread_pips: float = 1.5
    slippage_pips: float = 0.3
    commission_per_lot: float = 0.0
    param_grid: ParamGridIn = Field(default_factory=ParamGridIn)


MAX_GRID_CANDIDATES = 60  # bounds request cost: candidates * windows full-engine runs


@router.post("/walk-forward")
async def run_walk_forward_analysis(
    body: WalkForwardRequestIn,
    broker: BrokerAdapter = Depends(get_broker),
) -> dict:
    """Walk-forward analysis (docs/09_BACKTEST_DESIGN.md, docs/14_IMPLEMENTATION_PLAN.md).

    Deliberately stateless / not persisted to the DB — unlike `POST
    /backtests`, this is treated as an exploratory analysis tool rather than
    a saved run. It returns per-window results, a combined out-of-sample
    curve, parameter-stability flags, and an overfitting warning where
    applicable; it never returns anything that reads as "apply these
    parameters" — see `app/services/backtest/walk_forward.py`'s module
    docstring for why.
    """
    grid = ParamGrid(
        stop_loss_pips=body.param_grid.stop_loss_pips,
        take_profit_pips=body.param_grid.take_profit_pips,
        min_score_threshold=body.param_grid.min_score_threshold,
    )
    candidate_count = len(grid.candidates())
    if candidate_count > MAX_GRID_CANDIDATES:
        raise HTTPException(
            400,
            f"param_grid has {candidate_count} combinations, exceeding the {MAX_GRID_CANDIDATES} cap "
            "(each combination runs a full backtest per window) — narrow the grid.",
        )

    candles = await broker.get_candles(body.pair, body.timeframe, body.candle_count)
    higher_tf_candles = {}
    for label, gran in HIGHER_TF.get(body.timeframe, {}).items():
        higher_tf_candles[label] = await broker.get_candles(body.pair, gran, body.candle_count)

    config = WalkForwardConfig(
        pair=body.pair,
        timeframe=body.timeframe,
        train_bars=body.train_bars,
        test_bars=body.test_bars,
        step_bars=body.step_bars,
        initial_capital=body.initial_capital,
        risk_pct=body.risk_pct,
        spread_pips=body.spread_pips,
        slippage_pips=body.slippage_pips,
        commission_per_lot=body.commission_per_lot,
        param_grid=grid,
    )
    result = run_walk_forward(config, candles, higher_tf_candles)

    return {
        "windows": [
            {
                "window_index": w.window_index,
                "train_start": w.train_start.isoformat(),
                "train_end": w.train_end.isoformat(),
                "test_start": w.test_start.isoformat(),
                "test_end": w.test_end.isoformat(),
                "chosen_params": w.chosen_params,
                "train_metrics": w.train_metrics,
                "test_metrics": w.test_metrics,
                "candidates_evaluated": w.candidates_evaluated,
            }
            for w in result.windows
        ],
        "combined_test_metrics": result.combined_test_metrics,
        "combined_test_equity_curve": result.combined_test_equity_curve,
        "parameter_stability": [
            {
                "param": s.param,
                "values_by_window": s.values_by_window,
                "most_common_value": s.most_common_value,
                "agreement_ratio": s.agreement_ratio,
                "is_stable": s.is_stable,
            }
            for s in result.parameter_stability
        ],
        "overfitting_warning": result.overfitting_warning,
        "disclaimer": result.disclaimer,
    }


@router.get("/{backtest_id}")
async def get_backtest(backtest_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> dict:
    backtest = await session.get(Backtest, backtest_id)
    if backtest is None:
        raise HTTPException(404, "backtest not found")
    return {
        "id": str(backtest.id),
        "config": backtest.config,
        "summary": backtest.summary,
        "equity_curve": backtest.equity_curve,
        "status": backtest.status,
        "created_at": backtest.created_at.isoformat(),
    }


@router.get("/{backtest_id}/trades")
async def list_backtest_trades(backtest_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await session.execute(select(BacktestTrade).where(BacktestTrade.backtest_id == backtest_id))
    trades = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "segment": t.segment,
            "direction": t.direction,
            "entry_time": t.entry_time.isoformat(),
            "entry_price": t.entry_price,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "exit_price": t.exit_price,
            "size": t.size,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "pnl": t.pnl,
            "entry_reasons": t.entry_reasons,
            "exit_reason": t.exit_reason,
        }
        for t in trades
    ]


@router.get("/{backtest_id}/trades/{trade_id}")
async def get_backtest_trade(backtest_id: uuid.UUID, trade_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> dict:
    trade = await session.get(BacktestTrade, trade_id)
    if trade is None or trade.backtest_id != backtest_id:
        raise HTTPException(404, "trade not found")
    return {
        "id": str(trade.id),
        "segment": trade.segment,
        "direction": trade.direction,
        "entry_time": trade.entry_time.isoformat(),
        "entry_price": trade.entry_price,
        "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
        "exit_price": trade.exit_price,
        "pnl": trade.pnl,
        "entry_reasons": trade.entry_reasons,
        "exit_reason": trade.exit_reason,
    }
