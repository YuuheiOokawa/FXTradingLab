"""Audit log writes for sensitive operations (docs/15_PRODUCTION_READINESS_
REVIEW.md "Audit Log") — deliberately separate from the general structured
application log (`app/core/logging.py`) and from `SystemEvent` (free-form
operational logging): this exists specifically so "what changed, and when,
for the handful of actions that matter for accountability" has one reliable
place to look, independent of log rotation/retention on the general log.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_request_id
from app.db.models.journal import AuditLog

# Never pass a raw secret/token/password value into `before`, `after`, or
# `context` — this module does not redact (unlike app/core/logging.py's
# filter, which exists for exactly this reason on the general log); the
# caller is responsible for only ever passing already-safe values.
ACTIONS = frozenset(
    {
        "login",
        "logout",
        "kill_switch_on",
        "kill_switch_off",
        "risk_setting_change",
        "live_trading_admin_enable",
        "live_trading_admin_disable",
        "live_order_preview",
        "live_order_submit",
        "live_order_reject",
        "live_order_result",
        # The broker refused the order outright.
        "live_order_broker_reject",
        # The connection dropped mid-submission, so the order MAY exist upstream.
        # Audited under its own action because it is the one outcome that needs a
        # human to reconcile against the broker rather than a retry.
        "live_order_unknown",
    }
)


async def write_audit_log(
    session: AsyncSession,
    action: str,
    *,
    actor: str = "operator",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> AuditLog:
    if action not in ACTIONS:
        raise ValueError(f"unknown audit action {action!r} — add it to app.services.audit.ACTIONS deliberately")
    entry = AuditLog(
        ts=datetime.now(UTC),
        actor=actor,
        action=action,
        before=before,
        after=after,
        context=context or {},
        request_id=get_request_id(),
    )
    session.add(entry)
    return entry
