"""Worker heartbeat job (docs/02_SYSTEM_ARCHITECTURE.md "Observability")."""
from app.core.redis_client import get_redis
from app.worker.jobs import heartbeat


async def test_run_sets_a_ttl_bounded_key():
    redis = get_redis()
    await redis.delete(heartbeat.HEARTBEAT_KEY)

    await heartbeat.run()

    value = await redis.get(heartbeat.HEARTBEAT_KEY)
    assert value == "1"
    ttl = await redis.ttl(heartbeat.HEARTBEAT_KEY)
    assert 0 < ttl <= heartbeat.HEARTBEAT_TTL_SECONDS
