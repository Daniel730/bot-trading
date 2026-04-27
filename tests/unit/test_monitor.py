import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.monitor import ArbitrageMonitor
import uuid
from src.config import settings

@pytest.fixture
def monitor():
    # We need to ensure monitor.brokerage is a mock
    with patch("src.services.brokerage_service.BrokerageService") as mock_broker_class:
        m = ArbitrageMonitor(mode="live")
        # Ensure the instance created inside __init__ is our mock
        m.brokerage = mock_broker_class.return_value
        m.brokerage.get_venue.side_effect = lambda ticker: "WEB3" if "-USD" in ticker else "T212"
        return m

@pytest.mark.asyncio
async def test_execute_trade_success(monitor):
    """
    S-07: Test execute_trade path.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())
    
    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock) as mock_shadow, \
         patch.object(settings, "PAPER_TRADING", False):
        
        mock_bid_ask.return_value = (150.0, 150.1) # low spread
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_shadow.return_value = [] # empty portfolio for simplicity
        # get_account_cash is SYNC
        monitor.brokerage.get_account_cash.return_value = 10000.0
        monitor.brokerage.place_value_order = AsyncMock(return_value={"status": "success", "orderId": "123"})
        
        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)
        
        assert monitor.brokerage.place_value_order.call_count == 2
        assert mock_log_trade.call_count == 2
        mock_log_journal.assert_called_once()

@pytest.mark.asyncio
async def test_close_position_success(monitor):
    """
    S-07: Test _close_position path.
    """
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "BUY", "price": 150.0},
            {"ticker": "MSFT", "quantity": 5, "side": "SELL", "price": 300.0}
        ]
    }
    
    from src.services.persistence_service import ExitReason
    with patch("src.services.persistence_service.persistence_service.close_trade", new_callable=AsyncMock) as mock_close, \
         patch.object(settings, "PAPER_TRADING", False):
        monitor.brokerage.place_value_order = AsyncMock(return_value={"status": "success"})
        
        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)
        
        assert monitor.brokerage.place_value_order.call_count == 2
        mock_close.assert_called_once()

@pytest.mark.asyncio
async def test_execute_trade_crypto_live_uses_broker(monitor):
    pair = {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD", "id": "ETH-USD_BTC-USD"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow_exec, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock) as mock_shadow_portfolio, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (100.0, 100.05)
        mock_shadow_portfolio.return_value = []
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        monitor.brokerage.web3.enabled = True
        monitor.brokerage.web3.get_budget_snapshot = AsyncMock(
            return_value={"status": "success", "available_usd": 10000.0, "source": "unit_test"}
        )
        monitor.brokerage.place_value_order = AsyncMock(return_value={"status": "success", "order_id": "0xtx"})

        await monitor.execute_trade(pair, "Short-Long", 2000.0, 50000.0, signal_id)

        assert monitor.brokerage.place_value_order.call_count == 2
        monitor.brokerage.get_account_cash.assert_not_called()
        mock_shadow_exec.assert_not_called()
        assert mock_log_trade.call_count == 2
        mock_log_journal.assert_called_once()

@pytest.mark.asyncio
async def test_execute_trade_crypto_budget_cap_applied(monitor):
    pair = {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD", "id": "ETH-USD_BTC-USD"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=250.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 250.0, "used": 0.0, "remaining": 250.0}), \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "WEB3_BUDGET_USD", 250.0):

        mock_bid_ask.return_value = (100.0, 100.05)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        monitor.brokerage.web3.enabled = True
        monitor.brokerage.web3.get_budget_snapshot = AsyncMock(
            return_value={"status": "success", "available_usd": 1200.0, "source": "unit_test"}
        )
        monitor.brokerage.place_value_order = AsyncMock(return_value={"status": "success", "order_id": "0xtx"})

        await monitor.execute_trade(pair, "Short-Long", 2000.0, 50000.0, signal_id)

        assert monitor.brokerage.place_value_order.call_count == 2
        assert mock_validate_trade.call_count == 1
        assert mock_validate_trade.call_args.kwargs["total_portfolio_cash"] == 250.0

@pytest.mark.asyncio
async def test_orchestrator_veto(monitor):
    """
    S-07: Test orchestrator veto path in process_pair.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}
    
    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock) as mock_audit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True):
        
        mock_kf = MagicMock()
        # New signature: (state, innovation_variance, z_score, spread)
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5) 
        mock_kf_get.return_value = mock_kf
        
        # Orchestrator VETO (confidence < 0.5)
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}
        
        diagnostic = await monitor.process_pair(pair, latest_prices)
        
        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.3
        mock_audit.assert_called_once()
