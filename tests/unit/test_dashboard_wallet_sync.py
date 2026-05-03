from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.dashboard_service import (
    WalletRecommendationBuyRequest,
    WalletRecommendationRequest,
    WalletSyncRequest,
    dashboard_service,
    dashboard_state,
    brokerage_service,
)


@pytest.fixture
def alpaca_wallet_context(monkeypatch):
    original_monitor = dashboard_state.monitor
    dashboard_state.monitor = SimpleNamespace(
        active_pairs=[
            {"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT", "is_cointegrated": True},
        ]
    )

    monkeypatch.setattr(brokerage_service, "provider_name", "ALPACA")
    monkeypatch.setattr(brokerage_service, "provider", SimpleNamespace(is_supported_symbol=lambda ticker: True))
    monkeypatch.setattr(brokerage_service, "get_venue", lambda ticker: "ALPACA")
    monkeypatch.setattr(brokerage_service, "is_asset_active", AsyncMock(return_value=True))
    monkeypatch.setattr(brokerage_service, "test_connection", MagicMock(return_value=True))
    monkeypatch.setattr(brokerage_service, "get_positions", AsyncMock(return_value=[]))
    monkeypatch.setattr(brokerage_service, "get_pending_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(brokerage_service, "get_account_cash", AsyncMock(return_value=1000.0))
    monkeypatch.setattr(brokerage_service, "get_pending_orders_value", AsyncMock(return_value=0.0))
    place_value_order = AsyncMock(return_value={"status": "success", "order_id": "order-1"})
    monkeypatch.setattr(brokerage_service, "place_value_order", place_value_order)

    monkeypatch.setattr("src.services.budget_service.budget_service.get_effective_cash", lambda venue, cash: cash)
    monkeypatch.setattr("src.services.dashboard_service.dashboard_state.add_message", AsyncMock())

    yield SimpleNamespace(place_value_order=place_value_order)
    dashboard_state.monitor = original_monitor


@pytest.mark.asyncio
async def test_wallet_recommendations_are_alpaca_only(alpaca_wallet_context):
    result = await dashboard_service.calculate_wallet_recommendations(
        WalletRecommendationRequest(budget=100.0)
    )

    assert result["mode"] == "ALPACA"
    assert result["recommended_tickers"] == ["AAPL", "MSFT"]
    assert result["usable_budget"] == 100.0
    assert all(item["broker_ticker"] in {"AAPL", "MSFT"} for item in result["recommendations"])


@pytest.mark.asyncio
async def test_wallet_sync_places_weighted_alpaca_buy_orders(alpaca_wallet_context):
    result = await dashboard_service.sync_wallet_for_coint(WalletSyncRequest(budget=100.0))

    assert result["mode"] == "ALPACA"
    assert result["status"] == "ok"
    assert result["target_tickers"] == ["AAPL", "MSFT"]
    assert alpaca_wallet_context.place_value_order.await_count == 2


@pytest.mark.asyncio
async def test_wallet_recommendation_buy_uses_alpaca_orders(alpaca_wallet_context):
    result = await dashboard_service.buy_wallet_recommendations(
        WalletRecommendationBuyRequest(budget=100.0, tickers=["AAPL"])
    )

    assert result["mode"] == "ALPACA"
    assert result["target_tickers"] == ["AAPL"]
    alpaca_wallet_context.place_value_order.assert_awaited_once()
