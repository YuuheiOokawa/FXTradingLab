"""Per-request correlation ID (docs/15_PRODUCTION_READINESS_REVIEW.md
"Observability" — structured logs need a request_id/order_id to correlate
"why did this order fail" across log lines from different modules)."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_order_id: ContextVar[str | None] = ContextVar("order_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def get_order_id() -> str | None:
    return _order_id.get()


def set_order_id(value: str | None) -> None:
    _order_id.set(value)


@contextmanager
def order_context(order_id: str):
    """Attaches `order_id` to every log line emitted while the wrapped block
    runs, then restores the previous value — not just clears it, since a
    long-lived task (e.g. app/services/auto_trader.py's FULL_AUTO loop) can
    nest or sequence multiple orders in the same asyncio Task, where a plain
    `set_order_id(None)` would incorrectly wipe an outer scope's ID rather
    than restoring it."""
    token = _order_id.set(order_id)
    try:
        yield
    finally:
        _order_id.reset(token)
