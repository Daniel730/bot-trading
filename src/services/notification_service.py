import asyncio
import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.bot = Bot(token=self.bot_token)

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Sends a standard Telegram message asynchronously.
        """
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_trade_notification(self, ticker: str, quantity: float, success: bool, error: str = None) -> bool:
        """
        Sends a notification about a trade execution outcome.
        """
        action = "BUY" if quantity > 0 else "SELL"
        status = "✅ SUCCESS" if success else "❌ FAILED"
        
        text = (
            f"💼 *Trade Execution: {status}*\n"
            f"Ticker: `{ticker}`\n"
            f"Action: `{action}`\n"
            f"Quantity: `{abs(quantity):.6f}`\n"
        )
        
        if error:
            text += f"\n⚠️ *Error:* `{error}`"
            
        return await self.send_message(text)

    async def send_confirmation_request(self, signal_id: str, pair: str, z_score: float, rationale: str) -> bool:
        """
        Sends a message with inline buttons for manual confirmation.
        """
        text = (
            f"🎯 *Signal Detected: {pair}*\n"
            f"Z-Score: `{z_score:.2f}`\n\n"
            f"💡 *AI Analysis:*\n{rationale}\n\n"
            f"Do you want to proceed with the rebalance?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{signal_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{signal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            logger.info(f"Confirmation request sent for signal {signal_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send confirmation request: {e}")
            return False
            
    async def send_performance_report(self, sharpe_ratio: float, drawdown: float) -> bool:
        """
        Sends a performance report (Sharpe Ratio, Drawdown).
        """
        text = (
            f"📊 *Performance Report*\n"
            f"Sharpe Ratio: `{sharpe_ratio:.2f}`\n"
            f"Max Drawdown: `{drawdown*100:.2f}%`"
        )
        return await self.send_message(text)
