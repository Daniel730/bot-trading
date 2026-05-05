import pytest
from fastapi import HTTPException

from src.services.dashboard_service import DashboardSessionManager, verify_token


def test_signed_dashboard_session_survives_manager_recreation():
    first_manager = DashboardSessionManager(ttl_seconds=60)
    created = first_manager.create(actor="dashboard")

    fresh_manager = DashboardSessionManager(ttl_seconds=60)
    verified = fresh_manager.verify(created["session_token"])

    assert verified["actor"] == "dashboard"
    assert verified["expires_at"].isoformat() <= created["expires_at"]


def test_dashboard_session_allows_requests_without_resending_static_token():
    manager = DashboardSessionManager(ttl_seconds=60)
    created = manager.create(actor="dashboard")

    assert verify_token(token=None, session=created["session_token"]) == created["session_token"]


def test_dashboard_session_rejects_tampering():
    manager = DashboardSessionManager(ttl_seconds=60)
    created = manager.create(actor="dashboard")
    version, payload, signature = created["session_token"].split(".", 2)
    tampered_payload = f"{'A' if payload[0] != 'A' else 'B'}{payload[1:]}"
    tampered = f"{version}.{tampered_payload}.{signature}"

    with pytest.raises(HTTPException) as exc:
        manager.verify(tampered)

    assert exc.value.status_code == 401


def test_dashboard_session_revoke_blocks_signed_token():
    manager = DashboardSessionManager(ttl_seconds=60)
    created = manager.create(actor="dashboard")

    manager.revoke(created["session_token"])

    with pytest.raises(HTTPException) as exc:
        manager.verify(created["session_token"])

    assert exc.value.status_code == 401


def test_dashboard_session_expires():
    manager = DashboardSessionManager(ttl_seconds=-1)
    created = manager.create(actor="dashboard")

    with pytest.raises(HTTPException) as exc:
        manager.verify(created["session_token"])

    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_dashboard_login_fails_closed_without_notification_channel():
    from unittest.mock import patch
    from src.services.dashboard_service import DashboardLoginRequest, _login

    class DummyRequest:
        headers = {}
        client = None

    payload = DashboardLoginRequest(actor="dashboard", security_token="test-token")

    with patch("src.services.dashboard_service.verify_security_token", return_value=None), \
         patch("src.services.dashboard_service.login_challenge_manager.create", side_effect=HTTPException(status_code=503, detail="approval unavailable")), \
         patch("src.services.dashboard_service.dashboard_service.totp.public_status", return_value={"enabled": False}):
        with pytest.raises(HTTPException) as exc:
            await _login(payload, DummyRequest())

    assert exc.value.status_code == 503
