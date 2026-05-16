import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from src.services.dashboard_service import app, dashboard_state, dashboard_service
from src.config import settings

@pytest.fixture
def client(monkeypatch):
    from src.services.notification_service import notification_service

    async def send_dashboard_login_approval(challenge_id, summary):
        return True

    async def send_message(message):
        await dashboard_state.add_message("BOT", message)

    monkeypatch.setattr(
        notification_service,
        "send_dashboard_login_approval",
        send_dashboard_login_approval,
    )
    monkeypatch.setattr(notification_service, "send_message", send_message)
    with TestClient(app) as test_client:
        yield test_client


def dashboard_auth_query(client):
    token = settings.DASHBOARD_TOKEN or "arbi-elite-2026"
    response = client.post(
        "/api/auth/login",
        json={"security_token": token, "actor": "test"},
    )
    assert response.status_code == 200
    payload = response.json()
    if "session_token" not in payload:
        assert payload["status"] == "pending"
        challenge_id = payload["challenge_id"]
        from src.services.notification_service import notification_service

        future = notification_service.pending_approvals[challenge_id]
        future.get_loop().call_soon_threadsafe(future.set_result, True)
        response = client.post(
            "/api/auth/login/complete",
            json={"challenge_id": challenge_id},
        )
        assert response.status_code == 200
        payload = response.json()
    return f"token={token}&session={payload['session_token']}"


@pytest.mark.asyncio
async def test_terminal_command_integration(client):
    """Verify end-to-end command flow from API to Terminal State."""
    auth_query = dashboard_auth_query(client)
    
    # Clear messages
    async with dashboard_state._lock:
        dashboard_state.terminal_messages = []
    
    # 1. Send /status command via API
    response = client.post(
        f"/api/terminal/command?{auth_query}",
        json={"command": "/status"}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # 2. Check if USER message was added
    # We need to wait a bit as it's async, but TestClient is synchronous...
    # However, the endpoint awaits handle_dashboard_command which awaits add_message.
    
    assert len(dashboard_state.terminal_messages) >= 2 # USER command + BOT response
    
    user_msg = next(m for m in dashboard_state.terminal_messages if m["type"] == "USER")
    bot_msg = next(m for m in dashboard_state.terminal_messages if m["type"] == "BOT")
    
    assert user_msg["text"] == "/status"
    assert "Current Status" in bot_msg["text"]

@pytest.mark.asyncio
async def test_terminal_approval_integration(client):
    """Verify approval command flow."""
    auth_query = dashboard_auth_query(client)
    from src.services.notification_service import notification_service
    
    # 1. Mock a pending approval
    cid = "test-cid"
    future = asyncio.get_event_loop().create_future()
    notification_service.pending_approvals[cid] = future
    
    # 2. Send /approve command
    response = client.post(
        f"/api/terminal/command?{auth_query}",
        json={"command": f"/approve {cid}"}
    )
    
    assert response.status_code == 200
    assert future.done()
    assert await future == True
    
    # 3. Check message mirroring
    assert any(m["type"] == "BOT" and "Approval received" in m["text"] for m in dashboard_state.terminal_messages)

@pytest.mark.asyncio
async def test_audit_logging(client):
    """Verify that commands are logged to the database (Principle III)."""
    auth_query = dashboard_auth_query(client)
    
    with patch('src.services.notification_service.settings.PAPER_TRADING', True), \
         patch(
             'src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors',
             new=AsyncMock(side_effect=AssertionError("paper-mode audit test must not query Postgres")),
         ) as mock_shadow_portfolio:
        # Send a command
        response = client.post(
            f"/api/terminal/command?{auth_query}",
            json={"command": "/exposure"}
        )
        assert response.status_code == 200
        mock_shadow_portfolio.assert_not_awaited()
    
    # Check SQLite logs — query specifically for the /exposure command log entry
    with dashboard_service.persistence._get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM logs WHERE source = 'DASHBOARD_TERMINAL' AND message LIKE '%/exposure%' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert "/exposure" in row["message"]
