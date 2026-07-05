import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings


@pytest.mark.asyncio
@patch("src.monitor.data_service")
@patch("src.monitor.notification_service")
@patch("src.monitor.redis_service")
@patch("src.monitor.dashboard_service")
@patch("src.monitor.persistence_service")
async def test_startup_marks_no_scannable_pairs_after_health_checks(
    mock_persistence,
    mock_dashboard,
    mock_redis,
    mock_notify,
    mock_data,
    startup_monitor_factory,
    startup_health_check_connection,
):
    monitor = startup_monitor_factory()
    monitor.log_preflight = MagicMock()
    monitor.active_pairs = [{"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT"}]
    monitor.initialize_pairs = AsyncMock()
    monitor.is_market_open = MagicMock(return_value=False)
    monitor._fail_fast_on_unresolved_execution_state = AsyncMock(return_value=True)
    monitor._fail_fast_on_broker_ledger_mismatch = AsyncMock(return_value=True)
    monitor._get_sizing_base = AsyncMock()
    monitor.process_pair = AsyncMock()
    monitor._auto_scout_and_rotate_loop = MagicMock(return_value=None)

    mock_persistence.init_db = AsyncMock()
    mock_persistence.engine.connect.return_value = startup_health_check_connection()
    mock_persistence.engine.dispose = AsyncMock()
    mock_persistence.set_system_state = AsyncMock()
    mock_persistence.get_total_pnl = AsyncMock(return_value=0.0)
    mock_persistence.get_open_signals = AsyncMock(return_value=[])
    mock_dashboard.attach_monitor = MagicMock()
    mock_dashboard.start = AsyncMock()
    mock_dashboard.server = None
    mock_dashboard.dashboard_state.desired_bot_state = "RUNNING"
    no_scannable_seen = asyncio.Event()

    async def capture_dashboard_update(stage, *args, **kwargs):
        if stage == "NO_SCANNABLE_PAIRS":
            no_scannable_seen.set()

    mock_dashboard.update = AsyncMock(side_effect=capture_dashboard_update)
    mock_dashboard.update_metrics = AsyncMock()
    mock_notify.start_listening = AsyncMock()
    mock_notify.send_message = AsyncMock()
    mock_redis.client.ping = AsyncMock()
    mock_redis.client.aclose = AsyncMock()
    mock_data.get_latest_price_async = AsyncMock()

    with patch.object(settings, "PAPER_TRADING", True), patch(
        "src.monitor.background_task_watchdog.create_task"
    ), patch(
        "src.services.performance_service.performance_service.get_portfolio_metrics",
        AsyncMock(return_value={}),
    ):
        task = asyncio.create_task(monitor.run())
        await asyncio.wait_for(no_scannable_seen.wait(), timeout=3)
        task.cancel()
        await task

    mock_dashboard.update.assert_any_await(
        "NO_SCANNABLE_PAIRS",
        "No active pairs are currently scannable (1 loaded). Waiting for an eligible market/session.",
    )
    mock_data.get_latest_price_async.assert_not_awaited()
    monitor._get_sizing_base.assert_not_awaited()
    monitor.process_pair.assert_not_awaited()
