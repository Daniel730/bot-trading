from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.config import settings
from src.services.dashboard_service import (
    T212WalletRecommendationBuyRequest,
    T212WalletRecommendationRequest,
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
    monkeypatch.setattr(dashboard_state, "add_message", AsyncMock())

    submitted_orders = []
    metadata = {
        f"{ticker}_US_EQ": {"ticker": f"{ticker}_US_EQ", "minTradeQuantity": "0", "tickSize": "0.01"}
        for ticker in ("AAPL", "MSFT", "GOOG", "GOOGL", "KO", "PEP")
    }

    def fake_http_json(method, url, headers=None, payload=None, params=None, timeout=20.0):
        submitted_orders.append({"method": method, "url": url, "payload": payload})
        return {"orderId": f"order-{len(submitted_orders)}"}

    monkeypatch.setattr(dashboard_module.wallet_seed, "t212_config", lambda: ("https://example.test/api/v0", {}))
    monkeypatch.setattr(dashboard_module.wallet_seed, "preflight_t212_access", lambda base_url, headers: None)
    monkeypatch.setattr(dashboard_module.wallet_seed, "fetch_t212_metadata", lambda base_url, headers: metadata)
    monkeypatch.setattr(dashboard_module.wallet_seed, "yahoo_latest_price", lambda ticker: Decimal("100"))
    monkeypatch.setattr(dashboard_module.wallet_seed, "http_json", fake_http_json)

    yield SimpleNamespace(
        brokerage=dashboard_module.brokerage_service,
        submitted_orders=submitted_orders,
    )

    dashboard_state.monitor = original_monitor
    settings.T212_API_KEY = original_key
    settings.TRADING_212_API_KEY = original_alt_key
    settings.T212_BUDGET_USD = original_budget


@pytest.mark.asyncio
async def test_wallet_sync_buys_missing_coint_t212_tickers(wallet_sync_context, monkeypatch):
    monkeypatch.setattr(
        wallet_sync_context.brokerage,
        "get_positions",
        lambda: [{"ticker": "AAPL_US_EQ", "quantity": 2.0}],
    )
    monkeypatch.setattr(
        wallet_sync_context.brokerage,
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
    assert [order["status"] for order in result["orders"]] == ["ok", "ok"]
    assert len(wallet_sync_context.submitted_orders) == 2
    assert all(call["method"] == "POST" for call in wallet_sync_context.submitted_orders)
    assert all(call["url"].endswith("/equity/orders/limit") for call in wallet_sync_context.submitted_orders)
    assert all(call["payload"]["quantity"] > 0 for call in wallet_sync_context.submitted_orders)


@pytest.mark.asyncio
async def test_wallet_sync_noops_when_every_coint_ticker_is_already_owned(wallet_sync_context, monkeypatch):
    monkeypatch.setattr(
        wallet_sync_context.brokerage,
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
    assert wallet_sync_context.submitted_orders == []


@pytest.mark.asyncio
async def test_wallet_sync_rejects_budget_above_spendable(wallet_sync_context):
    with pytest.raises(HTTPException) as exc:
        await dashboard_service.sync_t212_wallet_for_coint(
            T212WalletSyncRequest(budget=101.0, delay_seconds=0)
        )

    assert exc.value.status_code == 400
    assert "exceeds spendable" in exc.value.detail
    assert wallet_sync_context.submitted_orders == []


@pytest.mark.asyncio
async def test_wallet_recommendations_default_to_coint_only(wallet_sync_context, monkeypatch):
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )

    result = await dashboard_service.calculate_t212_wallet_recommendations(
        T212WalletRecommendationRequest(budget=40.0, include_broken=False)
    )

    assert result["status"] == "ok"
    assert result["coint_pairs"] == 2
    assert result["broken_eligible_pairs"] == 1
    assert result["recommended_tickers"] == ["AAPL", "MSFT", "GOOG", "GOOGL"]
    assert {item["category"] for item in result["recommendations"]} == {"coint"}
    assert sum(item["suggested_amount"] for item in result["recommendations"]) == 40.0


@pytest.mark.asyncio
async def test_wallet_recommendations_can_include_broken_eligible(wallet_sync_context, monkeypatch):
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )

    result = await dashboard_service.calculate_t212_wallet_recommendations(
        T212WalletRecommendationRequest(budget=60.0, include_broken=True)
    )

    assert result["recommended_tickers"][:4] == ["AAPL", "MSFT", "GOOG", "GOOGL"]
    assert set(result["recommended_tickers"]) == {"AAPL", "MSFT", "GOOG", "GOOGL", "KO", "PEP"}
    broken = [item for item in result["recommendations"] if item["category"] == "broken_eligible"]
    assert [item["ticker"] for item in broken] == ["KO", "PEP"]
    assert sum(item["suggested_amount"] for item in result["recommendations"]) == 60.0


@pytest.mark.asyncio
async def test_buy_wallet_recommendations_submits_selected_broken_tickers(wallet_sync_context, monkeypatch):
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )

    result = await dashboard_service.buy_t212_wallet_recommendations(
        T212WalletRecommendationBuyRequest(
            budget=20.0,
            include_broken=True,
            tickers=["KO", "PEP"],
            delay_seconds=0,
        )
    )

    assert result["status"] == "ok"
    assert result["target_tickers"] == ["KO", "PEP"]
    assert [order["ticker"] for order in result["orders"]] == ["KO", "PEP"]
    assert [order["amount"] for order in result["orders"]] == [10.0, 10.0]
    assert len(wallet_sync_context.submitted_orders) == 2
