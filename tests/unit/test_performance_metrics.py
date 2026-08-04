"""Unit tests for performance metrics honesty and PnL aggregation."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import numpy as np
import pytest

from src.services.dashboard_service import DashboardState
from src.services.performance_service import PerformanceService
from src.services.persistence_service import OrderStatus, PersistenceService


@pytest.mark.asyncio
async def test_empty_returns_do_not_fake_sharpe_one():
    """Empty ledger must not report a fabricated healthy Sharpe of 1.0."""
    ps = PerformanceService()
    with patch(
        "src.services.persistence_service.persistence_service.get_daily_returns",
        new=AsyncMock(return_value={}),
    ), patch.object(ps, "get_dynamic_risk_free_rate", new=AsyncMock(return_value=0.02)):
        metrics = await ps.get_portfolio_metrics()

    assert metrics["sharpe_ratio"] == 0.0
    assert metrics["max_drawdown"] == 0.0
    assert metrics["sample_days"] == 0
    assert metrics["metrics_ready"] is False
    assert metrics["sharpe_ratio"] != 1.0


@pytest.mark.asyncio
async def test_single_day_returns_not_ready():
    """One observation is insufficient for Sharpe; report 0.0 / not ready."""
    ps = PerformanceService()
    with patch(
        "src.services.persistence_service.persistence_service.get_daily_returns",
        new=AsyncMock(return_value={"2026-08-01": 10.0}),
    ), patch.object(ps, "get_dynamic_risk_free_rate", new=AsyncMock(return_value=0.02)):
        metrics = await ps.get_portfolio_metrics()

    assert metrics["sample_days"] == 1
    assert metrics["metrics_ready"] is False
    assert metrics["sharpe_ratio"] == 0.0


@pytest.mark.asyncio
async def test_nan_sharpe_does_not_fallback_to_one():
    """NaN from Sharpe math must not become a fake 1.0."""
    ps = PerformanceService()
    daily = {f"2026-04-{i:02d}": 1.0 for i in range(1, 11)}
    with patch(
        "src.services.persistence_service.persistence_service.get_daily_returns",
        new=AsyncMock(return_value=daily),
    ), patch.object(ps, "get_dynamic_risk_free_rate", new=AsyncMock(return_value=0.02)), patch.object(
        ps, "calculate_sharpe", return_value=float("nan")
    ):
        metrics = await ps.get_portfolio_metrics()

    assert metrics["metrics_ready"] is True
    assert metrics["sharpe_ratio"] == 0.0
    assert not np.isnan(metrics["sharpe_ratio"])


@pytest.mark.asyncio
async def test_get_daily_returns_dedupes_pair_legs():
    """Both legs carry the same signal-level pnl; aggregate once per signal/day."""
    signal_id = uuid.uuid4()
    closed = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    legs = [
        SimpleNamespace(
            id=uuid.uuid4(),
            signal_id=signal_id,
            status=OrderStatus.CLOSED,
            closed_at=closed,
            execution_timestamp=datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc),
            metadata_json={"pnl": 12.5},
            venue="ALPACA",
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            signal_id=signal_id,
            status=OrderStatus.CLOSED,
            closed_at=closed,
            execution_timestamp=datetime(2026, 8, 1, 14, 1, tzinfo=timezone.utc),
            metadata_json={"pnl": 12.5},
            venue="ALPACA",
        ),
    ]

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return legs

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, _stmt):
            return _Result()

    service = PersistenceService()
    with patch.object(service, "AsyncSessionLocal", lambda: _Session()):
        daily = await service.get_daily_returns()
        total = await service.get_total_pnl()

    assert daily == {"2026-08-03": 12.5}
    assert total == 12.5


@pytest.mark.asyncio
async def test_chart_win_loss_buckets_by_closed_at():
    """Win/loss series must attribute realized outcomes to close day, not open day."""
    service = PersistenceService()
    history = {
        "items": [
            {
                "signal_id": "a",
                "opened_at": "2026-08-01T10:00:00+00:00",
                "closed_at": "2026-08-03T15:00:00+00:00",
                "pnl": 5.0,
            },
            {
                "signal_id": "b",
                "opened_at": "2026-08-01T11:00:00+00:00",
                "closed_at": "2026-08-03T16:00:00+00:00",
                "pnl": -2.0,
            },
        ],
        "total": 2,
        "page": 1,
        "page_size": 500,
    }
    with patch.object(service, "get_daily_returns", new=AsyncMock(return_value={})), patch.object(
        service, "get_trade_history", new=AsyncMock(return_value=history)
    ) as mock_history:
        series = await service.get_chart_series("win_loss")

    mock_history.assert_awaited_once()
    assert mock_history.await_args.kwargs.get("status") == "CLOSED"
    assert series["points"] == [
        {"timestamp": "2026-08-03", "wins": 1.0, "losses": 1.0},
    ]


@pytest.mark.asyncio
async def test_dashboard_update_pnl_writes_total_revenue_not_daily():
    """Monitor lifetime PnL must not overwrite today's daily_profit card."""
    state = DashboardState()
    state.portfolio_metrics["daily_profit"] = 3.0
    state.portfolio_metrics["total_revenue"] = None

    await state.update("Monitoring", "Scanning...", pnl=100.0)

    assert state.portfolio_metrics["daily_profit"] == 3.0
    assert state.portfolio_metrics["total_revenue"] == 100.0


@pytest.mark.asyncio
async def test_risk_service_defaults_missing_sharpe_to_zero():
    """Missing sharpe must not default to a healthy 1.0."""
    from src.services.risk_service import risk_service

    with patch(
        "src.services.performance_service.performance_service.get_portfolio_metrics",
        new=AsyncMock(return_value={}),
    ), patch(
        "src.services.volatility_service.volatility_service.get_volatility_status",
        return_value="NORMAL",
    ), patch(
        "src.services.volatility_service.volatility_service.get_l2_entropy",
        return_value=0.5,
    ), patch(
        "src.services.telemetry_service.telemetry_service.broadcast",
        MagicMock(),
    ):
        params = await risk_service.get_execution_params("AAPL")

    # sharpe 0.0 < RISK_SHARPE_FLOOR => Kelly capped
    assert params["risk_multiplier"] <= 0.1
