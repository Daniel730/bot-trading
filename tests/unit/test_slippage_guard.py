import pytest

from src.services.risk_service import RiskService


def test_friction_rejects_when_estimated_cost_exceeds_limit():
    risk = RiskService()

    result = risk.calculate_friction(100.0, flat_spread=2.0)

    assert result["is_acceptable"] is False
    assert result["friction_pct"] == pytest.approx(0.02)


def test_friction_accepts_when_estimated_cost_is_inside_limit():
    risk = RiskService()

    result = risk.calculate_friction(1000.0, flat_spread=5.0)

    assert result["is_acceptable"] is True
    assert result["friction_pct"] == pytest.approx(0.005)
