from unittest.mock import AsyncMock, patch

import pytest

from src.services.persistence_service import OrderStatus, persistence_service


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _StartupRecoverySession:
    def __init__(self, statuses_to_count=None):
        self.statuses_to_count = set(statuses_to_count or {OrderStatus.CLOSE_FAILED})

    def begin(self):
        return _FakeTransaction()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        params = statement.compile().params
        unresolved_statuses = params.get("status_1", [])
        if isinstance(unresolved_statuses, (list, tuple, set)) and unresolved_statuses:
            return _ScalarResult(
                sum(1 for status in self.statuses_to_count if status in unresolved_statuses)
            )
        return _ScalarResult(0)


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_blocks_when_unresolved_execution_state_exists(
    mock_dashboard,
    mock_persistence,
    mock_notify,
    startup_monitor_factory,
):
    monitor = startup_monitor_factory()
    monitor._run_startup_auto_reconciliation = AsyncMock()
    mock_persistence.count_startup_reconciliation_rows = AsyncMock(return_value=2)
    mock_persistence.get_startup_reconciliation_rows = AsyncMock(
        return_value=[
            {
                "id": "ledger-1",
                "order_id": "ORPHAN_abc",
                "signal_id": "signal-1",
                "ticker": "BTC-USD",
                "side": "BUY",
                "quantity": 0.004198,
                "price": 79519.1171875,
                "status": "FAILED",
                "venue": "ALPACA",
                "execution_timestamp": "2026-05-04T14:41:42.942715+00:00",
            }
        ]
    )
    mock_persistence.set_system_state = AsyncMock()
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    should_continue = await monitor._fail_fast_on_unresolved_execution_state()

    assert should_continue is False
    monitor._run_startup_auto_reconciliation.assert_awaited_once()
    mock_persistence.count_startup_reconciliation_rows.assert_awaited_once()
    mock_persistence.set_system_state.assert_awaited_once_with(
        "operational_status",
        "PAUSED_REQUIRES_MANUAL_REVIEW",
    )
    mock_notify.send_message.assert_awaited_once()
    mock_dashboard.update.assert_awaited_once()
    assert mock_dashboard.update.await_args.args[0] == "PAUSED_REQUIRES_MANUAL_REVIEW"
    dashboard_msg = mock_dashboard.update.await_args.args[1]
    assert "2 ledger rows require manual reconciliation" in dashboard_msg
    assert "Unresolved rows:" in dashboard_msg
    assert "id=ledger-1" in dashboard_msg
    assert "order_id=ORPHAN_abc" in dashboard_msg
    assert "ticker=BTC-USD" in dashboard_msg
    assert "status=FAILED" in dashboard_msg


@pytest.mark.asyncio
async def test_startup_treats_close_failed_as_unresolved_execution_state(monkeypatch):
    fake_session = _StartupRecoverySession()
    monkeypatch.setattr(persistence_service, "AsyncSessionLocal", lambda: fake_session)

    unresolved_count = await persistence_service.mark_startup_unsafe_signals_needs_reconciliation()

    assert unresolved_count == 1


@pytest.mark.asyncio
async def test_startup_treats_failed_submitted_and_partial_states_as_unresolved(monkeypatch):
    unsafe_statuses = {
        OrderStatus.FAILED,
        OrderStatus.ORDER_SUBMITTED,
        OrderStatus.LEG_A_SUBMITTED,
        OrderStatus.LEG_B_SUBMITTED,
        OrderStatus.LEG_A_PARTIAL,
        OrderStatus.LEG_B_PARTIAL,
        OrderStatus.PARTIAL_EXPOSURE,
    }
    fake_session = _StartupRecoverySession(unsafe_statuses)
    monkeypatch.setattr(persistence_service, "AsyncSessionLocal", lambda: fake_session)

    unresolved_count = await persistence_service.mark_startup_unsafe_signals_needs_reconciliation()

    assert unresolved_count == len(unsafe_statuses)
