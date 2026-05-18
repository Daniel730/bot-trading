import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.monitor import ArbitrageMonitor
from src.config import settings
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


class _HealthCheckConnection:
    def __init__(self, error=None):
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

@pytest.mark.asyncio
async def test_startup_refusal_missing_baselines():
    """
    T006: Verify that ArbitrageMonitor refuses to boot if LIVE_CAPITAL_DANGER is True
    and Redis baselines are missing.
    """
    # Force LIVE_CAPITAL_DANGER = True
    with patch.object(settings, 'LIVE_CAPITAL_DANGER', True):
        # Mock Redis to return None (missing baseline)
        mock_redis = MagicMock()
        
        async def mock_get(key):
            return None
            
        mock_redis.get = mock_get
        
        with patch('src.monitor.redis_service') as mock_redis_service:
            mock_redis_service.client = mock_redis

            with patch('src.monitor.notification_service') as mock_notify:
                async def mock_send_message(msg): pass
                mock_notify.send_message = mock_send_message

                monitor = ArbitrageMonitor()

                # Should raise SystemExit
                with pytest.raises(SystemExit) as excinfo:
                    await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])

                assert "CRITICAL: Missing L2 Entropy Baselines" in str(excinfo.value)
@pytest.mark.asyncio
async def test_startup_success_with_baselines():
    """
    T006: Verify that ArbitrageMonitor proceeds if baselines exist.
    """
    with patch.object(settings, 'LIVE_CAPITAL_DANGER', True):
        # Mock Redis to return valid data
        mock_redis = MagicMock()
        
        async def mock_get(key):
            return "valid_baseline_data"
            
        mock_redis.get = mock_get
        
        with patch('src.monitor.redis_service') as mock_redis_service:
            mock_redis_service.client = mock_redis
            
            monitor = ArbitrageMonitor()
            # Should not raise exception
            await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])

@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
async def test_startup_handles_database_initialization_failure(mock_persistence, mock_notify):
    monitor = ArbitrageMonitor()
    monitor.log_preflight = MagicMock()
    monitor.initialize_pairs = AsyncMock()
    mock_persistence.init_db = AsyncMock(side_effect=RuntimeError("db offline"))
    mock_notify.send_message = AsyncMock()

    await monitor.run()

    mock_persistence.init_db.assert_awaited_once()
    mock_notify.send_message.assert_awaited_once()
    assert "Database initialization failed" in mock_notify.send_message.await_args.args[0]
    monitor.initialize_pairs.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failing_check", "expected_message"),
    [
        ("postgres", "PostgreSQL connection failed"),
        ("redis", "Redis connection failed"),
        ("alpaca", "Alpaca API connection failed"),
    ],
)
@patch("src.monitor.notification_service")
@patch("src.monitor.redis_service")
@patch("src.monitor.dashboard_service")
@patch("src.monitor.persistence_service")
async def test_startup_health_check_failures_use_existing_notification_api(
    mock_persistence,
    mock_dashboard,
    mock_redis,
    mock_notify,
    failing_check,
    expected_message,
):
    monitor = ArbitrageMonitor()
    monitor.log_preflight = MagicMock()
    monitor.active_pairs = [{"ticker_a": "KO", "ticker_b": "PEP"}]
    monitor.initialize_pairs = AsyncMock()
    monitor.brokerage.get_portfolio = AsyncMock(return_value=[])
    mock_persistence.init_db = AsyncMock()
    mock_persistence.engine.connect.return_value = _HealthCheckConnection()
    mock_dashboard.attach_monitor = MagicMock()
    mock_dashboard.start = AsyncMock()
    mock_notify.start_listening = AsyncMock()
    mock_notify.send_message = AsyncMock()
    mock_redis.client.ping = AsyncMock()

    if failing_check == "postgres":
        mock_persistence.engine.connect.return_value = _HealthCheckConnection(RuntimeError("pg offline"))
    elif failing_check == "redis":
        mock_redis.client.ping.side_effect = RuntimeError("redis offline")
    else:
        monitor.brokerage.get_portfolio.side_effect = RuntimeError("alpaca offline")

    with patch.object(settings, "PAPER_TRADING", failing_check != "alpaca"), patch("src.monitor.asyncio.sleep", AsyncMock()):
        await monitor.run()

    mock_notify.send_message.assert_awaited()
    assert expected_message in mock_notify.send_message.await_args_list[-1].args[0]


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
):
    monitor = ArbitrageMonitor()
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
    mock_persistence.engine.connect.return_value = _HealthCheckConnection()
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


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_blocks_when_unresolved_execution_state_exists(mock_dashboard, mock_persistence, mock_notify):
    monitor = ArbitrageMonitor()
    mock_persistence.mark_startup_unsafe_signals_needs_reconciliation = AsyncMock(return_value=2)
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
    mock_persistence.mark_startup_unsafe_signals_needs_reconciliation.assert_awaited_once()
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


@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
@patch("src.monitor.dashboard_service")
async def test_startup_blocks_when_broker_has_unmanaged_position(mock_dashboard, mock_persistence, mock_notify):
    monitor = ArbitrageMonitor()
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
