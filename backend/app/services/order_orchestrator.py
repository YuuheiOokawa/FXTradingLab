"""Order Orchestrator — the only code allowed to call `BrokerAdapter.create_order`
or `close_position` (docs/10_RISK_MANAGEMENT.md). Every entry unconditionally goes
through `RiskEngine.validate()` first; nothing here may skip that call.

Paper trading never touches `BrokerAdapter.create_order` at all — it uses the
broker only for price *reads*, and simulates the fill/position book itself, so a
paper order can never, even by a future bug, become a real broker order.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerAdapter
from app.brokers.errors import BrokerConnectionError
from app.brokers.schemas import OrderRequest
from app.core.config import Settings, get_settings
from app.db.models.journal import SystemEvent, TradeJournal
from app.db.models.market import Instrument
from app.db.models.trading import LiveOrder, LivePosition, PaperAccount, PaperOrder, PaperPosition
from app.services.repo import get_instrument_by_symbol, get_or_create_paper_account, get_or_create_risk_settings
from app.services.risk_engine import RiskContext, RiskEngine, RiskRejected

_engine = RiskEngine()


class LiveTradingDisabled(Exception):
    def __init__(self, missing_gates: list[str]) -> None:
        super().__init__(f"LIVE trading disabled: missing gates {missing_gates}")
        self.missing_gates = missing_gates


def pip_size_for(symbol: str) -> float:
    return 0.01 if symbol.endswith("JPY") else 0.0001


async def _consecutive_losses(session: AsyncSession, source: str) -> int:
    result = await session.execute(
        select(TradeJournal.pnl)
        .where(TradeJournal.source == source)
        .order_by(TradeJournal.closed_at.desc())
        .limit(50)
    )
    count = 0
    for (pnl,) in result.all():
        if pnl < 0:
            count += 1
        else:
            break
    return count


async def _today_realized_pnl(session: AsyncSession, source: str) -> float:
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(TradeJournal.pnl).where(TradeJournal.source == source, TradeJournal.closed_at >= today_start)
    )
    return sum(pnl for (pnl,) in result.all())


async def _log_event(session: AsyncSession, category: str, severity: str, message: str, context: dict | None = None) -> None:
    session.add(SystemEvent(ts=datetime.now(UTC), category=category, severity=severity, message=message, context=context or {}))


async def _notify(session: AsyncSession, kind: str, title: str, body: str) -> None:
    from app.services.notifications.channel import notify

    await notify(session, kind, title, body)


@dataclass
class OrderOutcome:
    approved: bool
    order: PaperOrder | LiveOrder | None = None
    position: PaperPosition | LivePosition | None = None
    rejection_code: str | None = None
    rejection_message: str | None = None


class OrderOrchestrator:
    def __init__(
        self,
        broker: BrokerAdapter,
        settings: Settings | None = None,
        trading_broker: BrokerAdapter | None = None,
    ) -> None:
        """`broker` is the market-data source used for every price read (paper
        fills, live account/position display). `trading_broker` (defaults to
        `broker` when not given) is where LIVE orders actually get submitted —
        see docs/15_PRODUCTION_READINESS_REVIEW.md "BrokerAdapter split". Paper
        trading never touches `trading_broker` at all."""
        self._broker = broker
        self._trading_broker = trading_broker or broker
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------ paper --

    async def submit_paper_order(self, session: AsyncSession, order: OrderRequest) -> OrderOutcome:
        existing = await session.execute(
            select(PaperOrder).where(PaperOrder.idempotency_key == order.idempotency_key)
        )
        dup = existing.scalar_one_or_none()
        if dup is not None:
            # Idempotent replay: return the original result without re-running risk
            # checks or creating a second position (docs/10_RISK_MANAGEMENT.md).
            if dup.status == "rejected":
                raise RiskRejected(dup.reject_reason or "REJECTED", dup.reject_reason or "rejected")
            position_result = await session.execute(
                select(PaperPosition).where(PaperPosition.opening_idempotency_key == dup.idempotency_key)
            )
            return OrderOutcome(approved=True, order=dup, position=position_result.scalars().first())

        if order.order_type in ("limit", "stop") and order.limit_price is None:
            raise ValueError(f"order_type={order.order_type!r} requires limit_price")

        risk_settings = await get_or_create_risk_settings(session)
        account = await get_or_create_paper_account(session)
        instrument = await get_instrument_by_symbol(session, order.instrument)
        if instrument is None:
            raise ValueError(f"unknown instrument {order.instrument}")

        pip = pip_size_for(order.instrument)
        slippage = self._settings.paper_slippage_pips * pip
        try:
            quote = await self._broker.get_current_price(order.instrument)
            broker_connected = True
            spread_pips = quote.spread / pip
            # A successful fetch does NOT by itself mean the quote is fresh —
            # a broker call can return 200 with a genuinely stale/cached
            # price (docs/15_PRODUCTION_READINESS_REVIEW.md "Fail-closed
            # trading safety audit"). Compare the quote's own timestamp
            # (OANDA's server-side quote-generation time, not local receive
            # time — see app/brokers/oanda.py::get_current_price) against
            # PRICE_STALE_SECONDS, the same threshold the realtime tick
            # pipeline uses. This used to be inferred from broker_connected
            # alone, which never caught this case at all.
            price_age = (datetime.now(UTC) - quote.ts).total_seconds()
            price_stale = price_age > self._settings.price_stale_seconds
            if order.order_type == "market":
                # Slippage is an adverse offset - the actual fill is always
                # slightly worse than the quoted price, same convention the
                # backtest engine uses (docs/09_BACKTEST_DESIGN.md). Limit/stop
                # orders fill exactly at their trigger price once crossed (see
                # the pending-order fill path below), matching how a real
                # broker treats a satisfied limit price differently from a
                # market order's execution risk.
                fill_price = (quote.ask + slippage) if order.direction == "BUY" else (quote.bid - slippage)
            else:
                fill_price = 0.0  # not filled yet; set for real when the pending order triggers
        except BrokerConnectionError:
            broker_connected = False
            price_stale = True
            spread_pips = 0.0
            fill_price = 0.0

        open_positions_result = await session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.status == "open")
        )
        open_positions = open_positions_result.scalars().all()
        same_symbol_count = sum(1 for p in open_positions if p.instrument_id == instrument.id)

        # For a pending limit/stop order, fill_price isn't known yet - the
        # order's own limit_price is the best available reference for a
        # risk-amount estimate at placement time.
        risk_reference_price = fill_price if order.order_type == "market" else (order.limit_price or 0.0)
        risk_amount = abs(risk_reference_price - order.stop_loss) * order.size if order.stop_loss is not None else 0.0
        today_pnl = await _today_realized_pnl(session, "paper")
        equity = account.balance
        daily_loss_pct = max(0.0, -today_pnl) / equity * 100 if equity > 0 else 0.0
        drawdown_pct = max(0.0, (account.high_water_mark - equity) / account.high_water_mark * 100) if account.high_water_mark > 0 else 0.0
        consecutive = await _consecutive_losses(session, "paper")

        ctx = RiskContext(
            kill_switch_active=risk_settings.kill_switch_active,
            broker_connected=broker_connected,
            price_stale=price_stale,
            current_spread_pips=spread_pips,
            max_spread_pips=risk_settings.max_spread_pips_default,
            equity=equity,
            risk_amount=risk_amount,
            max_risk_per_trade_pct=risk_settings.max_risk_per_trade_pct,
            daily_loss_pct=daily_loss_pct,
            max_daily_loss_pct=risk_settings.max_daily_loss_pct,
            current_drawdown_pct=drawdown_pct,
            max_drawdown_pct=risk_settings.max_drawdown_pct,
            open_position_count=len(open_positions),
            max_concurrent_positions=risk_settings.max_concurrent_positions,
            same_symbol_open_count=same_symbol_count,
            max_same_symbol_positions=risk_settings.max_same_symbol_positions,
            consecutive_losses=consecutive,
            consecutive_loss_stop_count=risk_settings.consecutive_loss_stop_count,
            is_duplicate_idempotency_key=False,  # handled by the early-return above
        )
        result = _engine.validate(ctx)

        if not result.approved:
            rejected_row = PaperOrder(
                account_id=account.id,
                instrument_id=instrument.id,
                direction=order.direction,
                size=order.size,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                status="rejected",
                reject_reason=result.code,
                idempotency_key=order.idempotency_key,
                created_at=datetime.now(UTC),
            )
            session.add(rejected_row)
            await _log_event(session, "risk", "warning", f"paper order rejected: {result.code}", {"message": result.message})
            await _notify(session, "risk_reject", "注文が拒否されました", result.message or "")
            await session.commit()
            raise RiskRejected(result.code or "REJECTED", result.message or "rejected")

        if order.order_type != "market":
            # Limit/stop: no position opens yet - the order sits pending
            # until app/worker/jobs/paper_pending_orders.py sees the trigger
            # price crossed on a subsequent tick. Design deliberately leaves
            # room for partial fills later (a pending order could split into
            # several smaller PaperPosition rows referencing the same
            # opening_idempotency_key) without changing this shape - not
            # needed yet, per docs/01_REQUIREMENTS.md's explicit scope.
            pending_order = PaperOrder(
                account_id=account.id,
                instrument_id=instrument.id,
                direction=order.direction,
                size=order.size,
                order_type=order.order_type,
                limit_price=order.limit_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                status="pending",
                idempotency_key=order.idempotency_key,
                created_at=datetime.now(UTC),
            )
            session.add(pending_order)
            await _log_event(
                session,
                "order",
                "info",
                f"paper {order.order_type} order placed (pending): {order.instrument} {order.direction} @ {order.limit_price}",
            )
            await session.commit()
            return OrderOutcome(approved=True, order=pending_order, position=None)

        filled_order = PaperOrder(
            account_id=account.id,
            instrument_id=instrument.id,
            direction=order.direction,
            size=order.size,
            order_type="market",
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            status="filled",
            idempotency_key=order.idempotency_key,
            created_at=datetime.now(UTC),
        )
        position = PaperPosition(
            account_id=account.id,
            instrument_id=instrument.id,
            direction=order.direction,
            size=order.size,
            entry_price=fill_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            opened_at=datetime.now(UTC),
            status="open",
            opening_idempotency_key=order.idempotency_key,
        )
        session.add_all([filled_order, position])
        await _log_event(session, "order", "info", f"paper order filled: {order.instrument} {order.direction}")
        await session.commit()
        return OrderOutcome(approved=True, order=filled_order, position=position)

    async def close_paper_position(self, session: AsyncSession, position_id: uuid.UUID) -> PaperPosition:
        position = await session.get(PaperPosition, position_id)
        if position is None or position.status != "open":
            raise ValueError("position not open")
        instrument_row = await session.get(Instrument, position.instrument_id)
        quote = await self._broker.get_current_price(instrument_row.symbol)
        price = quote.bid if position.direction == "BUY" else quote.ask
        pnl = (price - position.entry_price) if position.direction == "BUY" else (position.entry_price - price)
        pnl *= position.size

        account = await session.get(PaperAccount, position.account_id)
        account.balance += pnl
        account.high_water_mark = max(account.high_water_mark, account.balance)

        position.status = "closed"
        position.closed_at = datetime.now(UTC)
        position.close_price = price
        position.realized_pnl = pnl

        session.add(
            TradeJournal(
                source="paper",
                source_ref_id=position.id,
                pair=instrument_row.symbol,
                direction=position.direction,
                entry_time=position.opened_at,
                entry_price=position.entry_price,
                exit_time=position.closed_at,
                exit_price=price,
                size=position.size,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                pnl=pnl,
                reason="manual close",
                closed_at=position.closed_at,
            )
        )
        await _log_event(session, "order", "info", f"paper position closed: {instrument_row.symbol} pnl={pnl:.2f}")
        await session.commit()
        return position

    async def try_fill_pending_order(self, session: AsyncSession, pending_order: PaperOrder) -> PaperPosition | None:
        """Checks one pending limit/stop order against the current quote and
        fills it if triggered. Returns None (leaving the order pending,
        unchanged) if not triggered, the broker is unreachable, or the kill
        switch is active — a pending order must never silently turn into a
        real position while the kill switch is on, mirroring the "kill
        switch checked before anything else" rule entry orders already
        follow (docs/10_RISK_MANAGEMENT.md)."""
        if pending_order.status != "pending":
            return None
        risk_settings = await get_or_create_risk_settings(session)
        if risk_settings.kill_switch_active:
            return None

        instrument_row = await session.get(Instrument, pending_order.instrument_id)
        try:
            quote = await self._broker.get_current_price(instrument_row.symbol)
        except BrokerConnectionError:
            return None
        # Same fail-closed rule as order entry (submit_paper_order above): a
        # successful fetch is not proof of freshness. A pending order must
        # never fill against a stale quote just because the broker call
        # itself didn't raise (docs/15_PRODUCTION_READINESS_REVIEW.md
        # "Fail-closed trading safety audit") — leave it pending and let the
        # next poll (10s later) try again with a fresh quote instead.
        if (datetime.now(UTC) - quote.ts).total_seconds() > self._settings.price_stale_seconds:
            return None

        pip = pip_size_for(instrument_row.symbol)
        slippage = self._settings.paper_slippage_pips * pip
        triggered = False
        fill_price = 0.0
        if pending_order.order_type == "limit":
            # A limit order seeks a BETTER-than-current price and fills
            # exactly at that price once the market reaches it.
            if pending_order.direction == "BUY" and quote.ask <= pending_order.limit_price:
                triggered, fill_price = True, pending_order.limit_price
            elif pending_order.direction == "SELL" and quote.bid >= pending_order.limit_price:
                triggered, fill_price = True, pending_order.limit_price
        elif pending_order.order_type == "stop":
            # A stop order becomes a market order once the trigger is
            # crossed, so it carries the same slippage a market order would.
            if pending_order.direction == "BUY" and quote.ask >= pending_order.limit_price:
                triggered, fill_price = True, quote.ask + slippage
            elif pending_order.direction == "SELL" and quote.bid <= pending_order.limit_price:
                triggered, fill_price = True, quote.bid - slippage

        if not triggered:
            return None

        position = PaperPosition(
            account_id=pending_order.account_id,
            instrument_id=pending_order.instrument_id,
            direction=pending_order.direction,
            size=pending_order.size,
            entry_price=fill_price,
            stop_loss=pending_order.stop_loss,
            take_profit=pending_order.take_profit,
            opened_at=datetime.now(UTC),
            status="open",
            opening_idempotency_key=pending_order.idempotency_key,
        )
        pending_order.status = "filled"
        session.add(position)
        await _log_event(
            session,
            "order",
            "info",
            f"paper {pending_order.order_type} order filled: {instrument_row.symbol} {pending_order.direction} @ {fill_price:.5f}",
        )
        await _notify(
            session, "order_filled", "指値/逆指値注文が約定しました", f"{instrument_row.symbol} {pending_order.direction} @ {fill_price:.5f}"
        )
        await session.commit()
        return position

    async def cancel_pending_order(self, session: AsyncSession, order_id: uuid.UUID) -> PaperOrder:
        order = await session.get(PaperOrder, order_id)
        if order is None or order.status != "pending":
            raise ValueError("order not pending")
        order.status = "cancelled"
        await session.commit()
        return order

    # ------------------------------------------------------------------- live --

    async def preview_live_order(self, session: AsyncSession, order: OrderRequest) -> dict:
        """Runs the exact Risk Engine validation and order-construction
        pipeline a real LIVE order would go through — real TRADING broker
        account/position state, real spread, real staleness check — but
        this method contains no call to `BrokerAdapter.create_order`
        anywhere in its body. That is a structural guarantee, not a flag
        that could be misconfigured: no code path through this function can
        ever place a real order, so it is deliberately NOT gated behind
        `check_live_gates()` — those three gates exist to protect against
        real execution, and there is nothing here to protect against
        (docs/15_PRODUCTION_READINESS_REVIEW.md "LIVE Trading Dry Run").

        Lets an operator verify Risk Engine sizing/limits and order
        construction work correctly against a real configured broker's real
        account state *before* ever flipping any of the three LIVE gates —
        including in `staging`, where `LIVE_TRADING_ENABLED` can never be
        true at all (`app/main.py`'s boot guard).
        """
        if order.order_type != "market":
            raise ValueError("preview_live_order only supports order_type='market' — LIVE execution itself is a stub (see submit_live_order)")

        risk_settings = await get_or_create_risk_settings(session)
        pip = pip_size_for(order.instrument)

        try:
            account = await self._trading_broker.get_account()
            quote = await self._trading_broker.get_current_price(order.instrument)
            positions = await self._trading_broker.get_positions()
            broker_connected = True
            spread_pips = quote.spread / pip
            price_age = (datetime.now(UTC) - quote.ts).total_seconds()
            price_stale = price_age > self._settings.price_stale_seconds
            estimated_entry = quote.ask if order.direction == "BUY" else quote.bid
        except BrokerConnectionError as exc:
            account = None
            positions = []
            broker_connected = False
            price_stale = True
            spread_pips = 0.0
            estimated_entry = None
            broker_error = str(exc)
        else:
            broker_error = None

        equity = account.equity if account is not None else 0.0
        open_position_count = len(positions)
        same_symbol_count = sum(1 for p in positions if p.instrument == order.instrument)
        risk_amount = (
            abs(estimated_entry - order.stop_loss) * order.size
            if estimated_entry is not None and order.stop_loss is not None
            else 0.0
        )
        today_pnl = await _today_realized_pnl(session, "live")
        daily_loss_pct = max(0.0, -today_pnl) / equity * 100 if equity > 0 else 0.0
        consecutive = await _consecutive_losses(session, "live")

        ctx = RiskContext(
            kill_switch_active=risk_settings.kill_switch_active,
            broker_connected=broker_connected,
            price_stale=price_stale,
            current_spread_pips=spread_pips,
            max_spread_pips=risk_settings.max_spread_pips_default,
            equity=equity,
            risk_amount=risk_amount,
            max_risk_per_trade_pct=risk_settings.max_risk_per_trade_pct,
            daily_loss_pct=daily_loss_pct,
            max_daily_loss_pct=risk_settings.max_daily_loss_pct,
            current_drawdown_pct=0.0,  # LIVE has no local high-water-mark table yet — see docs/14_IMPLEMENTATION_PLAN.md
            max_drawdown_pct=risk_settings.max_drawdown_pct,
            open_position_count=open_position_count,
            max_concurrent_positions=risk_settings.max_concurrent_positions,
            same_symbol_open_count=same_symbol_count,
            max_same_symbol_positions=risk_settings.max_same_symbol_positions,
            consecutive_losses=consecutive,
            consecutive_loss_stop_count=risk_settings.consecutive_loss_stop_count,
            is_duplicate_idempotency_key=False,
        )
        result = _engine.validate(ctx)

        preview = {
            "would_be_approved": result.approved,
            "reject_code": result.code,
            "reject_message": result.message,
            "instrument": order.instrument,
            "direction": order.direction,
            "size": order.size,
            "estimated_entry_price": estimated_entry,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "estimated_risk_amount": risk_amount,
            "account_equity": equity,
            "spread_pips": spread_pips,
            "price_stale": price_stale,
            "broker_connected": broker_connected,
            "broker_error": broker_error,
            "live_gates_satisfied": not self.check_live_gates(risk_settings.live_trading_admin_enabled, confirm_live=True),
        }
        await _log_event(
            session,
            "live_dry_run",
            "info",
            f"LIVE order preview: {order.direction} {order.instrument} x{order.size} -> "
            f"{'would approve' if result.approved else f'would reject ({result.code})'}",
            preview,
        )
        await session.commit()
        return preview

    def check_live_gates(self, risk_settings_admin_enabled: bool, confirm_live: bool) -> list[str]:
        """Returns the list of unmet gates (empty = all satisfied). Three
        independent conditions, all required (docs/10_RISK_MANAGEMENT.md)."""
        missing = []
        if not self._settings.live_trading_enabled:
            missing.append("LIVE_TRADING_ENABLED env var is false")
        if not risk_settings_admin_enabled:
            missing.append("admin setting live_trading_admin_enabled is false")
        if not confirm_live:
            missing.append("per-request confirm_live was not set")
        return missing

    async def submit_live_order(self, session: AsyncSession, order: OrderRequest, confirm_live: bool) -> OrderOutcome:
        risk_settings = await get_or_create_risk_settings(session)
        missing_gates = self.check_live_gates(risk_settings.live_trading_admin_enabled, confirm_live)
        if missing_gates:
            raise LiveTradingDisabled(missing_gates)

        # Real implementation would mirror submit_paper_order's RiskContext assembly
        # using self._trading_broker.get_account()/get_positions() instead of the
        # paper tables (note: self._trading_broker, not self._broker — the order
        # must go to the configured TRADING broker even if a different provider
        # is used for market data, see docs/15_PRODUCTION_READINESS_REVIEW.md),
        # then call self._trading_broker.create_order(order) only after RiskEngine
        # approval. Left minimal here: this path cannot be exercised without a
        # real funded broker account, which this build environment does not have
        # (see docs/14_IMPLEMENTATION_PLAN.md "Known gaps").
        raise LiveTradingDisabled(["LIVE order execution requires a configured, funded broker account"])

    # ------------------------------------------------------------------ kill --

    async def activate_kill_switch(self, session: AsyncSession, flatten_positions: bool) -> dict:
        risk_settings = await get_or_create_risk_settings(session)
        risk_settings.kill_switch_active = True
        await session.commit()
        await _log_event(session, "kill_switch", "warning", "Kill switch activated", {"flatten_positions": flatten_positions})
        await _notify(session, "kill_switch", "Kill Switchが作動しました", "新規注文と自動売買を停止しました。")

        flattened: list[str] = []
        if flatten_positions:
            open_positions = await session.execute(select(PaperPosition).where(PaperPosition.status == "open"))
            for position in open_positions.scalars().all():
                try:
                    await self.close_paper_position(session, position.id)
                    flattened.append(str(position.id))
                except Exception as exc:  # noqa: BLE001 - best-effort flatten, continue with remaining positions
                    await _log_event(session, "kill_switch", "error", f"failed to flatten position {position.id}: {exc}")
        await session.commit()
        return {"kill_switch_active": True, "flattened_positions": flattened}

    async def deactivate_kill_switch(self, session: AsyncSession) -> dict:
        risk_settings = await get_or_create_risk_settings(session)
        risk_settings.kill_switch_active = False
        await session.commit()
        await _log_event(session, "kill_switch", "info", "Kill switch deactivated")
        return {"kill_switch_active": False}
