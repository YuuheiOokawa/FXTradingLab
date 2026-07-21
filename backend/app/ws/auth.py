"""WebSocket auth (docs/11_SECURITY.md "BFF migration").

Two checks, both skipped in development for convenience (exactly like
`require_auth` for REST, app/api/deps.py):

1. Origin allowlist — outside development, a WS handshake from an origin not
   in `ALLOWED_ORIGINS` is rejected before any ticket check, the same
   boundary `CORSMiddleware` enforces for REST (Starlette's WS routes don't
   run through that middleware, so this is a separate, explicit check).
2. A short-lived, single-use ticket (`app/ws/tickets.py`) passed as
   `?ticket=`. Browsers can't set custom headers on a WS handshake, so this
   replaces the REST `Authorization: Bearer` scheme — but unlike the shared
   bearer token itself (the previous design here), a ticket is minted
   per-connection-attempt and can never be replayed, so it's safe to hand to
   the browser even though it travels in a URL (browser history, proxy
   logs, etc).
"""
from __future__ import annotations

from fastapi import WebSocket

from app.core.config import get_settings
from app.ws.tickets import consume_ticket


async def check_ws_auth(websocket: WebSocket) -> bool:
    """Returns True if the connection is authorized. Callers must close the
    socket (with a policy-violation code) themselves if this returns False —
    FastAPI requires the handshake to be accepted before a controlled close."""
    settings = get_settings()

    if settings.auth_required and settings.allowed_origins_list:
        origin = websocket.headers.get("origin")
        if origin and origin not in settings.allowed_origins_list:
            return False

    if not settings.auth_required:
        return True

    ticket = websocket.query_params.get("ticket")
    return await consume_ticket(ticket)
