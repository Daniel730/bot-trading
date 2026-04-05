import pytest
from src.services.risk_service import FeeAnalyzer

def test_fee_analyzer_rejects_high_friction():
    analyzer = FeeAnalyzer(max_friction_pct=0.02)
    
    # Case 1: $1 fee on $10 trade (10% friction) -> Should Reject
    result = analyzer.check_fees(ticker="AAPL", amount_fiat=10.0, commission=1.0)
    assert result["is_acceptable"] is False
    assert result["total_friction_percent"] == 0.10

def test_fee_analyzer_accepts_low_friction():
    analyzer = FeeAnalyzer(max_friction_pct=0.02)
    
    # Case 2: $0.10 fee on $10 trade (1% friction) -> Should Accept
    result = analyzer.check_fees(ticker="AAPL", amount_fiat=10.0, commission=0.1)
    assert result["is_acceptable"] is True
    assert result["total_friction_percent"] == 0.01

def test_fee_analyzer_fx_impact():
    analyzer = FeeAnalyzer(max_friction_pct=0.02)
    
    # Case 3: $0.05 commission + $0.20 FX fee on $10 trade (2.5% friction) -> Should Reject
    result = analyzer.check_fees(ticker="AAPL", amount_fiat=10.0, commission=0.05, fx_fee=0.20)
    assert result["is_acceptable"] is False
    assert result["total_friction_percent"] == 0.025

def test_kelly_criterion_calculation():
    from src.services.risk_service import KellyCalculator
    calculator = KellyCalculator(fractional_kelly=0.25)
    
    # p=0.6, b=1 (even money) -> Full Kelly = 0.6 - 0.4 = 0.2. Fractional (0.25x) = 0.05
    size = calculator.calculate_size(win_prob=0.6, win_loss_ratio=1.0)
    assert size == pytest.approx(0.05)
    
    # Case with ruin risk: p=0.4, b=1 -> Kelly < 0 -> Size should be 0
    size = calculator.calculate_size(win_prob=0.4, win_loss_ratio=1.0)
    assert size == 0.0

