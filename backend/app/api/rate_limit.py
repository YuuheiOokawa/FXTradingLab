"""Fixed-window rate limiting for /api/v1/* — docs/11_SECURITY.md "Rate limiting".

Found as a real gap during docs/15_PRODUCTION_READINESS_REVIEW.md: a
determined actor holding (or having leaked) the shared bearer token could
hammer the API with no limit. This closes that gap with a simple Redis
counter — adequate for a single-operator app; not a distributed rate limiter
and not meant to be one.
"""
from __future__ import annotations

import logging
import time

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


async def rate_limit(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Keyed by the bearer token — the actual identity in this
    single-operator model — falling back to client IP only when auth is
    disabled. Skipped entirely in development, same as `require_auth`, so
    local iteration (including a hot-reloading frontend polling aggressively)
    never gets a 429. Fails open (allows the request) if Redis itself is
    unreachable — a transient Redis blip should not compound into every API
    call failing; `/ready` already surfaces a Redis outage separately.
    """
    if not settings.auth_required:
        return

    identity = authorization or (request.client.host if request.client else "unknown")
    window = int(time.time() // 60)
    key = f"ratelimit:{identity}:{window}"

    try:
        redis_client = get_redis()
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
    except Exception:
        logger.exception("rate limit check failed open (redis unavailable)")
        return

    if count > settings.rate_limit_per_minute:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"rate limit exceeded ({settings.rate_limit_per_minute}/min) — retry after a short wait",
        )
