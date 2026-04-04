from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from src.config import settings
import asyncio
import uuid

class NotificationService:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.pending_approvals = {} # correlation_id -> asyncio.Future
        self.app = ApplicationBuilder().token(self.token).build()
        
        # Register handlers
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))
        self.app.add_handler(CommandHandler("exposure", self._handle_exposure))

    async def _handle_exposure(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays current sector exposure."""
        from src.services.shadow_service import shadow_service
        from src.services.risk_service import risk_service
        
        portfolio = shadow_service.get_active_portfolio_with_sectors()
        exposures = risk_service.get_all_sector_exposures(portfolio)
        
        if not exposures:
            await update.message.reply_text("Portfolio is currently empty.")
            return
            
        message = "📊 *Current Sector Exposure*\n\n"
        for sector, pct in sorted(exposures.items(), key=lambda x: x[1], reverse=True):
            status = "⚠️" if pct >= settings.MAX_SECTOR_EXPOSURE else "✅"
            message += f"{status} *{sector}*: {pct:.1%}\n"
            
        message += f"\n_Limit: {settings.MAX_SECTOR_EXPOSURE:.0%}_"
        await update.message.reply_text(text=message, parse_mode="Markdown")

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

    async def send_message(self, message: str):
        """Sends a plain text message to the Telegram chat and dashboard."""
        try:
            # 1. Send to Telegram
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            
            # 2. Send to Dashboard Terminal
            from src.services.dashboard_service import dashboard_state
            await dashboard_state.add_message("BOT", message)
            
        except Exception as e:
            print(f"TELEGRAM ERROR (send_message): {e}")

    async def request_approval(self, trade_summary: str) -> bool:
        """
        Sends message and WAITS for the user to click a button.
        Also sends to the dashboard terminal.
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
            text = f"🚨 APPROVAL REQUIRED\n{trade_summary}"
            
            # 1. Send to Telegram
            await self.app.bot.send_message(
                chat_id=self.chat_id, 
                text=text, 
                reply_markup=reply_markup
            )
            
            # 2. Send to Dashboard
            from src.services.dashboard_service import dashboard_state
            await dashboard_state.add_message("BOT", text, metadata={"correlation_id": correlation_id, "type": "approval"})

            # Wait for user response (max 5 minutes)
            return await asyncio.wait_for(future, timeout=300)
        except asyncio.TimeoutError:
            self.pending_approvals.pop(correlation_id, None)
            print(f"TELEGRAM: Timeout waiting for approval {correlation_id}")
            return False
        except Exception as e:
            print(f"TELEGRAM ERROR: {e}")
            return False

    async def handle_dashboard_command(self, command: str, metadata: dict = None):
        """Processes a command sent from the dashboard terminal."""
        from src.services.dashboard_service import dashboard_state
        from src.services.dashboard_service import dashboard_service
        
        # Log the user message to the terminal first
        await dashboard_state.add_message("USER", command)
        
        # Audit Log (Principle III)
        dashboard_service.persistence.log_event("INFO", "DASHBOARD_TERMINAL", f"User command: {command}", metadata)
        
        # Handle specific commands
        if command.startswith("/approve"):
            # Format: /approve correlation_id
            parts = command.split()
            cid = parts[1] if len(parts) > 1 else (metadata.get("correlation_id") if metadata else None)
            
            if cid in self.pending_approvals:
                future = self.pending_approvals.pop(cid)
                if not future.done():
                    future.set_result(True)
                    await self.send_message(f"✅ Dashboard Approval received for {cid}")
                return {"status": "success", "message": "Approval processed"}
            else:
                return {"status": "error", "message": "Invalid or expired correlation ID"}
        
        elif command == "/status":
            from src.services.dashboard_service import dashboard_service
            await self.send_message(f"Current Status: {dashboard_service.dashboard_state.stage}\nDetails: {dashboard_service.dashboard_state.details}")
            return {"status": "success", "message": "Status sent"}

        elif command == "/exposure":
            # We don't have an update object here, so we call the logic directly
            from src.services.shadow_service import shadow_service
            from src.services.risk_service import risk_service
            
            portfolio = shadow_service.get_active_portfolio_with_sectors()
            exposures = risk_service.get_all_sector_exposures(portfolio)
            
            if not exposures:
                await self.send_message("Portfolio is currently empty.")
            else:
                message = "📊 *Current Sector Exposure*\n\n"
                for sector, pct in sorted(exposures.items(), key=lambda x: x[1], reverse=True):
                    status = "⚠️" if pct >= settings.MAX_SECTOR_EXPOSURE else "✅"
                    message += f"{status} *{sector}*: {pct:.1%}\n"
                message += f"\n_Limit: {settings.MAX_SECTOR_EXPOSURE:.0%}_"
                await self.send_message(message)
            return {"status": "success", "message": "Exposure report sent"}

        return {"status": "error", "message": f"Unknown command: {command}"}

notification_service = NotificationService()
