import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.brokerage_service import BrokerageService
from src.services.brokerage.alpaca import AlpacaProvider

@pytest.fixture
def mock_alpaca():
    mock = MagicMock(spec=AlpacaProvider)
    mock.trade_api = MagicMock()

    # Mock account methods
    mock.get_account_cash.return_value = 1000.0
    mock.get_account_equity.return_value = 5000.0
    mock.get_account_buying_power.return_value = 2000.0

    # Mock order methods
    mock.get_pending_orders.return_value = []
    mock.place_value_order = AsyncMock(return_value={"status": "submitted", "ticker": "AAPL"})

    return mock

@pytest.mark.asyncio
async def test_budget_management(mock_alpaca):
    service = BrokerageService()
    service.provider = mock_alpaca # Inject mock

    cash = await service.get_account_cash()
    equity = await service.get_account_equity()
    bp = await service.get_account_buying_power()

    assert float(cash) == 1000.0
    assert float(equity) == 5000.0
    assert float(bp) == 2000.0

@pytest.mark.asyncio
async def test_atomic_leg_execution(mock_alpaca):
    service = BrokerageService()
    service.provider = mock_alpaca

    # Test place_value_order (Leg A)
    res_a = await service.place_value_order("AAPL", 500.0, "buy")
    assert res_a["status"] == "submitted"

    # Test place_value_order (Leg B)
    res_b = await service.place_value_order("MSFT", 500.0, "sell")
    assert res_b["status"] == "submitted"

    # Verify the provider method was called twice
    assert mock_alpaca.place_value_order.call_count == 2

@pytest.mark.asyncio
async def test_pending_orders_value(mock_alpaca):
    service = BrokerageService()
    service.provider = mock_alpaca

    # Mock a pending order list
    mock_alpaca.get_pending_orders.return_value = [
        {"ticker": "AAPL", "quantity": 1, "price": 200.0}
    ]

    pending_val = await service.get_pending_orders_value()
    assert float(pending_val) == 200.0
