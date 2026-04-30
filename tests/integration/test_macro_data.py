import pytest
import asyncio
from src.agents.macro_economic_agent import macro_economic_agent
from unittest.mock import AsyncMock, patch, MagicMock
import pandas as pd

def test_macro_data_retrieval():
    # Mock data_service to avoid real network calls
    with patch('src.services.data_service.data_service.get_latest_price_async', new_callable=AsyncMock) as mock_price:
        mock_price.return_value = {"^TNX": 4.2, "^VIX": 15.0, "SPY": 500.0, "QQQ": 400.0}
        
        with patch('src.services.data_service.data_service.get_historical_data_async', new_callable=AsyncMock) as mock_hist:
            # Mock SPY history for MA calculation
            df = pd.DataFrame({
                'Close': [400.0] * 200 # Constant prices
            })
            mock_hist.return_value = df
            
            summary = asyncio.run(macro_economic_agent.get_macro_summary())
            
            assert summary['yield_10y'] == 4.2
            assert summary['vix'] == 15.0
            assert summary['market_trend'] == "Bullish" # 500 > 400
            assert summary['risk_on'] == True
