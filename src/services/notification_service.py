from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes
from src.config import settings
import asyncio
import uuid

class NotificationService:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.pending_approvals = {} # correlation_id -> asyncio.Future
        self.app = ApplicationBuilder().token(self.token).build()
        
        # Register callback handler
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        
        # Always answer to stop the loading spinner, even if query is old
        try:
            await query.answer()
        except Exception:
            pass
        
        if not query.data or ":" not in query.data:
            return

        data = query.data.split(":")
        action = data[0]
        correlation_id = data[1]
        
        if correlation_id in self.pending_approvals:
            future = self.pending_approvals.pop(correlation_id)
            if not future.done():
                future.set_result(action == "approve")
                try:
                    await query.edit_message_text(text=f"{query.message.text}\n\n✅ Resultado: {'APROVADO' if action == 'approve' else 'REJEITADO'}")
                except Exception as e:
                    print(f"TELEGRAM: Could not edit message: {e}")

    async def start_listening(self):
        """Starts the Telegram bot listener in the background."""
        await self.app.initialize()
        await self.app.start()
        # drop_pending_updates=True is CRITICAL to avoid processing old clicks after restart
        await self.app.updater.start_polling(drop_pending_updates=True)
        print("TELEGRAM: Listener active (cleared pending updates).")

    async def request_approval(self, trade_summary: str) -> bool:
        """
        Sends message and WAITS for the user to click a button.
        """
        correlation_id = str(uuid.uuid4())[:8]
        keyboard = [
            [
                InlineKeyboardButton("Approve", callback_data=f"approve:{correlation_id}"),
                InlineKeyboardButton("Reject", callback_data=f"reject:{correlation_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        future = asyncio.get_event_loop().create_future()
        self.pending_approvals[correlation_id] = future
        
        try:
            await self.app.bot.send_message(
                chat_id=self.chat_id, 
                text=f"🚨 APPROVAL REQUIRED\n{trade_summary}", 
                reply_markup=reply_markup
            )
            
            # Wait for user response (max 5 minutes)
            return await asyncio.wait_for(future, timeout=300)
        except asyncio.TimeoutError:
            self.pending_approvals.pop(correlation_id, None)
            print(f"TELEGRAM: Timeout waiting for approval {correlation_id}")
            return False
        except Exception as e:
            print(f"TELEGRAM ERROR: {e}")
            return False

notification_service = NotificationService()
