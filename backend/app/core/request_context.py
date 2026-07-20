"""Per-request correlation ID (docs/15_PRODUCTION_READINESS_REVIEW.md
"Observability" — structured logs need a request_id/order_id to correlate
"why did this order fail" across log lines from different modules)."""
from __future__ import annotations

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
