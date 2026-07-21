"""Post-deployment smoke test (docs/22_PRODUCTION_CHECKLIST.md "Smoke Test").

Exercises a REAL deployed Staging (or Production) environment end-to-end
exactly the way a browser would: log in through the frontend's BFF, use the
resulting session cookie to call REST through the same proxy the browser
uses, mint a WebSocket ticket the same way the browser does, and open a
real WebSocket to confirm live ticks actually arrive. This is deliberately
NOT a unit/integration test against local code — it only exists to answer
"is the thing that's actually deployed right now working," which nothing
else in this repo's test suite can answer (docs/13_TEST_STRATEGY.md).

Usage:
    STAGING_BASE_URL=https://fxlab-staging.vercel.app \\
    STAGING_WS_URL=wss://fxlab-staging-api.up.railway.app \\
    STAGING_LOGIN_TOKEN=<the APP_API_TOKEN / login password> \\
    python3 backend/scripts/deploy_smoke_test.py

STAGING_BASE_URL is the FRONTEND origin (login and all REST calls go
through its BFF routes, matching what a browser does — never call the
backend directly here, that would not be testing the BFF proxy itself).
STAGING_WS_URL is the BACKEND's public origin (the browser connects its
WebSocket there directly, unproxied — see docs/11_SECURITY.md "BFF
migration"). STAGING_ORIGIN optionally overrides the Origin header sent on
the WebSocket handshake; defaults to STAGING_BASE_URL.

Never point this at Production with a throwaway/test instrument list
assumption — it only reads existing data (instruments, candles, replay,
paper account) and creates one disposable replay session; it places no
paper or live orders and never touches the Kill Switch or risk settings.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field

import httpx
import websockets


@dataclass
class Results:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))

    @property
    def all_ok(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


async def run(base_url: str, ws_base_url: str, login_token: str, origin: str) -> Results:
    results = Results()

    async with httpx.AsyncClient(base_url=base_url, timeout=15.0, follow_redirects=False) as client:
        # 1. Login
        try:
            resp = await client.post("/api/session-login", json={"token": login_token})
            results.record("login", resp.status_code == 200, f"status={resp.status_code}")
        except httpx.HTTPError as exc:
            results.record("login", False, str(exc))
            return results  # nothing downstream can work without a session

        if resp.status_code != 200:
            return results

        # 2. Markets (instruments)
        symbol = None
        try:
            resp = await client.get("/api/backend/instruments")
            ok = resp.status_code == 200
            instruments = resp.json() if ok else []
            if ok and instruments:
                symbol = instruments[0]["symbol"]
            results.record(
                "markets (GET /instruments)", ok and bool(instruments),
                f"status={resp.status_code} count={len(instruments) if ok else 'n/a'}",
            )
        except httpx.HTTPError as exc:
            results.record("markets (GET /instruments)", False, str(exc))

        # 3. Chart data
        if symbol:
            try:
                resp = await client.get(f"/api/backend/instruments/{symbol}/candles", params={"granularity": "H1", "count": 10})
                results.record("chart data (GET .../candles)", resp.status_code == 200, f"status={resp.status_code}")
            except httpx.HTTPError as exc:
                results.record("chart data (GET .../candles)", False, str(exc))
        else:
            results.record("chart data (GET .../candles)", False, "skipped — no instrument from previous check")

        # 4. System status
        try:
            resp = await client.get("/api/backend/system/status")
            results.record("system status", resp.status_code == 200, f"status={resp.status_code}")
        except httpx.HTTPError as exc:
            results.record("system status", False, str(exc))

        # 5. Paper trading account
        try:
            resp = await client.get("/api/backend/paper/account")
            results.record("paper trading account", resp.status_code == 200, f"status={resp.status_code}")
        except httpx.HTTPError as exc:
            results.record("paper trading account", False, str(exc))

        # 6. Replay session (create + one step)
        if symbol:
            try:
                resp = await client.post(
                    "/api/backend/replay/sessions",
                    json={"instrument": symbol, "granularity": "M15", "candle_count": 100},
                )
                ok = resp.status_code == 200
                session_id = resp.json().get("id") if ok else None
                results.record("replay session create", ok, f"status={resp.status_code}")
                if ok and session_id:
                    step_resp = await client.post(f"/api/backend/replay/sessions/{session_id}/step")
                    results.record("replay session step", step_resp.status_code == 200, f"status={step_resp.status_code}")
            except httpx.HTTPError as exc:
                results.record("replay session create", False, str(exc))
        else:
            results.record("replay session create", False, "skipped — no instrument from previous check")

        # 7. WS ticket mint
        ticket = None
        try:
            resp = await client.post("/api/ws-ticket")
            ok = resp.status_code == 200
            ticket = resp.json().get("ticket") if ok else None
            results.record("ws ticket mint", ok and bool(ticket), f"status={resp.status_code}")
        except httpx.HTTPError as exc:
            results.record("ws ticket mint", False, str(exc))

    # 8. WebSocket — real connection, wait for at least one tick frame
    if symbol and ticket:
        # Note: WS routes are mounted WITHOUT the /api/v1 prefix REST routes use
        # (app/main.py — app.include_router(ws_prices.router) has no prefix arg),
        # matching docs/05_API_DESIGN.md's "WS /ws/prices" (no /api/v1).
        ws_url = f"{ws_base_url}/ws/prices?instruments={symbol}&ticket={ticket}"
        try:
            async with websockets.connect(ws_url, origin=origin, open_timeout=10) as ws:
                message = await asyncio.wait_for(ws.recv(), timeout=15)
                payload = json.loads(message)
                results.record(
                    "websocket live tick",
                    isinstance(payload, dict) and "type" in payload,
                    f"first frame type={payload.get('type') if isinstance(payload, dict) else 'unparseable'}",
                )
        except Exception as exc:  # noqa: BLE001 — smoke test, report every failure mode uniformly
            results.record("websocket live tick", False, str(exc))
    else:
        results.record("websocket live tick", False, "skipped — no instrument or ticket from previous checks")

    return results


def main() -> int:
    base_url = os.environ.get("STAGING_BASE_URL")
    ws_base_url = os.environ.get("STAGING_WS_URL")
    login_token = os.environ.get("STAGING_LOGIN_TOKEN")
    origin = os.environ.get("STAGING_ORIGIN", base_url)

    missing = [name for name, value in [("STAGING_BASE_URL", base_url), ("STAGING_WS_URL", ws_base_url), ("STAGING_LOGIN_TOKEN", login_token)] if not value]
    if missing:
        print(f"Missing required env var(s): {', '.join(missing)}", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2

    results = asyncio.run(run(base_url, ws_base_url, login_token, origin))

    print()
    passed = sum(1 for _, ok, _ in results.checks if ok)
    print(f"{passed}/{len(results.checks)} checks passed")
    return 0 if results.all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
