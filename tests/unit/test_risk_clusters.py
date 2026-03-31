import pytest
from src.services.risk_service import RiskService
from src.config import settings

def test_sector_exposure_calculation():
    """
    Verifies that sector exposure is correctly calculated.
    """
    # Mock portfolio with $150 total value, $100 in Financials
    active_portfolio = [
        {"pair_id": "JPM_BAC", "size": 100.0, "sector": "Financials"},
        {"pair_id": "KO_PEP", "size": 50.0, "sector": "Consumer Staples"}
    ]
    
    # Financials exposure should be 100/150 = 66.6%
    result = RiskService.check_cluster_exposure("Financials", active_portfolio)
    assert round(result["exposure_pct"], 2) == 0.67
    
    # Consumer Staples exposure should be 50/150 = 33.3%
    result = RiskService.check_cluster_exposure("Consumer Staples", active_portfolio)
    assert round(result["exposure_pct"], 2) == 0.33

def test_sector_concentration_veto():
    """
    Verifies that the guard correctly flags exposure exceeding the limit.
    """
    # Settings has MAX_SECTOR_EXPOSURE = 0.30
    active_portfolio = [
        {"pair_id": "MSFT_AAPL", "size": 50.0, "sector": "Technology"},
        {"pair_id": "KO_PEP", "size": 100.0, "sector": "Consumer Staples"}
    ]
    
    # Technology is 50/150 = 33% (> 30%) -> Should NOT be allowed
    result = RiskService.check_cluster_exposure("Technology", active_portfolio)
    assert result["allowed"] is False
    
    # Energy is 0/150 = 0% (< 30%) -> Should be allowed
    result = RiskService.check_cluster_exposure("Energy", active_portfolio)
    assert result["allowed"] is True

def test_empty_portfolio_allowed():
    """
    Ensures any sector is allowed if the portfolio is empty.
    """
    active_portfolio = []
    result = RiskService.check_cluster_exposure("Financials", active_portfolio)
    assert result["allowed"] is True
    assert result["exposure_pct"] == 0.0
