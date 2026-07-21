"""Chaos test (docs/15_PRODUCTION_READINESS_REVIEW.md "Long-running / chaos
testing"): actually inject the failure modes the app is supposed to survive
— Redis down, Postgres down, worker killed, API killed, a flood of garbage
ticks, the rate limiter tripped — against a real running stack, and record
whether recovery is automatic or needs a human, not just assert it in a doc.

This script owns its own backend API + worker subprocesses (spawns them
itself so it can kill/restart them) and controls the system Postgres/Redis
services via `service postgresql`/`service redis-server` — the same
mechanism used elsewhere in this project's local dev workflow. It is NOT
meant to run against a shared/production database: it stops and starts
system-wide services. Point DATABASE_URL/REDIS_URL at disposable local
instances (e.g. the same ones `pytest` uses) before running this.

Requires passwordless (or already-elevated) access to `service
postgresql`/`service redis-server` — if that's not available in your
environment (e.g. Postgres/Redis run in Docker containers instead), adapt
the `_redis_down`/`_postgres_down` context managers to stop/start those
containers instead; the scenario logic itself is environment-agnostic.

Usage:
    cd backend && source .venv/bin/activate
    DATABASE_URL=postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab_test \
    REDIS_URL=redis://localhost:6379/1 \
    python -m scripts.chaos_test --i-understand-this-stops-postgres-and-redis
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import subprocess
import sys
import time

import httpx

API_BASE = "http://localhost:8000"
RESULTS: list[tuple[str, str, str]] = []  # (scenario, verdict, note)


def _record(scenario: str, verdict: str, note: str) -> None:
    RESULTS.append((scenario, verdict, note))
    print(f"  -> {verdict}: {note}")


def _wait_for(predicate, timeout: float, interval: float = 1.0, desc: str = "") -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _get(path: str, timeout: float = 3.0) -> httpx.Response | None:
    try:
        return httpx.get(f"{API_BASE}{path}", timeout=timeout)
    except httpx.HTTPError:
        return None


def _ready_ok() -> bool:
    resp = _get("/ready")
    return resp is not None and resp.status_code == 200


def _health_ok() -> bool:
    resp = _get("/health")
    return resp is not None and resp.status_code == 200


class Service:
    """Owns one long-running subprocess (the API or the worker) so this
    script can kill and relaunch it on demand."""

    def __init__(self, name: str, cmd: list[str], cwd: str, env: dict) -> None:
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.cmd, cwd=self.cwd, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def kill(self) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait(timeout=10)
            self.proc = None

    def restart(self) -> None:
        self.kill()
        self.start()


@contextlib.contextmanager
def _service_down(unit: str):
    subprocess.run(["service", unit, "stop"], check=False, capture_output=True)
    try:
        yield
    finally:
        subprocess.run(["service", unit, "start"], check=False, capture_output=True)


def scenario_redis_down() -> None:
    print("\n[Scenario] Redis stop -> /ready reflects it -> Redis restart -> auto-recovery?")
    with _service_down("redis-server"):
        down_detected = _wait_for(
            lambda: (r := _get("/ready")) is not None and r.status_code == 503 and r.json()["checks"]["redis"] is False,
            timeout=15,
        )
        if not down_detected:
            _record("redis_down", "FAIL", "/ready never reported redis down within 15s")
        else:
            _record("redis_down", "PASS", "/ready correctly reported redis down (fail-visible, not silently ignored)")
        # Rate limiting is documented to fail OPEN on a Redis outage — verify
        # that's actually true, not just claimed (docs/11_SECURITY.md).
        api_resp = _get("/api/v1/instruments")
        if api_resp is not None and api_resp.status_code == 200:
            _record("redis_down_rate_limit_fail_open", "PASS", "REST API still served requests with Redis down (documented fail-open)")
        else:
            _record(
                "redis_down_rate_limit_fail_open",
                "FAIL",
                f"REST API did not serve requests with Redis down (got {api_resp.status_code if api_resp else 'no response'}) — contradicts documented fail-open behavior",
            )
    recovered = _wait_for(_ready_ok, timeout=20)
    _record(
        "redis_down_recovery",
        "AUTO-RECOVERS" if recovered else "FAIL",
        "no API/worker restart needed — redis.asyncio reconnected on its own" if recovered else "/ready never recovered after Redis restart",
    )


def scenario_postgres_down() -> None:
    print("\n[Scenario] Postgres stop -> /ready reflects it -> Postgres restart -> auto-recovery?")
    with _service_down("postgresql"):
        down_detected = _wait_for(
            lambda: (r := _get("/ready")) is not None and r.status_code == 503 and r.json()["checks"]["database"] is False,
            timeout=15,
        )
        _record(
            "postgres_down",
            "PASS" if down_detected else "FAIL",
            "/ready correctly reported database down" if down_detected else "/ready never reported database down within 15s",
        )
        # A DB-touching endpoint must fail cleanly (5xx), not hang forever.
        start = time.monotonic()
        resp = _get("/api/v1/journal/trades?limit=1", timeout=10)
        elapsed = time.monotonic() - start
        if resp is not None and resp.status_code >= 500 and elapsed < 10:
            _record("postgres_down_fails_clean", "PASS", f"DB-backed endpoint returned {resp.status_code} in {elapsed:.1f}s, not a hang")
        else:
            _record(
                "postgres_down_fails_clean",
                "FAIL",
                f"DB-backed endpoint did not fail cleanly (status={resp.status_code if resp else None}, {elapsed:.1f}s)",
            )
    recovered = _wait_for(_ready_ok, timeout=20)
    _record(
        "postgres_down_recovery",
        "AUTO-RECOVERS" if recovered else "FAIL",
        "no API restart needed — pool_pre_ping reconnected on its own" if recovered else "/ready never recovered after Postgres restart",
    )


def scenario_worker_kill(worker: Service) -> None:
    print("\n[Scenario] Worker kill -> heartbeat goes stale -> manual restart required")
    worker.kill()
    stale_detected = _wait_for(
        lambda: (r := _get("/api/v1/system/status")) is not None and r.json().get("worker_alive") is False,
        timeout=100,  # heartbeat TTL is 90s
        interval=3,
    )
    _record(
        "worker_kill_detected",
        "PASS" if stale_detected else "FAIL",
        "worker_alive correctly flipped to false once the 90s heartbeat TTL expired" if stale_detected else "worker_alive never flipped to false",
    )
    worker.start()
    recovered = _wait_for(
        lambda: (r := _get("/api/v1/system/status")) is not None and r.json().get("worker_alive") is True,
        timeout=40,
    )
    _record(
        "worker_kill_recovery",
        "MANUAL (process-level)" if recovered else "FAIL",
        "restarting the process this script did manually brought worker_alive back — in a real deployment Railway's "
        "restartPolicyType=ON_FAILURE does this automatically, not a human, but a bare `python -m app.worker.main` "
        "left running locally has no supervisor of its own"
        if recovered
        else "worker_alive never recovered after restart",
    )


def scenario_api_kill(api: Service) -> None:
    print("\n[Scenario] API process kill -> unreachable -> manual restart required")
    api.kill()
    down_detected = _wait_for(lambda: not _health_ok(), timeout=10)
    _record("api_kill_detected", "PASS" if down_detected else "FAIL", "API became unreachable as expected" if down_detected else "API still reachable after kill (?)")
    api.start()
    recovered = _wait_for(_health_ok, timeout=20)
    _record(
        "api_kill_recovery",
        "MANUAL (process-level)" if recovered else "FAIL",
        "same as the worker: Railway's restart policy automates this in production; a bare local process does not"
        if recovered
        else "/health never recovered after restart",
    )


async def _scenario_abnormal_tick_flood() -> None:
    print("\n[Scenario] Flood of abnormal ticks -> all must be rejected, none corrupt the pipeline")
    import logging
    from datetime import UTC, datetime

    # validate_tick's rejection is logged at WARNING per-tick (correct for
    # real operation — a human should see these); silence it here purely so
    # this script's own output isn't 1000 lines of expected rejections.
    logging.getLogger("app.services.market_data").setLevel(logging.ERROR)

    from app.brokers.mock import MockAdapter
    from app.brokers.schemas import PriceQuote
    from app.core.redis_client import get_redis
    from app.services.market_data import MarketDataService, ensure_instruments

    redis = get_redis()
    broker = MockAdapter()
    service = MarketDataService(broker, redis)
    rows = await ensure_instruments(["CHAOS_USDJPY"])
    service._instrument_ids = {"CHAOS_USDJPY": str(rows["CHAOS_USDJPY"].id)}

    good = await broker.get_current_price("CHAOS_USDJPY")
    await service.handle_tick(good)
    last_good = service._last_valid_tick["CHAOS_USDJPY"]

    bad_ticks = [
        PriceQuote(instrument="CHAOS_USDJPY", bid=-1.0, ask=157.0, ts=datetime.now(UTC)),  # non-positive
        PriceQuote(instrument="CHAOS_USDJPY", bid=157.5, ask=157.0, ts=datetime.now(UTC)),  # bid >= ask
        PriceQuote(instrument="CHAOS_USDJPY", bid=157.0, ask=200.0, ts=datetime.now(UTC)),  # spread blowout
        PriceQuote(instrument="CHAOS_USDJPY", bid=200.0, ask=200.5, ts=datetime.now(UTC)),  # price jump
    ] * 250  # 1000 abnormal ticks total

    for tick in bad_ticks:
        await service.handle_tick(tick)

    still_good = service._last_valid_tick["CHAOS_USDJPY"]
    if still_good.bid == last_good.bid and still_good.ask == last_good.ask:
        _record("abnormal_tick_flood", "PASS", f"all {len(bad_ticks)} abnormal ticks rejected; last valid tick unchanged")
    else:
        _record("abnormal_tick_flood", "FAIL", "an abnormal tick corrupted the last-valid-tick state")

    from sqlalchemy import delete

    from app.db.models.market import Instrument, MarketTick
    from app.db.models.market import Candle as CandleModel
    from app.db.session import AsyncSessionLocal

    instrument_id = rows["CHAOS_USDJPY"].id
    async with AsyncSessionLocal() as session:
        # FK order matters: MarketTick/Candle reference Instrument.
        await session.execute(delete(MarketTick).where(MarketTick.instrument_id == instrument_id))
        await session.execute(delete(CandleModel).where(CandleModel.instrument_id == instrument_id))
        await session.execute(delete(Instrument).where(Instrument.id == instrument_id))
        await session.commit()


def scenario_rate_limit(api: Service, env: dict) -> None:
    print("\n[Scenario] Rate limit — must actually trip at the configured threshold")
    # Rate limiting (and auth) are skipped in APP_ENV=development, so this
    # scenario restarts the API in a non-dev mode with a low, fast-to-hit
    # limit rather than hammering the default 120/min for a full minute.
    limited_env = dict(env)
    limited_env["APP_ENV"] = "staging"
    limited_env["APP_API_TOKEN"] = "chaos-test-token"
    limited_env["ALLOWED_ORIGINS"] = "http://localhost:3000"
    limited_env["RATE_LIMIT_PER_MINUTE"] = "10"
    api.kill()
    api.env = limited_env
    api.start()
    if not _wait_for(_health_ok, timeout=20):
        _record("rate_limit", "FAIL", "API did not come back up in rate-limited test mode")
        return

    headers = {"Authorization": "Bearer chaos-test-token"}
    statuses = []
    for _ in range(15):
        resp = _get("/api/v1/instruments")
        # _get doesn't pass headers; do it directly here.
        resp = httpx.get(f"{API_BASE}/api/v1/instruments", headers=headers, timeout=3)
        statuses.append(resp.status_code)
    tripped = 429 in statuses
    first_429_at = statuses.index(429) + 1 if tripped else None
    _record(
        "rate_limit",
        "PASS" if tripped and first_429_at and first_429_at <= 12 else "FAIL",
        f"limit=10/min, got 429 at request #{first_429_at}" if tripped else f"never got a 429 across 15 requests: {statuses}",
    )
    # Restart back in plain dev mode for any scenario after this one.
    api.kill()
    api.env = env
    api.start()
    _wait_for(_health_ok, timeout=20)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--i-understand-this-stops-postgres-and-redis",
        action="store_true",
        dest="confirmed",
        help="required — this script stops and restarts system Postgres/Redis services",
    )
    args = parser.parse_args()
    if not args.confirmed:
        print("Refusing to run without --i-understand-this-stops-postgres-and-redis")
        print("(this script stops/restarts the system postgresql and redis-server services)")
        return 1

    env = dict(os.environ)
    env.setdefault("DATABASE_URL", "postgresql+asyncpg://fxlab:fxlab@localhost:5432/fxlab_test")
    env.setdefault("REDIS_URL", "redis://localhost:6379/1")
    env["APP_ENV"] = "development"

    api = Service("api", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"], cwd=".", env=env)
    worker = Service("worker", [sys.executable, "-m", "app.worker.main"], cwd=".", env=env)

    print("Starting API + worker...")
    api.start()
    worker.start()
    if not _wait_for(_health_ok, timeout=30):
        print("FATAL: API never became healthy — aborting")
        api.kill()
        worker.kill()
        return 1
    print("API + worker up.\n")

    try:
        scenario_redis_down()
        scenario_postgres_down()
        asyncio.run(_scenario_abnormal_tick_flood())
        scenario_rate_limit(api, env)
        scenario_worker_kill(worker)
        scenario_api_kill(api)
    finally:
        api.kill()
        worker.kill()

    print("\n=== Chaos test summary ===")
    failed = 0
    for scenario, verdict, note in RESULTS:
        print(f"{verdict:>22} | {scenario}")
        if verdict == "FAIL":
            failed += 1
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
