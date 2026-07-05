from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.brokerage_service import BrokerageService
from src.services.notification_service import NotificationService


def _brokerage_service() -> BrokerageService:
    with patch("src.services.brokerage_service.AlpacaProvider"):
        return BrokerageService()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_result",
    [
        {"status": "success", "order_id": "submitted-order"},
        {
            "status": "unknown",
            "requires_reconciliation": True,
            "client_order_id": "cid-budget-unknown",
        },
    ],
)
async def test_budget_updates_only_after_confirmed_fill(provider_result):
    svc = _brokerage_service()
    svc.provider.place_value_order = AsyncMock(return_value=dict(provider_result))

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False), patch(
        "src.services.budget_service.budget_service.update_used_budget"
    ) as mock_update:
        result = await svc.place_value_order(
            "MSFT", 500.0, "BUY", client_order_id="cid-budget-unknown"
        )

    assert result["venue"] == "ALPACA"
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_fill_updates_budget_once():
    svc = _brokerage_service()
    svc.provider.place_value_order = AsyncMock(
        return_value={
            "status": "filled",
            "order_id": "filled-order",
            "filled_notional": "487.25",
        }
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False), patch(
        "src.services.budget_service.budget_service.update_used_budget"
    ) as mock_update:
        result = await svc.place_value_order("MSFT", 500.0, "BUY")

    assert result["venue"] == "ALPACA"
    mock_update.assert_called_once_with("ALPACA", 487.25)


@pytest.mark.asyncio
async def test_invest_command_does_not_update_budget_on_submit_success():
    service = NotificationService.__new__(NotificationService)
    service.chat_id = "12345"
    service.request_approval = AsyncMock(return_value=True)
    service.send_message = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.username = "operator"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = ["100", "of", "AAPL", "confirm"]

    brokerage = MagicMock()
    brokerage.get_account_cash = AsyncMock(return_value=1_000.0)
    brokerage.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "submitted-order"}
    )

    with patch("src.services.notification_service.settings.PAPER_TRADING", False), patch(
        "src.services.notification_service.settings.LIVE_CAPITAL_DANGER", True
    ), patch("src.services.brokerage_service.BrokerageService", return_value=brokerage), patch(
        "src.services.budget_service.budget_service.get_effective_cash",
        return_value=1_000.0,
    ), patch(
        "src.services.budget_service.budget_service.update_used_budget"
    ) as mock_update:
        await service._handle_invest(update, context)

    brokerage.place_value_order.assert_awaited_once_with("AAPL", 100.0, "BUY")
    mock_update.assert_not_called()
