import pytest
from decimal import Decimal

from src.services.dashboard_service import dashboard_service


def test_weighted_wallet_plan_allocates_every_cent():
    recommendations = [
        {"ticker": "AAPL", "score": 3.0},
        {"ticker": "MSFT", "score": 1.0},
    ]

    plan = dashboard_service._build_weighted_wallet_plan(100.0, recommendations)

    assert plan[0][0] == "AAPL"
    assert plan[0][1] == Decimal("75")
    assert plan[1][0] == "MSFT"
    assert plan[1][1] == Decimal("25")
    assert sum(amount for _, amount in plan) == Decimal("100")


def test_weighted_wallet_plan_rejects_budget_too_small_for_candidates():
    with pytest.raises(ValueError):
        dashboard_service._build_weighted_wallet_plan(
            0.01,
            [{"ticker": "AAPL", "score": 1.0}, {"ticker": "MSFT", "score": 1.0}],
        )
