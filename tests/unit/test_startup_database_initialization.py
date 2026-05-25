from unittest.mock import AsyncMock, MagicMock, patch

import pytest

@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
async def test_startup_handles_database_initialization_failure(
    mock_persistence, mock_notify, startup_monitor_factory
):
    monitor = startup_monitor_factory()
    monitor.log_preflight = MagicMock()
    monitor.initialize_pairs = AsyncMock()
    mock_persistence.init_db = AsyncMock(side_effect=RuntimeError("db offline"))
    mock_notify.send_message = AsyncMock()

    await monitor.run()

    mock_persistence.init_db.assert_awaited_once()
    mock_notify.send_message.assert_awaited_once()
    assert "Database initialization failed" in mock_notify.send_message.await_args.args[0]
    monitor.initialize_pairs.assert_not_awaited()
