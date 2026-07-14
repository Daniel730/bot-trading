import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.services.dashboard_service import app, dashboard_state
from src.config import settings


@pytest.fixture
def client(monkeypatch):
    from src.services.notification_service import notification_service

    async def send_dashboard_login_approval(challenge_id, summary):
        return True

    async def send_message(message):
        await dashboard_state.add_message("BOT", message)

    monkeypatch.setattr(notification_service, "send_dashboard_login_approval", send_dashboard_login_approval)
    monkeypatch.setattr(notification_service, "send_message", send_message)
    with TestClient(app) as test_client:
        yield test_client


def _auth(client) -> str:
    token = settings.DASHBOARD_TOKEN or "arbi-elite-2026"
    resp = client.post("/api/auth/login", json={"security_token": token, "actor": "test"})
    assert resp.status_code == 200
    payload = resp.json()
    if "session_token" not in payload:
        from src.services.notification_service import notification_service

        challenge_id = payload["challenge_id"]
        future = notification_service.pending_approvals[challenge_id]
        future.get_loop().call_soon_threadsafe(future.set_result, True)
        payload = client.post("/api/auth/login/complete", json={"challenge_id": challenge_id}).json()
    return f"token={token}&session={payload['session_token']}"


def test_broker_positions_enriches_and_sorts(client):
    query = _auth(client)
    fake = [
        {"ticker": "ETH-USD", "quantity": 1.0, "averagePrice": 1000.0, "currentPrice": 900.0, "marketValue": 900.0},
        {"ticker": "BTC-USD", "quantity": 2.0, "averagePrice": 100.0, "currentPrice": 110.0, "marketValue": 220.0},
    ]
    with patch("src.services.dashboard_service.brokerage_service.get_positions", new_callable=AsyncMock, return_value=fake):
        resp = client.get(f"/api/broker/positions?{query}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == settings.BROKERAGE_PROVIDER
    assert body["total_market_value"] == pytest.approx(1120.0)
    # Sorted by market value desc -> ETH (900) first.
    assert [p["ticker"] for p in body["positions"]] == ["ETH-USD", "BTC-USD"]
    btc = next(p for p in body["positions"] if p["ticker"] == "BTC-USD")
    assert btc["unrealized_pl"] == pytest.approx(20.0)       # (110-100)*2
    assert btc["unrealized_pl_pct"] == pytest.approx(0.1)     # 20 / (100*2)
    eth = next(p for p in body["positions"] if p["ticker"] == "ETH-USD")
    assert eth["unrealized_pl"] == pytest.approx(-100.0)


def test_broker_positions_reports_error_gracefully(client):
    query = _auth(client)
    with patch("src.services.dashboard_service.brokerage_service.get_positions", new_callable=AsyncMock, side_effect=RuntimeError("broker down")):
        resp = client.get(f"/api/broker/positions?{query}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["positions"] == []
    assert "broker down" in body.get("error", "")


def test_broker_positions_requires_auth(client):
    resp = client.get("/api/broker/positions")
    assert resp.status_code == 401
