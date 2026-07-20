"""WebSocket auth (docs/15_PRODUCTION_READINESS_REVIEW.md "Security").

Browsers can't set custom headers on a WebSocket handshake, so REST's
`Authorization: Bearer` scheme doesn't apply directly — the token is instead
passed as a `?token=` query parameter and validated here before `accept()`.
Skipped in development for convenience, exactly like `require_auth` for REST
(app/api/deps.py) — enforced everywhere else.
"""
from __future__ import annotations

from fastapi import WebSocket

from app.core.config import get_settings


async def check_ws_auth(websocket: WebSocket) -> bool:
    """Returns True if the connection is authorized. Callers must close the
    socket (with a policy-violation code) themselves if this returns False —
    FastAPI requires the handshake to be accepted before a controlled close."""
    settings = get_settings()
    if not settings.auth_required:
        return True
    if not settings.app_api_token:
        return False
    token = websocket.query_params.get("token")
    return token == settings.app_api_token
