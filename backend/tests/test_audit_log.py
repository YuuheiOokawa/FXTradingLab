"""Audit log (docs/15_PRODUCTION_READINESS_REVIEW.md "Audit Log") — separate
from SystemEvent (free-form operational logging): a reliable who/when/what/
before/after trail for the specific named sensitive actions."""
import httpx
import pytest
from sqlalchemy import select

from app.brokers.mock import MockAdapter
from app.db.models.journal import AuditLog
from app.main import app
from app.services.audit import write_audit_log
from app.services.order_orchestrator import OrderOrchestrator


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_write_audit_log_rejects_an_unknown_action(db_session):
    with pytest.raises(ValueError):
        await write_audit_log(db_session, "not_a_real_action")


async def test_activating_kill_switch_writes_an_audit_entry(db_session):
    orchestrator = OrderOrchestrator(MockAdapter())
    await orchestrator.activate_kill_switch(db_session, flatten_positions=False)

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "kill_switch_on"))
    entry = result.scalar_one()
    assert entry.before == {"kill_switch_active": False}
    assert entry.after == {"kill_switch_active": True}


async def test_deactivating_kill_switch_writes_an_audit_entry_and_a_system_event(db_session):
    """Regression test for a real bug found while adding this: the previous
    code committed BEFORE adding the SystemEvent row, so it was silently
    never persisted (get_db()'s session context doesn't auto-commit on
    close). Both the audit entry AND the system event must actually land."""
    from app.db.models.journal import SystemEvent

    orchestrator = OrderOrchestrator(MockAdapter())
    await orchestrator.activate_kill_switch(db_session, flatten_positions=False)
    await orchestrator.deactivate_kill_switch(db_session)

    audit_result = await db_session.execute(select(AuditLog).where(AuditLog.action == "kill_switch_off"))
    assert audit_result.scalar_one() is not None

    event_result = await db_session.execute(
        select(SystemEvent).where(SystemEvent.category == "kill_switch", SystemEvent.message == "Kill switch deactivated")
    )
    assert event_result.scalar_one_or_none() is not None


async def test_risk_setting_change_writes_a_before_after_audit_entry(client):
    resp = await client.put("/api/v1/settings/risk", json={"max_risk_per_trade_pct": 2.5})
    assert resp.status_code == 200

    resp2 = await client.get("/api/v1/audit-log?limit=10")
    entries = resp2.json()
    change_entries = [e for e in entries if e["action"] == "risk_setting_change"]
    assert change_entries
    latest = change_entries[0]
    assert latest["after"]["max_risk_per_trade_pct"] == 2.5


async def test_enabling_live_trading_admin_setting_gets_its_own_audit_action(client):
    resp = await client.put("/api/v1/settings/risk", json={"live_trading_admin_enabled": True})
    assert resp.status_code == 200

    resp2 = await client.get("/api/v1/audit-log?limit=10")
    entries = resp2.json()
    assert any(e["action"] == "live_trading_admin_enable" for e in entries)

    # Cleanup: disable again so this test doesn't leave LIVE trading's admin
    # gate armed for any test that runs after it.
    resp3 = await client.put("/api/v1/settings/risk", json={"live_trading_admin_enabled": False})
    assert resp3.status_code == 200
    resp4 = await client.get("/api/v1/audit-log?limit=10")
    assert any(e["action"] == "live_trading_admin_disable" for e in resp4.json())


async def test_session_event_endpoint_records_login_and_logout(client):
    resp1 = await client.post("/api/v1/system/session-event", json={"action": "login"})
    assert resp1.status_code == 200
    resp2 = await client.post("/api/v1/system/session-event", json={"action": "logout"})
    assert resp2.status_code == 200

    resp3 = await client.get("/api/v1/audit-log?limit=10")
    actions = [e["action"] for e in resp3.json()]
    assert "login" in actions
    assert "logout" in actions


async def test_session_event_rejects_an_unsupported_action(client):
    resp = await client.post("/api/v1/system/session-event", json={"action": "delete_everything"})
    assert resp.status_code == 422
