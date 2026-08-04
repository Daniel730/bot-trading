from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.brokerage_service import BrokerageService


def _open_gate_patches():
    """Broker opens require non-shadow + LIVE_CAPITAL_DANGER + capital halt clear."""
    return (
        patch("src.services.brokerage_service.settings.PAPER_TRADING", False),
        patch("src.services.brokerage_service.settings.LIVE_CAPITAL_DANGER", True),
        patch(
            "src.services.capital_halt_service.enforce_capital_halt_or_raise_state",
            new=AsyncMock(return_value={"halt": False, "reason": None, "details": {}}),
        ),
    )


@pytest.mark.asyncio
async def test_brokerage_service_places_alpaca_market_order():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        service = BrokerageService("LEGACY")
    service.provider.place_market_order = AsyncMock(
        return_value={"status": "success", "order_id": "123"}
    )

    p1, p2, p3 = _open_gate_patches()
    with p1, p2, p3:
        result = await service.place_market_order("KO", 1.0, "BUY")

    assert result["status"] == "success"
    assert result["venue"] == "ALPACA"
    service.provider.place_market_order.assert_awaited_once_with("KO", 1.0, "BUY", None, None)


@pytest.mark.asyncio
async def test_brokerage_service_blocks_open_in_shadow_paper():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        service = BrokerageService()
    service.provider.place_market_order = AsyncMock(
        return_value={"status": "success", "order_id": "should-not-fire"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", True):
        result = await service.place_market_order("KO", 1.0, "BUY")

    assert result["status"] == "error"
    assert "PAPER_TRADING" in result["message"]
    service.provider.place_market_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_brokerage_service_gets_alpaca_portfolio():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        service = BrokerageService()
    service.provider.get_portfolio = MagicMock(return_value=[{"ticker": "KO", "quantity": 10.0}])

    result = await service.get_portfolio()

    assert len(result) == 1
    assert result[0]["ticker"] == "KO"
