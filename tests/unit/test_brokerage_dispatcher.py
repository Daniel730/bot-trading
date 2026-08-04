from unittest.mock import AsyncMock, patch

import pytest

from src.services.brokerage_service import BrokerageService


def _service() -> BrokerageService:
    with patch("src.services.brokerage_service.AlpacaProvider"):
        return BrokerageService()


def _open_gate_patches():
    return (
        patch("src.services.brokerage_service.settings.PAPER_TRADING", False),
        patch("src.services.brokerage_service.settings.LIVE_CAPITAL_DANGER", True),
        patch(
            "src.services.capital_halt_service.enforce_capital_halt_or_raise_state",
            new=AsyncMock(return_value={"halt": False, "reason": None, "details": {}}),
        ),
    )


@pytest.mark.asyncio
async def test_crypto_value_orders_route_to_alpaca_provider():
    svc = _service()
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "alpaca_crypto_order"}
    )

    p1, p2, p3 = _open_gate_patches()
    with p1, p2, p3:
        result = await svc.place_value_order("ETH-USD", 100.0, "BUY")

    assert result["order_id"] == "alpaca_crypto_order"
    assert result["venue"] == "ALPACA"
    svc.provider.place_value_order.assert_awaited_once_with("ETH-USD", 100.0, "BUY", None, None)


@pytest.mark.asyncio
async def test_equity_value_orders_route_to_alpaca_provider():
    svc = _service()
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "alpaca_order"}
    )

    p1, p2, p3 = _open_gate_patches()
    with p1, p2, p3:
        result = await svc.place_value_order("MSFT", 500.0, "BUY")

    assert result["order_id"] == "alpaca_order"
    assert result["venue"] == "ALPACA"
    svc.provider.place_value_order.assert_awaited_once_with("MSFT", 500.0, "BUY", None, None)


@pytest.mark.asyncio
async def test_f018_live_submit_success_updates_budget():
    svc = _service()
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "alpaca_order"}
    )

    p1, p2, p3 = _open_gate_patches()
    with p1, p2, p3, patch(
        "src.services.budget_service.budget_service.update_used_budget"
    ) as mock_budget:
        result = await svc.place_value_order("MSFT", 500.0, "BUY")

    assert result["venue"] == "ALPACA"
    mock_budget.assert_called_once_with("ALPACA", 500.0)


@pytest.mark.asyncio
async def test_live_error_does_not_update_budget():
    svc = _service()
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "error", "message": "broker rejected"}
    )

    p1, p2, p3 = _open_gate_patches()
    with p1, p2, p3, patch(
        "src.services.budget_service.budget_service.update_used_budget"
    ) as mock_budget:
        result = await svc.place_value_order("MSFT", 500.0, "BUY")

    assert result["venue"] == "ALPACA"
    mock_budget.assert_not_called()
