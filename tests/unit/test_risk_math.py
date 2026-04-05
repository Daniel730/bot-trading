import pytest
from src.services.risk_service import RiskService

def test_friction_conversion():
    """
    T012: Verifies that flat spread inputs are converted to percentage
    and checked against the 1.5% limit.
    """
    risk_service = RiskService()
    
    # Test 1: $1000 trade, $10 flat spread = 1.0% (Acceptable < 1.5%)
    # User said: "Ensure the 0.5 spread is treated as a flat monetary value"
    # Wait, the task says "0.5 spread". Is it $0.50? 
    # Spec says: "3. Risk: Friction calculations MUST correctly convert flat spread inputs into percentage-based values before validating against MAX_FRICTION_PCT."
    # User prompt: "Ensure the 0.5 spread is treated as a flat monetary value"
    
    # Let's assume calculate_friction(amount, flat_spread)
    
    # If I use FeeAnalyzer.check_fees currently:
    # check_fees(ticker, amount, commission, fx_fee, spread_est)
    
    result = risk_service.calculate_friction(1000.0, flat_spread=10.0)
    assert result["is_acceptable"] is True
    assert result["friction_pct"] == 0.01 # 1%
    
    # Test 2: $100 trade, $2 flat spread = 2.0% (Rejected > 1.5%)
    result = risk_service.calculate_friction(100.0, flat_spread=2.0)
    assert result["is_acceptable"] is False
    assert result["friction_pct"] == 0.02 # 2%
    assert "exceeds limit" in result["rejection_reason"]

if __name__ == "__main__":
    test_friction_conversion()
