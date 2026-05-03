import pytest
from decimal import Decimal
from src.services.risk_service import RiskService
from src.services.trade_math import build_pair_legs, cap_pair_notional, estimate_pair_profit
from src.config import settings
from unittest.mock import MagicMock, patch

@pytest.fixture
def risk_service():
    return RiskService()

def test_kelly_calculation(risk_service):
    # win_prob = 0.6, win_loss = 1.0 -> kelly = (0.6*1 - 0.4)/1 = 0.2
    # with fractional_kelly = 0.25 (default) -> 0.2 * 0.25 = 0.05 (5%)
    size = risk_service.kelly_calculator.calculate_size(0.6, 1.0)
    assert size == pytest.approx(0.05)

def test_validate_trade_sizing(risk_service):
    # Total portfolio = $100,000
    # Kelly fraction = 5% (from 0.6 win prob and 0.25 fractional kelly)
    # Expected size = $5,000
    # Max allocation = 5% ($5,000) from .env
    # Result should be $5,000

    res = risk_service.validate_trade(
        ticker="AAPL_MSFT",
        total_portfolio_cash=100000.0,
        amount_fiat=100000.0,
        win_prob=0.6,
        win_loss_ratio=1.0
    )

    assert res["is_acceptable"] is True
    assert res["kelly_fraction"] == pytest.approx(0.05)
    assert res["final_amount"] == pytest.approx(5000.0, abs=0.1)

def test_validate_trade_allocation_cap(risk_service):
    # Override settings for this test to ensure 15%
    with patch('src.services.risk_service.settings') as mock_settings:
        mock_settings.MAX_ALLOCATION_PERCENTAGE = 15.0
        mock_settings.KELLY_FRACTION = 0.25
        mock_settings.MIN_TRADE_VALUE = 1.0

        # Kelly = (0.7*1 - 0.3)/1 = 0.4
        # Fractional Kelly = 1.0 (override calculator)
        risk_service.kelly_calculator.fractional_kelly = 1.0

        # Total portfolio = $100,000
        # Kelly fraction = 40% -> $40,000
        # Max allocation = 15% -> $15,000
        # Result should be capped at $15,000

        res = risk_service.validate_trade(
            ticker="AAPL_MSFT",
            total_portfolio_cash=100000.0,
            amount_fiat=100000.0,
            win_prob=0.7,
            win_loss_ratio=1.0
        )

        assert res["final_amount"] == pytest.approx(15000.0)

def test_friction_rejection(risk_service):
    # Small trade $10.0
    # Friction $0.50 (5%)
    # Max friction 1.5%
    # Should be rejected

    res = risk_service.fee_analyzer.check_fees("AAPL", 10.0, flat_spread=0.5)
    assert res["is_acceptable"] is False
    assert "exceeds limit" in res["rejection_reason"]

def test_pair_leg_sizing_splits_gross_notional_by_hedge_ratio():
    legs = build_pair_legs(
        price_a=100.0,
        price_b=50.0,
        hedge_ratio=2.0,
        gross_notional=1000.0,
        direction="Short-Long",
    )

    assert legs.side_a == "SELL"
    assert legs.side_b == "BUY"
    assert legs.quantity_a == pytest.approx(5.0)
    assert legs.quantity_b == pytest.approx(10.0)
    assert legs.notional_a == pytest.approx(500.0)
    assert legs.notional_b == pytest.approx(500.0)
    assert legs.gross_notional == pytest.approx(1000.0)


def test_pair_notional_is_capped_by_available_budget():
    assert cap_pair_notional(1500.0, 900.0, min_trade_value=1.0) == pytest.approx(900.0)
    assert cap_pair_notional(1500.0, 0.50, min_trade_value=1.0) == 0.0


def test_expected_profit_uses_spread_capture_and_full_pair_friction():
    legs = build_pair_legs(
        price_a=150.0,
        price_b=150.0,
        hedge_ratio=1.0,
        gross_notional=1000.0,
        direction="Short-Long",
    )
    preview = estimate_pair_profit(
        quantity_a=legs.quantity_a,
        gross_notional=legs.gross_notional,
        spread=0.30,
        z_score=3.0,
        innovation_variance=0.01,
        friction_pct=0.001,
        take_profit_zscore=0.5,
        stop_loss_zscore=3.5,
    )

    assert preview.gross_profit == pytest.approx(0.833333, rel=1e-5)
    assert preview.friction_usd == pytest.approx(1.0)
    assert preview.net_profit < 0
