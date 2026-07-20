"""Event-driven, bar-by-bar backtest engine (docs/09_BACKTEST_DESIGN.md).

Deliberately not a pure vectorized backtest: exit logic (SL/TP/trailing) needs
intrabar high/low, not just close, to be realistic. Each bar's signal evaluation
only ever sees candles up to and including that bar — no lookahead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd

from app.brokers.schemas import Candle, Granularity
from app.services.backtest.metrics import compute_metrics
from app.services.signal_engine import Reason, SignalResult, evaluate

Segment = Literal["in_sample", "out_of_sample"]

MIN_SCORE_THRESHOLD = 55  # matches "買い"/"売り" label floor (docs/08_SIGNAL_ENGINE.md)
INDICATOR_WINDOW = 260  # bars of context handed to the signal engine each step (EMA200 warmup + margin)


def pip_size_for(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


@dataclass
class BacktestConfig:
    pair: str
    timeframe: Granularity
    initial_capital: float = 1_000_000.0
    risk_pct: float = 1.0
    spread_pips: float = 1.5
    slippage_pips: float = 0.3
    commission_per_lot: float = 0.0
    stop_loss_pips: float = 30.0
    take_profit_pips: float = 60.0
    trailing_stop_pips: float | None = None
    in_sample_ratio: float = 0.7
    min_score_threshold: int = MIN_SCORE_THRESHOLD


@dataclass
class TradeRecord:
    segment: Segment
    direction: Literal["BUY", "SELL"]
    entry_time: datetime
    entry_price: float
    size: float
    stop_loss: float | None
    take_profit: float | None
    entry_reasons: list[Reason] = field(default_factory=list)
    exit_time: datetime | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    exit_reason: str = ""


@dataclass
class BacktestResult:
    trades: list[TradeRecord]
    equity_curve: list[dict]
    summary: dict


def _candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": [c.open_time for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )


class BacktestEngine:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.pip = pip_size_for(config.pair)

    def run(
        self,
        candles: list[Candle],
        higher_tf_candles: dict[str, list[Candle]] | None = None,
    ) -> BacktestResult:
        higher_tf_candles = higher_tf_candles or {}
        df = _candles_to_df(candles)
        higher_dfs = {tf: _candles_to_df(c) for tf, c in higher_tf_candles.items()}
        higher_times = {tf: d["open_time"].to_numpy() for tf, d in higher_dfs.items()}

        split_index = int(len(df) * self.config.in_sample_ratio)

        trades: list[TradeRecord] = []
        equity_curve: list[dict] = []
        balance = self.config.initial_capital
        position: TradeRecord | None = None
        trail_extreme: float | None = None  # best price since entry, for trailing stop

        for i in range(len(df)):
            row = df.iloc[i]
            segment: Segment = "in_sample" if i < split_index else "out_of_sample"

            if position is not None:
                position, balance, trail_extreme, closed = self._update_open_position(
                    position, row, balance, trail_extreme
                )
                if closed:
                    trades.append(position)
                    position = None
                    trail_extreme = None

            if position is None and i >= 200:
                window = df.iloc[max(0, i - INDICATOR_WINDOW + 1) : i + 1]
                higher_window = {}
                for tf, d in higher_dfs.items():
                    idx = int(np.searchsorted(higher_times[tf], row["open_time"], side="right"))
                    if idx == 0:
                        continue
                    higher_window[tf] = d.iloc[max(0, idx - INDICATOR_WINDOW) : idx]
                signal = evaluate(window, higher_window)
                if signal.score >= self.config.min_score_threshold:
                    position = self._open_position(signal, row, segment)
                    trail_extreme = position.entry_price

            equity = balance + (self._unrealized_pnl(position, row["close"]) if position else 0.0)
            equity_curve.append({"time": row["open_time"].isoformat(), "equity": equity})

        if position is not None:
            last_row = df.iloc[-1]
            price = last_row["close"]
            position.exit_time = last_row["open_time"]
            position.exit_price = price
            position.pnl = self._pnl(position, price)
            position.exit_reason = "End of backtest — force closed"
            balance += position.pnl
            trades.append(position)
            equity_curve[-1]["equity"] = balance

        overall = compute_metrics(trades, self.config.initial_capital, equity_curve)
        is_trades = [t for t in trades if t.segment == "in_sample"]
        oos_trades = [t for t in trades if t.segment == "out_of_sample"]
        is_curve = equity_curve[:split_index] or equity_curve
        oos_curve = equity_curve[split_index:] or equity_curve
        summary = {
            "overall": overall,
            "in_sample": compute_metrics(is_trades, self.config.initial_capital, is_curve),
            "out_of_sample": compute_metrics(
                oos_trades,
                is_curve[-1]["equity"] if is_curve else self.config.initial_capital,
                oos_curve,
            ),
        }
        return BacktestResult(trades=trades, equity_curve=equity_curve, summary=summary)

    def _open_position(self, signal: SignalResult, row: pd.Series, segment: Segment) -> TradeRecord:
        close = float(row["close"])
        spread = self.config.spread_pips * self.pip
        slippage = self.config.slippage_pips * self.pip
        if signal.direction == "BUY":
            entry_price = close + spread / 2 + slippage
            stop_loss = entry_price - self.config.stop_loss_pips * self.pip
            take_profit = entry_price + self.config.take_profit_pips * self.pip
        else:
            entry_price = close - spread / 2 - slippage
            stop_loss = entry_price + self.config.stop_loss_pips * self.pip
            take_profit = entry_price - self.config.take_profit_pips * self.pip

        risk_amount = self.config.initial_capital * self.config.risk_pct / 100
        sl_distance = abs(entry_price - stop_loss)
        size = (risk_amount / sl_distance) if sl_distance > 0 else 0.0

        return TradeRecord(
            segment=segment,
            direction=signal.direction,
            entry_time=row["open_time"],
            entry_price=entry_price,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_reasons=signal.reasons,
        )

    def _update_open_position(
        self, position: TradeRecord, row: pd.Series, balance: float, trail_extreme: float | None
    ) -> tuple[TradeRecord | None, float, float | None, bool]:
        high, low = float(row["high"]), float(row["low"])
        direction = position.direction

        if self.config.trailing_stop_pips is not None and trail_extreme is not None:
            trail_dist = self.config.trailing_stop_pips * self.pip
            if direction == "BUY":
                trail_extreme = max(trail_extreme, high)
                candidate_stop = trail_extreme - trail_dist
                if position.stop_loss is None or candidate_stop > position.stop_loss:
                    position.stop_loss = candidate_stop
            else:
                trail_extreme = min(trail_extreme, low)
                candidate_stop = trail_extreme + trail_dist
                if position.stop_loss is None or candidate_stop < position.stop_loss:
                    position.stop_loss = candidate_stop

        exit_price: float | None = None
        exit_reason = ""
        if direction == "BUY":
            if position.stop_loss is not None and low <= position.stop_loss:
                exit_price, exit_reason = position.stop_loss, "SL hit"
            elif position.take_profit is not None and high >= position.take_profit:
                exit_price, exit_reason = position.take_profit, "TP hit"
        else:
            if position.stop_loss is not None and high >= position.stop_loss:
                exit_price, exit_reason = position.stop_loss, "SL hit"
            elif position.take_profit is not None and low <= position.take_profit:
                exit_price, exit_reason = position.take_profit, "TP hit"

        if exit_price is None:
            return position, balance, trail_extreme, False

        position.exit_time = row["open_time"]
        position.exit_price = exit_price
        position.pnl = self._pnl(position, exit_price)
        position.exit_reason = exit_reason
        balance += position.pnl
        return position, balance, trail_extreme, True

    def _pnl(self, position: TradeRecord, exit_price: float) -> float:
        diff = (exit_price - position.entry_price) if position.direction == "BUY" else (position.entry_price - exit_price)
        commission = self.config.commission_per_lot * (position.size / 100_000)
        return diff * position.size - commission

    def _unrealized_pnl(self, position: TradeRecord | None, current_close: float) -> float:
        if position is None:
            return 0.0
        return self._pnl(position, float(current_close))
