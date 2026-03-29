import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from typing import Optional

class NotificationService:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.chat_id = TELEGRAM_CHAT_ID

    async def send_message(self, text: str, parse_mode: str = 'HTML'):
        """Send a basic text notification."""
        await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)

    async def send_approval_request(self, signal_id: str, ticker_a: str, ticker_b: str, z_score: float, ai_rationale: str):
        """Send an interactive approval request for a trade signal."""
        keyboard = [
            [
                InlineKeyboardButton("Approve ✅", callback_data=f"approve_{signal_id}"),
                InlineKeyboardButton("Reject ❌", callback_data=f"reject_{signal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"<b>🚨 Arbitrage Signal Detected</b>\n\n"
            f"Pair: {ticker_a} / {ticker_b}\n"
            f"Z-Score: {z_score:.2f}\n"
            f"AI Rationale: {ai_rationale}\n\n"
            f"Do you want to execute the rebalance?"
        )
        
        await self.bot.send_message(chat_id=self.chat_id, text=message, reply_markup=reply_markup, parse_mode='HTML')

    def start_bot(self):
        """Initializes the bot application and registers callback handlers."""
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            data = query.data
            signal_id = data.split("_")[1]
            
            if data.startswith("approve"):
                # Persist approval in SQLite
                self._update_approval_status(signal_id, "APPROVED")
                await query.edit_message_text(text=f"{query.message.text}\n\n<b>Status: APPROVED ✅</b>", parse_mode='HTML')
            elif data.startswith("reject"):
                self._update_approval_status(signal_id, "REJECTED")
                await query.edit_message_text(text=f"{query.message.text}\n\n<b>Status: REJECTED ❌</b>", parse_mode='HTML')

        application.add_handler(CallbackQueryHandler(button_callback))
        # This would normally run in the background (e.g. application.run_polling())
        return application

    def _update_approval_status(self, signal_id: str, status: str):
        """Update signal approval status in SQLite."""
        import sqlite3
        conn = sqlite3.connect("trading_bot.sqlite")
        cursor = conn.cursor()
        cursor.execute("UPDATE SignalRecord SET user_approval_status = ? WHERE id = ?", (status, signal_id))
        conn.commit()
        conn.close()
