import pytest
from src.services.risk_service import RiskService
from src.config import settings

def test_fee_calculation():
    risk = RiskService()
    
    # $100 trade, 1% spread, no commission/FX
    res = risk.calculate_friction(100.0, 1.0, 0.0, 0.0)
    assert res['total_cost'] == 1.0
    assert res['friction_pct'] == 0.01
    assert not res['is_excessive'] # 1.0% < 1.5%

    # $10 trade, 1% spread + $0.50 commission
    # Costs: $0.10 (spread) + $0.50 (comm) = $0.60
    # $0.60 / $10 = 6.0% friction
    res = risk.calculate_friction(10.0, 1.0, 0.50, 0.0)
    assert res['total_cost'] == 0.60
    assert res['friction_pct'] == 0.06
    assert res['is_excessive'] # 6% > 1.5%

def test_trade_allowed_limits():
    risk = RiskService()
    
    # Within limits
    res = risk.is_trade_allowed(10.0, 0.01)
    assert res['allowed'] == True
    
    # Below minimum value ($1.00)
    res = risk.is_trade_allowed(0.50, 0.001)
    assert res['allowed'] == False
    assert "below minimum" in res['reason'].lower()
    
    # Above max friction (1.5%)
    res = risk.is_trade_allowed(10.0, 0.02)
    assert res['allowed'] == False
    assert "exceeds limit" in res['reason'].lower()


def test_validate_trade_checks_fees_on_final_sized_amount():
    risk = RiskService()

    result = risk.validate_trade("AAPL", total_portfolio_cash=500.0, amount_fiat=500.0)

    assert result["is_acceptable"] is False
    assert result["final_amount"] == 0.0
    assert "friction" in result["rejection_reason"].lower()
