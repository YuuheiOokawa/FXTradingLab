"""Worker liveness heartbeat (docs/02_SYSTEM_ARCHITECTURE.md "Observability").

`system:broker_connected` already reflects whether the price stream itself is
flowing, but a worker process that's alive-but-stuck, or whose broker stream
died in a way that never updates that key, should still be distinguishable
from a worker process that isn't running at all (crashed, never deployed,
wrong start command — see docs/17_PRODUCTION_DEPLOYMENT_GUIDE.md's note about
the worker service needing a manual Start Command override on Railway). This
job just proves the worker's scheduler loop is alive, independent of
market-data specifics.
"""
from __future__ import annotations

from app.core.redis_client import get_redis

HEARTBEAT_KEY = "system:worker_heartbeat"
HEARTBEAT_TTL_SECONDS = 90  # generous vs. the 30s interval this job runs on


async def run() -> None:
    await get_redis().set(HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL_SECONDS)
