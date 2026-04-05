import pytest
from src.services.dca_service import DRIPManager

def test_drip_accumulation():
    drip = DRIPManager(min_sweep_threshold=1.0)
    
    # Add $0.40 dividend
    drip.add_dividend(ticker="AAPL", amount=0.40)
    assert drip.get_balance("AAPL") == 0.40
    assert drip.should_sweep("AAPL") is False
    
    # Add $0.70 more -> Total $1.10
    drip.add_dividend(ticker="AAPL", amount=0.70)
    assert drip.get_balance("AAPL") == 1.10
    assert drip.should_sweep("AAPL") is True

def test_drip_sweep_reset():
    drip = DRIPManager(min_sweep_threshold=1.0)
    drip.add_dividend(ticker="AAPL", amount=1.50)
    
    amount_to_invest = drip.sweep("AAPL")
    assert amount_to_invest == 1.50
    assert drip.get_balance("AAPL") == 0.0
