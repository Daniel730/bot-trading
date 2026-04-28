import pytest
import asyncio
import uuid
from unittest.mock import MagicMock, patch
from src.services.risk_service import risk_service
from src.services.volatility_service import volatility_service
from src.services.performance_service import performance_service
from src.services.execution_service_client import execution_client
from src.services.redis_service import redis_service

@pytest.mark.asyncio
async def test_volatility_switch_trigger():
    """
    Test SC-002: Volatility Switch identifies 95% of volatility spikes using L2 entropy.
    Test User Story 3: max_slippage_pct reduced in HIGH_VOLATILITY.
    """
    ticker = "BTC-USD"
    
    # Mock High Entropy L2 Snapshot (many small orders, high randomness)
    # Shannon Entropy will be high
    high_entropy_snapshot = {
        "bids": [[10000 - i, 0.01] for i in range(20)],
        "asks": [[10001 + i, 0.01] for i in range(20)]
    }
    
    with patch.object(redis_service, 'get_json', return_value=high_entropy_snapshot), \
         patch.object(performance_service, 'get_portfolio_metrics', return_value={"sharpe_ratio": 1.5, "max_drawdown": 0.05}):
        status = await volatility_service.get_volatility_status(ticker)
        assert status == "HIGH_VOLATILITY"

        params = await risk_service.get_execution_params(ticker)
        assert params["max_slippage_pct"] == 0.0005 # Tightened from 0.001

@pytest.mark.asyncio
async def test_drawdown_risk_scaling():
    """
    Test SC-001: Position size scales linearly with drawdown: 0% at 15% drawdown.
    Test User Story 1 Acceptance 2: Sharpe ratio < 0.5 => Kelly fraction capped at 0.1.
    """
    ticker = "ETH-USD"
    
    # Mock 10% Drawdown and 1.2 Sharpe
    with patch.object(performance_service, 'get_portfolio_metrics', return_value={
        "sharpe_ratio": 1.2,
        "max_drawdown": 0.10
    }):
        params = await risk_service.get_execution_params(ticker)
        # 1.0 - (0.10 / 0.15) = 1.0 - 0.666 = 0.333
        assert 0.33 < params["risk_multiplier"] < 0.34
        
    # Mock 16% Drawdown (Absolute Stop)
    with patch.object(performance_service, 'get_portfolio_metrics', return_value={
        "sharpe_ratio": 1.2,
        "max_drawdown": 0.16
    }):
        params = await risk_service.get_execution_params(ticker)
        assert params["risk_multiplier"] == 0.0

    # Mock low Sharpe ratio (< 0.5)
    with patch.object(performance_service, 'get_portfolio_metrics', return_value={
        "sharpe_ratio": 0.4,
        "max_drawdown": 0.02
    }):
        params = await risk_service.get_execution_params(ticker)
        assert params["risk_multiplier"] == 0.1 # Capped

@pytest.mark.asyncio
async def test_execution_client_dynamic_params():
    """
    Verifies that ExecutionServiceClient fetches dynamic params when none provided.
    """
    signal_id = str(uuid.uuid4())
    legs = [{"ticker": "KO", "side": "BUY", "quantity": 100, "target_price": 60.0}]
    
    # Mock RiskService and Redis lock
    mock_params = {
        "risk_multiplier": 0.5,
        "max_slippage_pct": 0.0005,
        "volatility_status": "HIGH_VOLATILITY"
    }
    
    with patch.object(redis_service, 'set_nx', return_value=True), \
         patch.object(risk_service, 'get_execution_params', return_value=mock_params), \
         patch.object(execution_client, 'get_stub') as mock_stub_factory:
        
        mock_stub = MagicMock()
        # Create a mock for the method that returns a future
        mock_execute = MagicMock()
        future = asyncio.Future()
        future.set_result(MagicMock(status=1)) # STATUS_SUCCESS
        mock_execute.return_value = future
        mock_stub.ExecuteTrade = mock_execute
        
        mock_stub_factory.return_value = mock_stub
        
        await execution_client.execute_trade(signal_id, "KO_PEP", legs)
        
        # Verify call arguments (proto fields are exact decimal strings)
        call_args = mock_execute.call_args
        request = call_args[0][0]
        assert float(request.risk_multiplier) == 0.5
        assert float(request.max_slippage_pct) == 0.0005
