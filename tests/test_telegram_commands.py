import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.notification_service import NotificationService
from src.config import settings

@pytest.fixture
def telegram_update():
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.username = "testuser"
    update.message.reply_text = AsyncMock()
    
    context = MagicMock()
    context.args = []
    
    return update, context

@pytest.fixture
def notification_service():
    with patch("src.services.notification_service.settings") as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = "dummy_token"
        mock_settings.TELEGRAM_CHAT_ID = "12345"
        # Avoid full initialization of the ApplicationBuilder for unit tests
        with patch("src.services.notification_service.ApplicationBuilder"):
            service = NotificationService()
            service.chat_id = "12345"
            service._telegram_enabled = True
            service.request_approval = AsyncMock(return_value=True)
            service.send_message = AsyncMock()
            return service

@pytest.mark.asyncio
async def test_unauthorized_user_blocked(notification_service, telegram_update):
    update, context = telegram_update
    update.effective_user.id = 99999 # Not the configured chat_id "12345"
    
    await notification_service._handle_invest(update, context)
    
    update.message.reply_text.assert_called_with("⛔ Unauthorized.")
    notification_service.send_message.assert_called_once()
    assert "UNAUTHORIZED /invest ATTEMPT" in notification_service.send_message.call_args[0][0]

@pytest.mark.asyncio
async def test_ambiguous_ticker_rejected(notification_service, telegram_update):
    update, context = telegram_update
    context.args = ["10", "of", "AA@PL", "confirm"]
    
    await notification_service._handle_invest(update, context)
    update.message.reply_text.assert_called_with("⛔ Ambiguous or malformed ticker symbol.")

@pytest.mark.asyncio
async def test_huge_value_rejected(notification_service, telegram_update):
    update, context = telegram_update
    context.args = ["100000", "of", "AAPL", "confirm"]
    
    await notification_service._handle_invest(update, context)
    update.message.reply_text.assert_called_with("⛔ Amount must be between $0.01 and $10,000.")

@pytest.mark.asyncio
async def test_missing_confirm_rejected(notification_service, telegram_update):
    update, context = telegram_update
    context.args = ["10", "of", "AAPL"] # Missing 'confirm'
    
    await notification_service._handle_invest(update, context)
    assert "Usage: /invest [amount] of [ticker] confirm" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
@patch("src.services.notification_service.settings")
async def test_live_mode_safety_guard(mock_settings, notification_service, telegram_update):
    update, context = telegram_update
    context.args = ["10", "of", "AAPL", "confirm"]
    
    mock_settings.PAPER_TRADING = False
    mock_settings.LIVE_CAPITAL_DANGER = False
    
    await notification_service._handle_invest(update, context)
    assert "Trading commands are disabled by default in live mode" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
@patch("src.services.notification_service.settings")
@patch("src.services.notification_service.budget_service")
@patch("src.services.notification_service.BrokerageService")
async def test_budget_reservation_and_approval(mock_brokerage_cls, mock_budget_service, mock_settings, notification_service, telegram_update):
    update, context = telegram_update
    context.args = ["100", "of", "AAPL", "confirm"]
    
    mock_settings.PAPER_TRADING = False
    mock_settings.LIVE_CAPITAL_DANGER = True
    
    mock_brokerage = AsyncMock()
    mock_brokerage_cls.return_value = mock_brokerage
    mock_brokerage.get_account_cash.return_value = 1000.0
    mock_brokerage.place_value_order.return_value = {"status": "success"}
    
    # 1. Budget insufficient scenario
    mock_budget_service.get_effective_cash.return_value = 50.0 # Less than requested 100
    await notification_service._handle_invest(update, context)
    assert "Insufficient effective cash" in update.message.reply_text.call_args[0][0]
    
    # 2. Budget sufficient scenario
    mock_budget_service.get_effective_cash.return_value = 500.0
    notification_service.request_approval.return_value = True # User approves
    
    await notification_service._handle_invest(update, context)
    
    # Check that manual approval was forced (trade_value bypassed)
    notification_service.request_approval.assert_called_with(
        "/invest command: BUY $100.00 of AAPL", trade_value=100.0, force_manual=True
    )
    
    # Check that budget was updated
    mock_budget_service.update_used_budget.assert_called_with("ALPACA", 100.0)
    
    # Check brokerage was called
    mock_brokerage.place_value_order.assert_called_with("AAPL", 100.0, "BUY")
