import json
from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings


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
    mock_persistence.get_system_state = AsyncMock(return_value="")
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", False):
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
    mock_persistence.get_system_state = AsyncMock(return_value="")
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", False):
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


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_allows_unmanaged_positions_when_ignore_flag_enabled(
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
                "currentPrice": 67000.0,
                "marketValue": 2010.0,
            }
        ]
    )
    mock_persistence.get_open_signals = AsyncMock(return_value=[])
    mock_persistence.set_system_state = AsyncMock()
    mock_persistence.get_system_state = AsyncMock(return_value="")
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", True), \
         patch.object(settings, "LIVE_CAPITAL_DANGER", False):
        should_continue = await monitor._fail_fast_on_broker_ledger_mismatch()

    assert should_continue is True
    # Must not pause the bot — ignore means continue scanning.
    paused_calls = [
        call
        for call in mock_persistence.set_system_state.await_args_list
        if call.args == ("operational_status", "PAUSED_REQUIRES_MANUAL_REVIEW")
    ]
    assert paused_calls == []

    mock_notify.send_message.assert_awaited_once()
    mock_dashboard.update.assert_awaited_once()
    assert mock_dashboard.update.await_args.args[0] == "UNMANAGED_POSITIONS_IGNORED"
    message = mock_dashboard.update.await_args.args[1]
    assert "RISK ALERT" in message
    assert "NOT auto-flattening overnight" in message
    assert "BTCUSD" in message
    assert "Broker/ledger reconciliation audit:" in message
    assert "suggested_action=IMPORT_OR_CLOSE_MANUALLY_NO_AUTO_FLATTEN" in message

    state_calls = [
        call
        for call in mock_persistence.set_system_state.await_args_list
        if call.args[0] == "unmanaged_broker_positions"
    ]
    assert len(state_calls) == 1
    payload = json.loads(state_calls[0].args[1])
    assert payload["ignored"] is True
    assert payload["auto_flatten"] is False
    assert payload["symbols"] == ["BTCUSD"]
    assert payload["count"] == 1


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_clears_unmanaged_state_when_broker_matches_ledger(
    mock_dashboard,
    mock_persistence,
    mock_notify,
    startup_monitor_factory,
):
    monitor = startup_monitor_factory()
    monitor.brokerage.get_portfolio = AsyncMock(
        return_value=[
            {
                "ticker": "ETH-USD",
                "quantity": 0.5,
                "quantityAvailableForTrading": 0.5,
            }
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

    with patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", True):
        should_continue = await monitor._fail_fast_on_broker_ledger_mismatch()

    assert should_continue is True
    mock_persistence.set_system_state.assert_awaited_once_with("unmanaged_broker_positions", "")
    mock_notify.send_message.assert_not_awaited()
    mock_dashboard.update.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_ignore_unmanaged_never_implies_auto_flatten(
    mock_dashboard,
    mock_persistence,
    mock_notify,
    startup_monitor_factory,
):
    """Regression: ignore flag must alert + continue, never liquidate foreign inventory."""
    monitor = startup_monitor_factory()
    monitor.brokerage.get_portfolio = AsyncMock(
        return_value=[{"ticker": "SOLUSD", "quantity": 2.0, "quantityAvailableForTrading": 2.0}]
    )
    monitor.brokerage.place_value_order = AsyncMock()
    monitor.brokerage.execute_order = AsyncMock()
    mock_persistence.get_open_signals = AsyncMock(return_value=[])
    mock_persistence.set_system_state = AsyncMock()
    mock_persistence.get_system_state = AsyncMock(return_value="")
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", True):
        should_continue = await monitor._fail_fast_on_broker_ledger_mismatch()

    assert should_continue is True
    # Mismatch ignore path is read-only — no broker flatten / close orders.
    monitor.brokerage.place_value_order.assert_not_awaited()
    monitor.brokerage.execute_order.assert_not_awaited()
    message = mock_notify.send_message.await_args.args[0]
    assert "NOT auto-flattening overnight" in message
    assert "suggested_action=IMPORT_OR_CLOSE_MANUALLY_NO_AUTO_FLATTEN" in message


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_skips_alert_for_operator_acknowledged_unmanaged(
    mock_dashboard,
    mock_persistence,
    mock_notify,
    startup_monitor_factory,
):
    monitor = startup_monitor_factory()
    monitor.brokerage.get_portfolio = AsyncMock(
        return_value=[{"ticker": "BTC-USD", "quantity": 0.1, "quantityAvailableForTrading": 0.1}]
    )
    mock_persistence.get_open_signals = AsyncMock(return_value=[])
    mock_persistence.set_system_state = AsyncMock()
    mock_persistence.get_system_state = AsyncMock(
        return_value=json.dumps(
            {"symbols": {"BTC-USD": {"note": "paper_ack", "provenance": "broker_foreign_holding"}}}
        )
    )
    mock_notify.send_message = AsyncMock()
    mock_dashboard.update = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", False):
        should_continue = await monitor._fail_fast_on_broker_ledger_mismatch()

    assert should_continue is True
    mock_notify.send_message.assert_not_awaited()
    mock_dashboard.update.assert_not_awaited()
    state_calls = [
        call
        for call in mock_persistence.set_system_state.await_args_list
        if call.args[0] == "unmanaged_broker_positions"
    ]
    assert state_calls
    payload = json.loads(state_calls[0].args[1])
    assert payload["acknowledged_only"] is True
    assert payload["symbols"] == ["BTC-USD"]
