import pytest
import asyncio
import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from src.monitor import ArbitrageMonitor
from src.config import settings


class _HealthCheckConnection:
    def __init__(self, error=None):
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_startup_monitor(mode: str = "live") -> ArbitrageMonitor:
    return ArbitrageMonitor(mode=mode)


@pytest.fixture
def startup_monitor_factory(fake_broker):
    with patch("src.monitor.BrokerageService", return_value=fake_broker):
        yield _make_startup_monitor


def test_startup_guards_construct_monitor_through_isolated_factory():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    violations = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

        def visit_Call(self, node):
            if getattr(node.func, "id", None) == "ArbitrageMonitor":
                current = self.stack[-1] if self.stack else None
                if current != "_make_startup_monitor":
                    violations.append(node.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)

    assert violations == []


@pytest.mark.asyncio
async def test_alpaca_paper_broker_startup_skips_live_entropy_baselines(monkeypatch, startup_monitor_factory):
    pairs = [{"ticker_a": "BTC-USD", "ticker_b": "ETH-USD"}]
    monitor = startup_monitor_factory()
    monitor.verify_entropy_baselines = AsyncMock(
        side_effect=AssertionError("Alpaca paper broker mode must not require live entropy baselines")
    )

    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setattr("src.monitor.persistence_service.get_active_trading_pairs", AsyncMock(return_value=pairs))
    monkeypatch.setattr("src.monitor.build_candidate_pairs", MagicMock(return_value=pairs))
    monkeypatch.setattr("src.monitor.filter_pair_universe", AsyncMock(return_value=(pairs, [])))
    monkeypatch.setattr("src.monitor.dashboard_service.update", AsyncMock())
    monkeypatch.setattr("src.monitor.data_service.get_historical_data_async", AsyncMock(return_value=None))

    await monitor.initialize_pairs()

    monitor.verify_entropy_baselines.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_refusal_missing_baselines(startup_monitor_factory):
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

                monitor = startup_monitor_factory()

                # Should raise SystemExit
                with pytest.raises(SystemExit) as excinfo:
                    await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])

                assert "CRITICAL: Missing L2 Entropy Baselines" in str(excinfo.value)
@pytest.mark.asyncio
async def test_startup_success_with_baselines(startup_monitor_factory):
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
            
            monitor = startup_monitor_factory()
            # Should not raise exception
            await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])

@pytest.mark.asyncio
@patch("src.monitor.notification_service")
@patch("src.monitor.persistence_service")
async def test_startup_handles_database_initialization_failure(mock_persistence, mock_notify, startup_monitor_factory):
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
    startup_monitor_factory,
):
    monitor = startup_monitor_factory()
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
    startup_monitor_factory,
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
