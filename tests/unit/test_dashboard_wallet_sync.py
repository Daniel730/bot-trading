import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from src.config import settings
from src.services.dashboard_service import (
    WalletRecommendationBuyRequest,
    WalletRecommendationRequest,
    WalletSyncRequest,
    dashboard_service,
    dashboard_state,
)


@pytest.fixture
def wallet_context(monkeypatch):
    """
    Provide a pytest fixture that configures a controllable wallet testing environment and yields a factory to build provider-specific mocked brokerages.
    
    The fixture replaces dashboard_state.monitor with a SimpleNamespace containing predefined active_pairs, sets settings.T212_BUDGET_USD to 0.0, and patches dashboard_service.brokerage_service methods to predictable test doubles. After the test, original monitor, provider_name, and budget are restored.
    
    Parameters:
        monkeypatch (pytest.MonkeyPatch): Pytest monkeypatch fixture used to apply temporary attribute/method patches.
    
    Returns:
        build (Callable[[str], SimpleNamespace]): A factory that accepts a `provider_name` and returns a SimpleNamespace with:
            - brokerage: the patched brokerage_service
            - place_value_order: an AsyncMock that simulates placing value orders and returns a success dict including a provider-prefixed order_id
    """
    import src.services.dashboard_service as dashboard_module

    original_monitor = dashboard_state.monitor
    original_provider_name = dashboard_module.brokerage_service.provider_name
    original_budget = settings.T212_BUDGET_USD

    settings.T212_BUDGET_USD = 0.0
    dashboard_state.monitor = SimpleNamespace(
        active_pairs=[
            {"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT", "is_cointegrated": True},
            {"id": "KO_PEP", "ticker_a": "KO", "ticker_b": "PEP", "is_cointegrated": False},
            {"id": "BTC_ETH", "ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "is_cointegrated": True},
            {"id": "GOOG_GOOGL", "ticker_a": "GOOG", "ticker_b": "GOOGL", "is_cointegrated": True},
        ]
    )

    def build(provider_name: str):
        """
        Create a mocked brokerage environment configured for the given provider name.
        
        Sets dashboard_module.brokerage_service.provider_name and monkeypatches the brokerage methods to deterministic test doubles:
        - connection and account queries return fixed success/cash values,
        - position and pending-order queries return empty results,
        - get_venue maps tickers containing "-USD" to "WEB3" otherwise to the provider name,
        - place_value_order is an AsyncMock that simulates successful order placement and returns a dict with `status` and an `order_id` prefixed by the lowercased provider name.
        
        Parameters:
            provider_name (str): The provider name to apply to the mocked brokerage.
        
        Returns:
            SimpleNamespace: Contains two attributes:
                - brokerage: the patched brokerage service object.
                - place_value_order: the AsyncMock used for placing value orders (awaitable).
        """
        brokerage = dashboard_module.brokerage_service
        brokerage.provider_name = provider_name

        monkeypatch.setattr(brokerage, "test_connection", lambda: True)
        monkeypatch.setattr(
            brokerage,
            "get_venue",
            lambda ticker: "WEB3" if "-USD" in str(ticker).upper() else provider_name,
        )
        monkeypatch.setattr(brokerage, "get_account_cash", lambda: 100.0)
        monkeypatch.setattr(brokerage, "get_pending_orders_value", AsyncMock(return_value=0.0))
        monkeypatch.setattr(brokerage, "get_positions", lambda: [])
        monkeypatch.setattr(brokerage, "get_pending_orders", AsyncMock(return_value=[]))
        monkeypatch.setattr(dashboard_state, "add_message", AsyncMock())

        async def fake_place_value_order(ticker, amount, side, *args, **kwargs):
            """
            Return a fake successful order response for tests.
            
            Returns:
                dict: Response with 'status' set to 'success' and 'order_id' formatted as '<provider>-<ticker>', where '<provider>' is the lowercased `provider_name` from the enclosing scope and '<ticker>' is the supplied ticker.
            """
            return {"status": "success", "order_id": f"{provider_name.lower()}-{ticker}"}

        place_value_order = AsyncMock(side_effect=fake_place_value_order)
        monkeypatch.setattr(brokerage, "place_value_order", place_value_order)

        return SimpleNamespace(
            brokerage=brokerage,
            place_value_order=place_value_order,
        )

    yield build

    dashboard_state.monitor = original_monitor
    dashboard_module.brokerage_service.provider_name = original_provider_name
    settings.T212_BUDGET_USD = original_budget


@pytest.mark.asyncio
async def test_wallet_sync_buys_missing_active_t212_tickers(wallet_context, monkeypatch):
    context = wallet_context("T212")
    monkeypatch.setattr(
        context.brokerage,
        "get_positions",
        lambda: [
            {"ticker": "AAPL_US_EQ", "quantity": 2.0},
            {"ticker": "AAPL", "quantity": 2.0},
        ],
    )
    monkeypatch.setattr(
        context.brokerage,
        "get_pending_orders",
        AsyncMock(
            return_value=[
                {"ticker": "MSFT_US_EQ", "quantity": 1.0},
                {"ticker": "MSFT", "quantity": 1.0},
            ]
        ),
    )

    result = await dashboard_service.sync_wallet_for_coint(
        WalletSyncRequest(budget=20.0, delay_seconds=0)
    )

    assert result["status"] == "ok"
    assert result["mode"] == "T212"
    assert result["target_tickers"] == ["KO", "PEP", "GOOG", "GOOGL"]
    assert result["skipped"] == [
        {"ticker": "AAPL", "reason": "owned"},
        {"ticker": "MSFT", "reason": "pending_buy"},
    ]
    assert [order["amount"] for order in result["orders"]] == [5.0, 5.0, 5.0, 5.0]
    assert context.place_value_order.await_args_list == [
        call("KO", 5.0, "BUY"),
        call("PEP", 5.0, "BUY"),
        call("GOOG", 5.0, "BUY"),
        call("GOOGL", 5.0, "BUY"),
    ]


@pytest.mark.asyncio
async def test_wallet_sync_uses_active_alpaca_provider_and_raw_tickers(wallet_context, monkeypatch):
    context = wallet_context("ALPACA")
    monkeypatch.setattr(
        context.brokerage,
        "get_positions",
        lambda: [{"ticker": "AAPL", "quantity": 2.0}],
    )
    monkeypatch.setattr(
        context.brokerage,
        "get_pending_orders",
        AsyncMock(return_value=[{"ticker": "MSFT", "quantity": 1.0}]),
    )

    result = await dashboard_service.sync_wallet_for_coint(
        WalletSyncRequest(budget=20.0, delay_seconds=0)
    )

    assert result["status"] == "ok"
    assert result["mode"] == "ALPACA"
    assert result["target_tickers"] == ["KO", "PEP", "GOOG", "GOOGL"]
    assert context.place_value_order.await_args_list == [
        call("KO", 5.0, "BUY"),
        call("PEP", 5.0, "BUY"),
        call("GOOG", 5.0, "BUY"),
        call("GOOGL", 5.0, "BUY"),
    ]


@pytest.mark.asyncio
async def test_wallet_sync_noops_when_every_active_alpaca_ticker_is_already_owned(wallet_context, monkeypatch):
    context = wallet_context("ALPACA")
    monkeypatch.setattr(
        context.brokerage,
        "get_positions",
        lambda: [
            {"ticker": "AAPL", "quantity": 1.0},
            {"ticker": "MSFT", "quantity": 1.0},
            {"ticker": "KO", "quantity": 1.0},
            {"ticker": "PEP", "quantity": 1.0},
            {"ticker": "GOOG", "quantity": 1.0},
            {"ticker": "GOOGL", "quantity": 1.0},
        ],
    )

    result = await dashboard_service.sync_wallet_for_coint(
        WalletSyncRequest(budget=20.0, delay_seconds=0)
    )

    assert result["status"] == "ok"
    assert result["target_tickers"] == []
    assert result["orders"] == []
    context.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_wallet_sync_warns_but_proceeds_when_budget_above_spendable(wallet_context, caplog):
    context = wallet_context("T212")

    with caplog.at_level(logging.WARNING):
        result = await dashboard_service.sync_wallet_for_coint(
            WalletSyncRequest(budget=101.0, delay_seconds=0)
        )

    assert result["status"] == "ok"
    assert context.place_value_order.await_count == 6
    assert any(
        "Wallet sync budget" in record.getMessage()
        and "exceeds spendable T212" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_wallet_recommendations_include_all_active_tickers_by_default(wallet_context, monkeypatch, caplog):
    wallet_context("T212")
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )

    with caplog.at_level(logging.WARNING):
        result = await dashboard_service.calculate_wallet_recommendations(
            WalletRecommendationRequest(budget=40.0, include_broken=False)
        )

    assert result["status"] == "ok"
    assert result["coint_pairs"] == 2
    assert result["broken_eligible_pairs"] == 1
    assert result["recommended_tickers"][:4] == ["AAPL", "MSFT", "GOOG", "GOOGL"]
    assert set(result["recommended_tickers"]) == {"AAPL", "MSFT", "GOOG", "GOOGL", "KO", "PEP"}
    assert {item["category"] for item in result["recommendations"]} == {"coint", "broken_eligible"}
    assert sum(item["suggested_amount"] for item in result["recommendations"]) == 40.0
    assert [
        record.getMessage()
        for record in caplog.records
        if "Including non-COINT ticker" in record.getMessage()
    ] == [
        "DASHBOARD: Including non-COINT ticker KO in candidates for T212",
        "DASHBOARD: Including non-COINT ticker PEP in candidates for T212",
    ]


@pytest.mark.asyncio
async def test_wallet_recommendations_use_raw_alpaca_broker_tickers(wallet_context, monkeypatch):
    wallet_context("ALPACA")
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )

    result = await dashboard_service.calculate_wallet_recommendations(
        WalletRecommendationRequest(budget=60.0, include_broken=True)
    )

    assert result["mode"] == "ALPACA"
    assert set(result["recommended_tickers"]) == {"AAPL", "MSFT", "GOOG", "GOOGL", "KO", "PEP"}
    assert {item["ticker"]: item["broker_ticker"] for item in result["recommendations"]} == {
        "AAPL": "AAPL",
        "MSFT": "MSFT",
        "GOOG": "GOOG",
        "GOOGL": "GOOGL",
        "KO": "KO",
        "PEP": "PEP",
    }


@pytest.mark.asyncio
async def test_buy_wallet_recommendations_submits_selected_broken_tickers(wallet_context, monkeypatch):
    context = wallet_context("T212")
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )

    result = await dashboard_service.buy_wallet_recommendations(
        WalletRecommendationBuyRequest(
            budget=20.0,
            include_broken=True,
            tickers=["KO", "PEP"],
            delay_seconds=0,
        )
    )

    assert result["status"] == "ok"
    assert result["target_tickers"] == ["KO", "PEP"]
    assert [order["ticker"] for order in result["orders"]] == ["KO", "PEP"]
    assert context.place_value_order.await_args_list == [
        call("KO", 10.0, "BUY"),
        call("PEP", 10.0, "BUY"),
    ]


@pytest.mark.asyncio
async def test_buy_wallet_recommendations_places_alpaca_coint_orders(wallet_context, monkeypatch):
    context = wallet_context("ALPACA")
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )

    result = await dashboard_service.buy_wallet_recommendations(
        WalletRecommendationBuyRequest(
            budget=50.0,
            include_broken=False,
            tickers=["AAPL", "MSFT"],
            delay_seconds=0,
        )
    )

    assert result["status"] == "ok"
    assert result["mode"] == "ALPACA"
    assert result["target_tickers"] == ["AAPL", "MSFT"]
    assert [item["broker_ticker"] for item in result["recommendations"]] == ["AAPL", "MSFT"]
    assert context.place_value_order.await_args_list == [
        call("AAPL", 25.0, "BUY"),
        call("MSFT", 25.0, "BUY"),
    ]


@pytest.mark.asyncio
async def test_buy_wallet_recommendations_manual_override_for_skipped_ticker(wallet_context, monkeypatch, caplog):
    context = wallet_context("ALPACA")
    monkeypatch.setattr(
        dashboard_service,
        "_wallet_pair_z_scores",
        AsyncMock(return_value={"AAPL_MSFT": 2.4, "KO_PEP": 3.1, "GOOG_GOOGL": 1.2}),
    )
    monkeypatch.setattr(
        context.brokerage,
        "get_positions",
        lambda: [{"ticker": "KO", "quantity": 1.0}],
    )

    with caplog.at_level(logging.WARNING):
        result = await dashboard_service.buy_wallet_recommendations(
            WalletRecommendationBuyRequest(
                budget=10.0,
                include_broken=False,
                tickers=["KO"],
                delay_seconds=0,
            )
        )

    assert result["status"] == "ok"
    assert result["target_tickers"] == ["KO"]
    assert result["recommendations"][0]["category"] == "manual_override"
    assert context.place_value_order.await_args_list == [call("KO", 10.0, "BUY")]
    assert any(
        "Manual override buy for non-recommended ticker KO" in record.getMessage()
        for record in caplog.records
    )
