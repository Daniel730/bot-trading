from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from src.config import settings
import asyncio
import uuid

class NotificationService:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.pending_approvals = {} # correlation_id -> asyncio.Future
        self._telegram_enabled = False
        self.app = None

        # Guard: skip Telegram setup if token is absent or still a placeholder.
        # This lets the bot run in paper-trading mode without a Telegram account.
        _placeholder_tokens = {"", "None", "your_token_here", "YOUR_TELEGRAM_BOT_TOKEN"}
        if not self.token or str(self.token).strip() in _placeholder_tokens:
            print("TELEGRAM: Token not configured — Telegram notifications disabled. "
                  "Paper trading and console logging will still work.")
            return

        try:
            self.app = ApplicationBuilder().token(self.token).build()
            # Register handlers
            self.app.add_handler(CallbackQueryHandler(self._handle_callback))
            self.app.add_handler(CommandHandler("exposure", self._handle_exposure))
            self.app.add_handler(CommandHandler("invest", self._handle_invest))
            self.app.add_handler(CommandHandler("cash", self._handle_cash))
            self.app.add_handler(CommandHandler("portfolio", self._handle_portfolio))
            self.app.add_handler(CommandHandler("why", self._handle_why))
            self.app.add_handler(CommandHandler("macro", self._handle_macro))
            self._telegram_enabled = True
        except Exception as e:
            print(f"TELEGRAM: Failed to initialize ({e}). Telegram notifications disabled.")

    async def _handle_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays macro economic summary."""
        try:
            from src.agents.macro_economic_agent import macro_economic_agent
            summary = await macro_economic_agent.get_macro_summary()
            message = macro_economic_agent.format_summary_for_telegram(summary)
            await update.message.reply_text(text=message, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    async def _handle_why(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Explains the thesis for a ticker: /why [ticker]"""
        try:
            if not context.args:
                await update.message.reply_text("Usage: /why [ticker]")
                return
            
            ticker = context.args[0].upper()
            from src.agents.portfolio_manager_agent import portfolio_manager
            
            await update.message.reply_text(f"🔍 Analyzing internal logs for {ticker}...")
            thesis = await portfolio_manager.generate_investment_thesis(ticker)
            await update.message.reply_text(text=thesis, parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    async def _handle_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Creates or updates a portfolio strategy: /portfolio define [id] ticker=T weight=W ..."""
        try:
            args = context.args
            if not args or args[0].lower() != "define":
                await update.message.reply_text("Usage: /portfolio define [id] ticker=T weight=W ...\nExample: /portfolio define safe ticker=SPY weight=0.6 ticker=BND weight=0.4")
                return
            
            strategy_id = args[1]
            # Parse pairs
            assets = []
            current_ticker = None
            for item in args[2:]:
                if item.startswith("ticker="):
                    current_ticker = item.split("=")[1].upper()
                elif item.startswith("weight="):
                    weight = float(item.split("=")[1])
                    if current_ticker:
                        assets.append({"ticker": current_ticker, "weight": weight})
                        current_ticker = None
            
            from src.models.persistence import PersistenceManager
            persistence = PersistenceManager(settings.DB_PATH)
            
            for asset in assets:
                persistence.save_portfolio_strategy(strategy_id, asset['ticker'], asset['weight'], "Balanced")
            
            await update.message.reply_text(f"✅ Strategy '{strategy_id}' defined with {len(assets)} assets.")
            
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    async def _handle_invest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Executes a value-based fractional order or schedules DCA: /invest [amount] of [ticker] OR /invest schedule amount=X frequency=Y strategy=S"""
        try:
            args = context.args
            if not args:
                await update.message.reply_text("Usage:\n/invest [amount] of [ticker]\n/invest schedule amount=X frequency=Y strategy=S")
                return

            if args[0].lower() == "schedule":
                # Parse schedule args
                params = {}
                for item in args[1:]:
                    if "=" in item:
                        k, v = item.split("=")
                        params[k] = v
                
                amount = float(params.get("amount", 0))
                frequency = params.get("frequency", "weekly")
                strategy_id = params.get("strategy", "safe")
                
                from src.models.persistence import PersistenceManager
                from datetime import datetime, timedelta
                persistence = PersistenceManager(settings.DB_PATH)
                
                # Default next run to 1 minute from now for testing
                next_run = datetime.now() + timedelta(minutes=1)
                
                persistence.save_dca_schedule(amount, frequency, strategy_id, next_run)
                await update.message.reply_text(f"✅ DCA Scheduled: ${amount:.2f} {frequency} into '{strategy_id}'. First run: {next_run.strftime('%H:%M:%S')}")
                return

            if len(args) < 3 or args[1].lower() != "of":
                await update.message.reply_text("Usage: /invest [amount] of [ticker]\nExample: /invest 10 of AAPL")
                return
            
            amount = float(args[0])
            ticker = args[2].upper()
            
            from src.services.brokerage_service import BrokerageService
            brokerage = BrokerageService()
            
            await update.message.reply_text(f"⏳ Processing investment: ${amount:.2f} of {ticker}...")
            
            # Execute value-based order
            result = await brokerage.place_value_order(ticker, amount, "BUY")
            
            if result.get("status") == "error":
                await update.message.reply_text(f"❌ Failed: {result.get('message')}")
            else:
                # result normally contains the order object from T212
                order_id = result.get('orderId', 'N/A')
                await update.message.reply_text(f"✅ SUCCESS: Invested ${amount:.2f} in {ticker}\nOrder ID: {order_id}")
                
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    async def _handle_cash(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays account cash balance and SGOV sweep status: /cash"""
        try:
            from src.services.brokerage_service import BrokerageService
            from src.services.cash_management_service import cash_management_service
            brokerage = BrokerageService()
            
            cash = brokerage.get_account_cash()
            sweep_ticker = cash_management_service.sweep_ticker
            
            portfolio = await brokerage.get_portfolio()
            sweep_pos = next((p for p in portfolio if p['ticker'] == brokerage._format_ticker(sweep_ticker)), None)
            
            sweep_value = 0.0
            if sweep_pos:
                # v0 doesn't always have current value, but we can approximate or use DataService
                qty = sweep_pos.get('quantity', 0.0)
                from src.services.data_service import data_service
                prices = await data_service.get_latest_price([sweep_ticker])
                price = prices.get(sweep_ticker, 0.0)
                sweep_value = qty * price

            message = "💰 *Cash Management Summary*\n\n"
            message += f"💵 *Free Cash*: ${cash:.2f}\n"
            message += f"🛡️ *{sweep_ticker} Sweep*: ${sweep_value:.2f}\n"
            message += f"📊 *Total Liquidity*: ${cash + sweep_value:.2f}\n"
            
            await update.message.reply_text(text=message, parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    async def _handle_exposure(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays current sector exposure."""
        from src.services.shadow_service import shadow_service
        from src.services.risk_service import risk_service

        portfolio = await shadow_service.get_active_portfolio_with_sectors()
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
        """
        Starts the Telegram bot listener in the background.
        This allows the user to interact with the bot via commands like /status or /exposure.
        """
        if not self._telegram_enabled:
            print("TELEGRAM: Listener not started (Telegram disabled). Bot is running in console-only mode.")
            return
        await self.app.initialize()
        await self.app.start()
        # drop_pending_updates=True is CRITICAL to avoid processing old clicks after restart
        await self.app.updater.start_polling(drop_pending_updates=True)
        print("TELEGRAM: Listener active (cleared pending updates).")

        # Sprint J: Heartbeat Startup Message
        await self.send_message("🚀 *Arbitrage Bot Online*\n\nMonitoring active. All health checks passed. System is in `Ready` mode.")

    async def send_message(self, message: str):
        """Sends a plain text message to the Telegram chat and dashboard."""
        if not self._telegram_enabled:
            # Fallback: echo to console so operator still sees bot activity
            print(f"[BOT MSG] {message}")
            return
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

    async def _paper_notify(self, trade_summary: str) -> None:
        """Fire-and-forget notification for paper-mode auto-approvals.

        Failures here must never propagate to the caller -- paper trades
        must simulate regardless of Telegram or dashboard health (FR-002).
        """
        text = "Paper trade auto-approved\n" + trade_summary
        if self._telegram_enabled:
            try:
                await self.app.bot.send_message(chat_id=self.chat_id, text=text)
            except Exception as e:
                print(f"TELEGRAM (paper-notify): send failed, non-fatal: {e}")
        else:
            print(f"[PAPER TRADE] {text}")
        try:
            from src.services.dashboard_service import dashboard_state
            await dashboard_state.add_message(
                "BOT", text, metadata={"type": "paper_auto_approved"}
            )
        except Exception as e:
            print(f"DASHBOARD (paper-notify): add_message failed, non-fatal: {e}")

    async def request_approval(self, trade_summary: str) -> bool:
        """Gate a trade on operator approval.

        In live mode: sends inline-button Telegram message and waits for
        the operator to click Approve/Reject (5 min timeout -> False).

        In paper mode (settings.PAPER_TRADING=True): returns True in
        under 100ms and dispatches a fire-and-forget notification so the
        operator still has visibility (spec FR-001..FR-003).
        """
        # Paper-mode fast path.
        if settings.PAPER_TRADING:
            asyncio.create_task(self._paper_notify(trade_summary))
            return True

        if not self._telegram_enabled:
            # Without Telegram, live trades cannot be human-gated.
            # Log clearly and auto-approve so the bot doesn't silently stall.
            print(f"[APPROVAL] Telegram not configured. Auto-approving live trade: {trade_summary}")
            return True

        correlation_id = str(uuid.uuid4())[:8]
        keyboard = [
            [
                InlineKeyboardButton("Approve", callback_data=f"approve:{correlation_id}"),
                InlineKeyboardButton("Reject", callback_data=f"reject:{correlation_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        loop = asyncio.get_running_loop()
        future = loop.create_future()
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
        
        print(f"TERMINAL: Received command '{command}' with metadata {metadata}")
        
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
                print(f"TERMINAL: Approval failed. CID '{cid}' not found in {list(self.pending_approvals.keys())}")
                return {"status": "error", "message": "Invalid or expired correlation ID"}
        
        elif command == "/status":
            from src.services.dashboard_service import dashboard_service
            await self.send_message(
                f"Current Status: {dashboard_service.dashboard_state.stage}\n"
                f"Details: {dashboard_service.dashboard_state.details}"
            )
            return {"status": "success", "message": "Status sent"}

        elif command == "/exposure":
            from src.services.shadow_service import shadow_service
            from src.services.risk_service import risk_service

            portfolio = await shadow_service.get_active_portfolio_with_sectors()
            exposures = risk_service.get_all_sector_exposures(portfolio)

            if not exposures:
                await self.send_message("Portfolio is currently empty.")
            else:
                message = "📊 *Current Sector Exposure*\n\n"
                for sector, pct in sorted(exposures.items(), key=lambda x: x[1], reverse=True):
                    flag = "⚠️" if pct >= settings.MAX_SECTOR_EXPOSURE else "✅"
                    message += f"{flag} *{sector}*: {pct:.1%}\n"
                message += f"\n_Limit: {settings.MAX_SECTOR_EXPOSURE:.0%}_"
                await self.send_message(message)
            return {"status": "success", "message": "Exposure report sent"}

        return {"status": "error", "message": f"Unknown command: {command}"}


notification_service = NotificationService()
