import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.cash_management_service import cash_management_service

@pytest.mark.asyncio
async def test_sweep_idle_cash_fixed():
    """
    A-01: Verify fix for missing await for get_account_cash() in sweep_idle_cash().
    """
    with patch("src.services.cash_management_service.brokerage_service") as mock_broker:
        mock_broker.get_account_cash = AsyncMock(return_value=100.0)
        mock_broker.execute_order = AsyncMock(return_value={"status": "success"})
        
        # Mock persistence to avoid real DB hits in unit tests if possible, 
        # but here we also want to verify it works.
        cash_management_service.persistence.save_cash_sweep = MagicMock()
        
        await cash_management_service.sweep_idle_cash()
        mock_broker.get_account_cash.assert_called_once()
        mock_broker.execute_order.assert_called_once()
        cash_management_service.persistence.save_cash_sweep.assert_called_once()

@pytest.mark.asyncio
async def test_liquidate_for_trade_fixed():
    """
    A-01: Verify fix for missing await for get_portfolio() and get_latest_price() in liquidate_for_trade().
    """
    mock_portfolio = [{"ticker": "SGOV", "quantity": 10, "averagePrice": 100}]
    with patch("src.services.cash_management_service.brokerage_service") as mock_broker, \
         patch("src.services.data_service.data_service.get_latest_price", new_callable=AsyncMock) as mock_prices:
        
        mock_broker.get_portfolio = AsyncMock(return_value=mock_portfolio)
        mock_broker._format_ticker = lambda x: x 
        mock_broker.execute_order = AsyncMock(return_value={"status": "success"})
        mock_prices.return_value = {"SGOV": 101.0}
        
        cash_management_service.persistence.save_cash_sweep = MagicMock()
        
        await cash_management_service.liquidate_for_trade(50.0)
        mock_broker.get_portfolio.assert_called_once()
        mock_prices.assert_called_once_with(["SGOV"])
        mock_broker.execute_order.assert_called_once()
        cash_management_service.persistence.save_cash_sweep.assert_called_once()
