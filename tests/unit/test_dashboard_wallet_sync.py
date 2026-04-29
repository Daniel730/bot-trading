from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.config import settings
from src.services.dashboard_service import (
    T212WalletSyncRequest,
    dashboard_service,
    dashboard_state,
)


@pytest.fixture
def wallet_sync_context(monkeypatch):
    original_monitor = dashboard_state.monitor
    original_key = settings.T212_API_KEY
    original_alt_key = settings.TRADING_212_API_KEY
    original_budget = settings.T212_BUDGET_USD

    settings.T212_API_KEY = "test-key"
    settings.TRADING_212_API_KEY = ""
    settings.T212_BUDGET_USD = 0.0
    dashboard_state.monitor = SimpleNamespace(
        active_pairs=[
            {"ticker_a": "AAPL", "ticker_b": "MSFT", "is_cointegrated": True},
            {"ticker_a": "KO", "ticker_b": "PEP", "is_cointegrated": False},
            {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "is_cointegrated": True},
            {"ticker_a": "GOOG", "ticker_b": "GOOGL", "is_cointegrated": True},
        ]
    )

    import src.services.dashboard_service as dashboard_module

    monkeypatch.setattr(dashboard_module.brokerage_service, "get_venue", lambda ticker: "T212")
    monkeypatch.setattr(dashboard_module.brokerage_service, "get_account_cash", lambda: 100.0)
    monkeypatch.setattr(dashboard_module.brokerage_service, "get_pending_orders_value", AsyncMock(return_value=0.0))
    monkeypatch.setattr(dashboard_module.brokerage_service, "get_positions", lambda: [])
    monkeypatch.setattr(dashboard_module.brokerage_service, "get_pending_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(dashboard_module.brokerage_service, "place_value_order", AsyncMock(return_value={"order_id": "ok"}))
    monkeypatch.setattr(dashboard_state, "add_message", AsyncMock())

    yield dashboard_module.brokerage_service

    dashboard_state.monitor = original_monitor
    settings.T212_API_KEY = original_key
    settings.TRADING_212_API_KEY = original_alt_key
    settings.T212_BUDGET_USD = original_budget


@pytest.mark.asyncio
async def test_wallet_sync_buys_missing_coint_t212_tickers(wallet_sync_context, monkeypatch):
    monkeypatch.setattr(
        wallet_sync_context,
        "get_positions",
        lambda: [{"ticker": "AAPL_US_EQ", "quantity": 2.0}],
    )
    monkeypatch.setattr(
        wallet_sync_context,
        "get_pending_orders",
        AsyncMock(return_value=[{"ticker": "MSFT_US_EQ", "quantity": 1.0}]),
    )

    result = await dashboard_service.sync_t212_wallet_for_coint(
        T212WalletSyncRequest(budget=20.0, delay_seconds=0)
    )

    assert result["status"] == "ok"
    assert result["target_tickers"] == ["GOOG", "GOOGL"]
    assert result["skipped"] == [
        {"ticker": "AAPL", "reason": "owned"},
        {"ticker": "MSFT", "reason": "pending_buy"},
    ]
    assert [order["amount"] for order in result["orders"]] == [10.0, 10.0]
    assert wallet_sync_context.place_value_order.await_count == 2
    assert all(call.args[2] == "BUY" for call in wallet_sync_context.place_value_order.await_args_list)


@pytest.mark.asyncio
async def test_wallet_sync_noops_when_every_coint_ticker_is_already_owned(wallet_sync_context, monkeypatch):
    monkeypatch.setattr(
        wallet_sync_context,
        "get_positions",
        lambda: [
            {"ticker": "AAPL_US_EQ", "quantity": 1.0},
            {"ticker": "MSFT_US_EQ", "quantity": 1.0},
            {"ticker": "GOOG_US_EQ", "quantity": 1.0},
            {"ticker": "GOOGL_US_EQ", "quantity": 1.0},
        ],
    )

    result = await dashboard_service.sync_t212_wallet_for_coint(
        T212WalletSyncRequest(budget=20.0, delay_seconds=0)
    )

    assert result["status"] == "ok"
    assert result["target_tickers"] == []
    assert result["orders"] == []
    wallet_sync_context.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_wallet_sync_rejects_budget_above_spendable(wallet_sync_context):
    with pytest.raises(HTTPException) as exc:
        await dashboard_service.sync_t212_wallet_for_coint(
            T212WalletSyncRequest(budget=101.0, delay_seconds=0)
        )

    assert exc.value.status_code == 400
    assert "exceeds spendable" in exc.value.detail
    wallet_sync_context.place_value_order.assert_not_awaited()
