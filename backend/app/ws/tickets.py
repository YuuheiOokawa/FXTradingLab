"""Short-lived, single-use WebSocket auth tickets.

Replaces the previous design (a long-lived shared bearer token passed as a
`?token=` WS query param — the same secret the browser used for REST) with a
ticket that (a) only this backend can mint, gated behind the normal
`require_auth` bearer check on `POST /api/v1/system/ws-ticket`, (b) is valid
for a few seconds, and (c) is consumed — deleted from Redis — the instant a
connection attempt uses it, successful or not. A leaked ticket (browser
history, a proxy access log, a shoulder-surfed URL) is worthless almost
immediately and can never be replayed for a second connection.

Minting still requires the real bearer token; only the *frontend BFF* (which
holds that token server-side, never the browser — see
docs/11_SECURITY.md "BFF migration") ever calls the mint endpoint. The
browser only ever sees the resulting one-shot ticket.
"""
from __future__ import annotations

import secrets

from app.core.redis_client import get_redis

TICKET_TTL_SECONDS = 45
_KEY_PREFIX = "ws_ticket:"


async def mint_ticket() -> str:
    ticket = secrets.token_urlsafe(32)
    await get_redis().set(f"{_KEY_PREFIX}{ticket}", "1", ex=TICKET_TTL_SECONDS)
    return ticket


async def consume_ticket(ticket: str | None) -> bool:
    """True iff `ticket` was a still-valid, not-yet-used ticket — and it is
    now gone from Redis either way, so this can never return True twice for
    the same ticket."""
    if not ticket:
        return False
    value = await get_redis().getdel(f"{_KEY_PREFIX}{ticket}")
    return value is not None
