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
