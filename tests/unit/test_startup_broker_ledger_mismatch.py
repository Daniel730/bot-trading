from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings
from src.monitor import ArbitrageMonitor


def _make_startup_monitor(mode: str = "live") -> ArbitrageMonitor:
    return ArbitrageMonitor(mode=mode)


@pytest.fixture
def startup_monitor_factory(fake_broker):
    with patch("src.monitor.BrokerageService", return_value=fake_broker):
        yield _make_startup_monitor


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_blocks_when_broker_has_unmanaged_position(
    mock_dashboard,
    mock_persistence,
    mock_notify,
    startup_monitor_factory,
):
    monitor = startup_monitor_factory()
    monitor.brokerage.get_portfolio = AsyncMock(
        return_value=[
            {
                "ticker": "BTCUSD",
                "quantity": 0.03,
                "quantityAvailableForTrading": 0.03,
            }
        ]
    )
    mock_persistence.get_open_signals = AsyncMock(return_value=[])
    mock_persistence.set_system_state = AsyncMock()
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", False):
        should_continue = await monitor._fail_fast_on_broker_ledger_mismatch()

    assert should_continue is False
    mock_persistence.set_system_state.assert_awaited_once_with(
        "operational_status",
        "PAUSED_REQUIRES_MANUAL_REVIEW",
    )
    mock_notify.send_message.assert_awaited_once()
    mock_dashboard.update.assert_awaited_once()
    assert "broker/ledger mismatch" in mock_dashboard.update.await_args.args[1]
    assert "BTCUSD" in mock_dashboard.update.await_args.args[1]


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_broker_ledger_mismatch_reports_read_only_reconciliation_audit(
    mock_dashboard,
    mock_persistence,
    mock_notify,
    startup_monitor_factory,
):
    monitor = startup_monitor_factory()
    monitor.brokerage.get_portfolio = AsyncMock(
        return_value=[
            {
                "ticker": "BTCUSD",
                "quantity": 0.03,
                "quantityAvailableForTrading": 0.02,
                "currentPrice": 67000.0,
                "marketValue": 2010.0,
            },
            {
                "ticker": "ETH-USD",
                "quantity": 0.5,
                "quantityAvailableForTrading": 0.5,
                "currentPrice": 3500.0,
                "marketValue": 1750.0,
            },
        ]
    )
    mock_persistence.get_open_signals = AsyncMock(
        return_value=[
            {
                "signal_id": "managed-eth-signal",
                "legs": [{"ticker": "ETH-USD", "side": "BUY", "quantity": 0.5}],
            }
        ]
    )
    mock_persistence.set_system_state = AsyncMock()
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", False):
        should_continue = await monitor._fail_fast_on_broker_ledger_mismatch()

    assert should_continue is False
    message = mock_dashboard.update.await_args.args[1]
    assert "Broker/ledger reconciliation audit:" in message
    assert (
        "broker_symbol=BTCUSD canonical_symbol=BTCUSD quantity=0.03 "
        "available_quantity=0.02 current_price=67000.0 market_value=2010.0 "
        "ledger_match=no signal_ids=none suggested_action=IMPORT_OR_CLOSE_MANUALLY_BEFORE_RESTART"
    ) in message
    assert (
        "broker_symbol=ETH-USD canonical_symbol=ETHUSD quantity=0.5 "
        "available_quantity=0.5 current_price=3500.0 market_value=1750.0 "
        "ledger_match=yes signal_ids=managed-eth-signal suggested_action=VERIFY_LEDGER_MATCH"
    ) in message
