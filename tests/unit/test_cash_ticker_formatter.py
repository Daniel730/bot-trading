from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.notification_service import NotificationService
from src.services.cash_management_service import CashManagementService
from src.services import cash_management_service as cash_module


@pytest.mark.asyncio
async def test_cash_command_uses_real_ticker_formatter(monkeypatch):
    service = NotificationService.__new__(NotificationService)
    update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    context = SimpleNamespace(args=[])

    monkeypatch.setattr("src.services.brokerage_service.BrokerageService.__init__", lambda self: None)
    monkeypatch.setattr(
        "src.services.brokerage_service.BrokerageService.get_account_cash",
        AsyncMock(return_value=25.0),
    )
    monkeypatch.setattr(
        "src.services.brokerage_service.BrokerageService.get_portfolio",
        AsyncMock(return_value=[{"ticker": "SGOV", "quantity": 2.0}]),
    )
    monkeypatch.setattr(
        "src.services.data_service.data_service.get_latest_price_async",
        AsyncMock(return_value={"SGOV": 100.0}),
    )

    await service._handle_cash(update, context)

    reply = update.message.reply_text.await_args.kwargs.get("text", "")
    assert "Cash Management Summary" in reply
    assert "Total Liquidity" in reply
    assert "$225.00" in reply


@pytest.mark.asyncio
async def test_cash_management_liquidate_uses_real_ticker_formatter(monkeypatch):
    service = CashManagementService.__new__(CashManagementService)
    service.sweep_ticker = "SGOV"
    service.persistence = SimpleNamespace(save_cash_sweep=MagicMock())

    monkeypatch.setattr(
        cash_module.brokerage_service,
        "get_portfolio",
        AsyncMock(return_value=[{"ticker": "SGOV", "quantity": 3.0, "averagePrice": 99.0}]),
    )
    monkeypatch.setattr(
        cash_module.brokerage_service,
        "execute_order",
        AsyncMock(return_value={"status": "success"}),
        raising=False,
    )
    monkeypatch.setattr(
        "src.services.data_service.data_service.get_latest_price_async",
        AsyncMock(return_value={"SGOV": 100.0}),
    )

    liquidated = await service.liquidate_for_trade(125.0)

    assert liquidated == 125.0
    cash_module.brokerage_service.execute_order.assert_awaited_once_with("SGOV", 125.0, side="sell")
    service.persistence.save_cash_sweep.assert_called_once_with("SWEEP_OUT", 125.0, "SGOV", 175.0)
