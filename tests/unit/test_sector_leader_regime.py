import pytest
import pandas as pd
import numpy as np
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.agents.macro_economic_agent import macro_economic_agent
from src.agents.orchestrator import orchestrator

@pytest.mark.asyncio
async def test_regime_bullish_sma():
    """Test H4: BULLISH regime (SMA20 > SMA50)"""
    # Create 60 days of data where SMA20 is above SMA50
    # Last 20 days: Price 110, First 40 days: Price 100
    prices = [100] * 40 + [110] * 20
    df = pd.DataFrame({"NVDA": prices}, index=pd.date_range("2024-01-01", periods=60))
    
    with patch('src.services.data_service.DataService.get_historical_data', return_value=df):
        regime = await macro_economic_agent.get_ticker_regime("NVDA")
        assert regime == "BULLISH"

@pytest.mark.asyncio
async def test_regime_bearish_sma():
    """Test H4: BEARISH regime (SMA20 < SMA50)"""
    # Last 20 days: Price 90, First 40 days: Price 100
    prices = [100] * 40 + [90] * 20
    df = pd.DataFrame({"NVDA": prices}, index=pd.date_range("2024-01-01", periods=60))
    
    with patch('src.services.data_service.DataService.get_historical_data', return_value=df):
        regime = await macro_economic_agent.get_ticker_regime("NVDA")
        assert regime == "BEARISH"

@pytest.mark.asyncio
async def test_regime_extreme_volatility():
    """Test H4: EXTREME_VOLATILITY (>3% drop)"""
    # Last day drop from 100 to 95 (5% drop)
    prices = [100] * 59 + [95]
    df = pd.DataFrame({"NVDA": prices}, index=pd.date_range("2024-01-01", periods=60))
    
    with patch('src.services.data_service.DataService.get_historical_data', return_value=df):
        regime = await macro_economic_agent.get_ticker_regime("NVDA")
        assert regime == "EXTREME_VOLATILITY"

@pytest.mark.asyncio
async def test_orchestrator_sector_veto():
    """Test H4: Orchestrator veto when sector leader is in panic"""
    state = {
        'signal_context': {
            'ticker_a': 'AMD',
            'ticker_b': 'TSMC',
            'signal_id': 'IA_SCAN_001',
            'sector': 'Technology',
        },
        'bull_verdict': {'confidence': 0.9},
        'bear_verdict': {'confidence': 0.1},
        'system_state': {'consecutive_api_timeouts': '0'}
    }
    
    # Mock NVDA (leader for AMD/TSMC) returning EXTREME_VOLATILITY
    with patch('src.agents.macro_economic_agent.macro_economic_agent.get_ticker_regime', return_value="EXTREME_VOLATILITY"), \
         patch('src.services.persistence_service.persistence_service.get_agent_metrics', new_callable=AsyncMock, return_value=(1,1)), \
         patch('src.services.persistence_service.persistence_service.get_system_state', new_callable=AsyncMock, return_value="0"), \
         patch('src.services.persistence_service.persistence_service.set_system_state', new_callable=AsyncMock, return_value=None), \
         patch('src.services.redis_service.redis_service.get_kalman_state', new_callable=AsyncMock, return_value=None), \
         patch('src.services.telemetry_service.telemetry_service.broadcast', return_value=None), \
         patch('src.agents.portfolio_manager_agent.portfolio_manager_agent.get_optimization_advice', new_callable=AsyncMock, return_value={"is_recommended": True, "improvement": 0.1}):
        
        final_state = await orchestrator.ainvoke(state)
        
        assert final_state['final_confidence'] == 0.0
        assert "CRITICAL VETO" in final_state['final_verdict']
        assert "NVDA" in final_state['final_verdict']


@pytest.mark.asyncio
async def test_orchestrator_missing_sector_defaults_to_spy():
    """Unmapped pairs should use SPY, not the Technology/NVDA beacon."""
    state = {
        'signal_context': {'ticker_a': 'PNC', 'ticker_b': 'USB', 'signal_id': 'IA_SCAN_002'},
    }

    with patch('src.agents.macro_economic_agent.macro_economic_agent.get_ticker_regime', return_value="EXTREME_VOLATILITY") as mock_regime, \
         patch('src.services.persistence_service.persistence_service.get_system_state', new_callable=AsyncMock, return_value="0"), \
         patch('src.services.telemetry_service.telemetry_service.broadcast', return_value=None):

        final_state = await orchestrator.ainvoke(state)

        mock_regime.assert_awaited_once_with("SPY")
        assert final_state['final_confidence'] == 0.0
        assert "CRITICAL VETO" in final_state['final_verdict']
        assert "SPY" in final_state['final_verdict']
