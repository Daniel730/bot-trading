from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from src.config import settings
import asyncio
import logging
import re
import uuid


logger = logging.getLogger(__name__)
REDACTED_TELEGRAM_TOKEN = "<redacted-telegram-token>"
_TELEGRAM_BOT_URL_RE = re.compile(r"(api\.telegram\.org/bot)[^/\s]+")
_TELEGRAM_BOT_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}")
_TELEGRAM_LOG_REDACTION_LOGGERS = (
    __name__,
    "httpx",
    "httpcore",
    "telegram",
    "telegram.ext",
    "telegram.request",
)


def _redact_telegram_sensitive_text(value, token: str = "") -> str:
    text = str(value)
    token = str(token or "")
    if token:
        text = text.replace(token, REDACTED_TELEGRAM_TOKEN)
    text = _TELEGRAM_BOT_URL_RE.sub(r"\1" + REDACTED_TELEGRAM_TOKEN, text)
    return _TELEGRAM_BOT_TOKEN_RE.sub(REDACTED_TELEGRAM_TOKEN, text)


def _redact_logging_value(value):
    text = str(value)
    redacted = _redact_telegram_sensitive_text(text)
    return redacted if redacted != text else value


def _is_telegram_markdown_parse_error(error) -> bool:
    text = str(error).lower()
    return "can't parse entities" in text or "can't parse message text" in text


class TelegramTokenRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_logging_value(record.msg)
        if isinstance(record.args, dict):
            record.args = {
                key: _redact_logging_value(arg)
                for key, arg in record.args.items()
            }
        elif record.args:
            record.args = tuple(_redact_logging_value(arg) for arg in record.args)
        return True


_TELEGRAM_LOG_REDACTION_FILTER = TelegramTokenRedactionFilter()


def configure_telegram_log_redaction() -> None:
    for logger_name in _TELEGRAM_LOG_REDACTION_LOGGERS:
        logger = logging.getLogger(logger_name)
        if not any(
            isinstance(filter_, TelegramTokenRedactionFilter)
            for filter_ in logger.filters
        ):
            logger.addFilter(_TELEGRAM_LOG_REDACTION_FILTER)


class NotificationService:
    def __init__(self):
        configure_telegram_log_redaction()
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.pending_approvals = {}  # correlation_id -> asyncio.Future
        self.pending_approval_summaries = {}  # correlation_id -> trade summary text
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
            logger.warning(
                "TELEGRAM: Failed to initialize (%s). Telegram notifications disabled.",
                self._redact_sensitive_text(e),
            )

    def _redact_sensitive_text(self, value) -> str:
        return _redact_telegram_sensitive_text(value, self.token)

    async def _handle_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays macro economic summary."""
        try:
            from src.agents.macro_economic_agent import macro_economic_agent
            summary = await macro_economic_agent.get_macro_summary()
            message = macro_economic_agent.format_summary_for_telegram(summary)
            await update.message.reply_text(text=message, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {self._redact_sensitive_text(e)}")

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
            await update.message.reply_text(f"⚠️ Error: {self._redact_sensitive_text(e)}")

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
            await update.message.reply_text(f"⚠️ Error: {self._redact_sensitive_text(e)}")

    async def _handle_invest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Executes a value-based fractional order or schedules DCA: /invest [amount] of [ticker] confirm OR /invest schedule amount=X frequency=Y strategy=S"""
        try:
            # PATCH 2a: Validate sender is the configured operator.
            # Without this, any member of the Telegram chat (group chats, leaked tokens)
            # can place live market orders against the account.
            sender_user_id = str(update.effective_user.id)
            if sender_user_id != str(self.chat_id):
                await update.message.reply_text("⛔ Unauthorized.")
                await self.send_message(f"🚨 UNAUTHORIZED /invest ATTEMPT by user {sender_user_id} (@{update.effective_user.username})")
                import logging
                logging.getLogger("audit").critical(f"UNAUTHORIZED COMMAND: sender={sender_user_id} user=@{update.effective_user.username}")
                return

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
                # PATCH 2b: Reject non-positive or excessively large DCA amounts.
                if amount <= 0 or amount > 10_000:
                    await update.message.reply_text("⛔ Amount must be between $0.01 and $10,000.")
                    return
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

            if len(args) < 4 or args[1].lower() != "of" or args[3].lower() != "confirm":
                await update.message.reply_text("Usage: /invest [amount] of [ticker] confirm\nExample: /invest 10 of AAPL confirm")
                return
            
            amount = float(args[0])
            ticker = args[2].upper()

            # PATCH 2c: Reject non-positive or excessively large amounts.
            if amount <= 0 or amount > 10_000:
                await update.message.reply_text("⛔ Amount must be between $0.01 and $10,000.")
                return

            # Check ticker format
            if not ticker.isalnum() and "-" not in ticker:
                await update.message.reply_text("⛔ Ambiguous or malformed ticker symbol.")
                return

            import logging
            audit_logger = logging.getLogger("audit")

            # PATCH 2d: In paper mode, log the intent but do NOT hit the real broker.
            if settings.PAPER_TRADING:
                await update.message.reply_text(
                    f"📝 PAPER MODE: /invest ${amount:.2f} of {ticker} logged (no real order placed)."
                )
                audit_logger.info(f"AUDIT: /invest paper-logged. user={sender_user_id} ticker={ticker} amount={amount}")
                return

            if not getattr(settings, 'LIVE_CAPITAL_DANGER', False):
                await update.message.reply_text("⛔ Trading commands are disabled by default in live mode. (LIVE_CAPITAL_DANGER not true)")
                return

            from src.services.brokerage_service import BrokerageService
            from src.services.budget_service import budget_service
            brokerage = BrokerageService()

            actual_cash = await brokerage.get_account_cash()
            effective_cash = budget_service.get_effective_cash("ALPACA", actual_cash)
            if amount > effective_cash:
                await update.message.reply_text(f"⛔ Insufficient effective cash. Requested: ${amount:.2f}, Available: ${effective_cash:.2f}")
                audit_logger.warning(f"AUDIT: /invest rejected, insufficient budget. requested={amount} effective={effective_cash}")
                return

            # PATCH 2e: In live mode, require explicit approval before placing the order.
            trade_summary = f"/invest command: BUY ${amount:.2f} of {ticker}"
            approved = await self.request_approval(trade_summary, trade_value=amount, force_manual=True)
            if not approved:
                await update.message.reply_text(f"❌ Investment rejected by operator (or timed out).")
                audit_logger.info(f"AUDIT: /invest rejected by operator. ticker={ticker} amount={amount}")
                return
            
            audit_logger.info(f"AUDIT: /invest APPROVED. Executing BUY ${amount} of {ticker}...")
            await update.message.reply_text(f"⏳ Processing investment: ${amount:.2f} of {ticker}...")
            
            # Execute value-based order
            result = await brokerage.place_value_order(ticker, amount, "BUY")
            
            if result.get("status") == "error":
                await update.message.reply_text(f"❌ Failed: {result.get('message')}")
            else:
                await update.message.reply_text(f"✅ Order placed successfully.")
            
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {self._redact_sensitive_text(e)}")

    async def _handle_cash(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            from src.services.cash_management_service import cash_management_service
            from src.services.brokerage_service import BrokerageService
            brokerage = BrokerageService()
            
            cash = await brokerage.get_account_cash()
            sweep_ticker = cash_management_service.sweep_ticker
            
            portfolio = await brokerage.get_portfolio()
            sweep_pos = next((p for p in portfolio if p['ticker'] == brokerage._format_ticker(sweep_ticker)), None)
            
            sweep_value = 0.0
            if sweep_pos:
                qty = sweep_pos.get('quantity', 0.0)
                from src.services.data_service import data_service
                prices = await data_service.get_latest_price_async([sweep_ticker])
                price = prices.get(sweep_ticker, 0.0)
                sweep_value = qty * price

            message = "💰 *Cash Management Summary*\n\n"
            message += f"💵 *Free Cash*: ${cash:.2f}\n"
            message += f"🛡️ *{sweep_ticker} Sweep*: ${sweep_value:.2f}\n"
            message += f"📊 *Total Liquidity*: ${cash + sweep_value:.2f}\n"
            
            await update.message.reply_text(text=message, parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {self._redact_sensitive_text(e)}")

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
        
        sender_user_id = str(query.from_user.id)
        if sender_user_id != str(self.chat_id):
            await query.answer("⛔ Unauthorized.", show_alert=True)
            import logging
            logging.getLogger("audit").critical(f"UNAUTHORIZED CALLBACK: sender={sender_user_id} user=@{query.from_user.username}")
            return
            
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
            self.pending_approval_summaries.pop(correlation_id, None)
            if not future.done():
                future.set_result(action == "approve")
                try:
                    await query.edit_message_text(text=f"{query.message.text}\n\n✅ Resultado: {'APROVADO' if action == 'approve' else 'REJEITADO'}")
                except Exception as e:
                    logger.warning("TELEGRAM: Could not edit message: %s", self._redact_sensitive_text(e))

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
            try:
                from src.services.dashboard_service import dashboard_state
                await dashboard_state.add_message("BOT", message)
            except Exception as e:
                logger.warning("DASHBOARD ERROR (send_message fallback): %s", self._redact_sensitive_text(e))
            return
        try:
            # 1. Send to Telegram
            try:
                await self.app.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode="Markdown"
                )
            except Exception as e:
                if not _is_telegram_markdown_parse_error(e):
                    raise
                await self.app.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                )

            # 2. Send to Dashboard Terminal
            from src.services.dashboard_service import dashboard_state
            await dashboard_state.add_message("BOT", message)

        except Exception as e:
            logger.warning("TELEGRAM ERROR (send_message): %s", self._redact_sensitive_text(e))

    async def send_dashboard_login_approval(self, correlation_id: str, summary: str) -> bool:
        """Send an interactive dashboard-login approval request."""
        text = f"🔐 *Dashboard Login Approval*\n\n{summary}\n\nApprove this login?"
        try:
            from src.services.dashboard_service import dashboard_state
            await dashboard_state.add_message(
                "BOT",
                text,
                metadata={"correlation_id": correlation_id, "type": "dashboard_login_approval"},
            )
        except Exception as e:
            logger.warning("DASHBOARD ERROR (login approval): %s", self._redact_sensitive_text(e))

        if not self._telegram_enabled:
            print(f"[LOGIN APPROVAL] Telegram not configured. Challenge {correlation_id}: {summary}")
            return False

        keyboard = [
            [
                InlineKeyboardButton("Approve Login", callback_data=f"approve:{correlation_id}"),
                InlineKeyboardButton("Reject", callback_data=f"reject:{correlation_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return True
        except Exception as e:
            logger.warning("TELEGRAM ERROR (login approval): %s", self._redact_sensitive_text(e))
            return False

    async def _paper_notify(self, trade_summary: str) -> None:
        """Fire-and-forget notification for paper-mode auto-approvals.

        Failures here must never propagate to the caller -- paper trades
        must simulate regardless of Telegram or dashboard health (FR-002).
        """
        text = "Trade auto-approved\n" + trade_summary
        if self._telegram_enabled:
            try:
                await self.app.bot.send_message(chat_id=self.chat_id, text=text)
            except Exception as e:
                logger.warning(
                    "TELEGRAM (paper-notify): send failed, non-fatal: %s",
                    self._redact_sensitive_text(e),
                )
        else:
            print(f"[PAPER TRADE] {text}")
        try:
            from src.services.dashboard_service import dashboard_state
            await dashboard_state.add_message(
                "BOT", text, metadata={"type": "paper_auto_approved"}
            )
        except Exception as e:
            logger.warning(
                "DASHBOARD (paper-notify): add_message failed, non-fatal: %s",
                self._redact_sensitive_text(e),
            )

    def _schedule_paper_notify(self, trade_summary: str) -> None:
        notify = self._paper_notify

        async def runner():
            try:
                await notify(trade_summary)
            except Exception as e:
                logger.warning("PAPER notify failed, non-fatal: %s", self._redact_sensitive_text(e))
        asyncio.create_task(runner())

    async def request_approval(self, trade_summary: str, trade_value: float = None, force_manual: bool = False) -> bool:
        """Gate a trade on operator approval.

        In live mode: sends inline-button Telegram message and waits for
        the operator to click Approve/Reject (5 min timeout -> False).

        In paper mode (settings.PAPER_TRADING=True): returns True in
        under 100ms and dispatches a fire-and-forget notification so the
        operator still has visibility (spec FR-001..FR-003).
        """
        # Paper-mode fast path.
        if settings.PAPER_TRADING:
            self._schedule_paper_notify(trade_summary)
            return True

        if not self._telegram_enabled:
            # Live mode must fail-closed when human approval is required but unavailable.
            logger.warning(
                "[APPROVAL] Telegram approval channel unavailable. Pausing live trading for manual review: %s",
                trade_summary,
            )
            try:
                from src.services.dashboard_service import dashboard_service
                from src.services.persistence_service import persistence_service
                await dashboard_service.update("PAUSED_REQUIRES_MANUAL_REVIEW", "Telegram approval channel unavailable; live execution paused.")
                await persistence_service.set_system_state("operational_status", "PAUSED_REQUIRES_MANUAL_REVIEW")
            except Exception as pause_exc:
                logger.warning("[APPROVAL] Failed to publish pause state: %s", self._redact_sensitive_text(pause_exc))
            return False

        # Threshold auto-approval fast path. In live mode this is only allowed
        # after the operator's approval channel has been configured.
        if not force_manual and trade_value is not None and trade_value <= settings.APPROVAL_THRESHOLD:
            self._schedule_paper_notify(f"Auto-approved below threshold:\n{trade_summary}")
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
        self.pending_approval_summaries[correlation_id] = trade_summary

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
            self.pending_approval_summaries.pop(correlation_id, None)
            logger.warning("TELEGRAM: Timeout waiting for approval %s", correlation_id)
            return False
        except Exception as e:
            self.pending_approvals.pop(correlation_id, None)
            self.pending_approval_summaries.pop(correlation_id, None)
            logger.warning("TELEGRAM ERROR: %s", self._redact_sensitive_text(e))
            try:
                from src.services.dashboard_service import dashboard_service
                from src.services.persistence_service import persistence_service
                await dashboard_service.update("PAUSED_REQUIRES_MANUAL_REVIEW", "Approval workflow failed; live execution paused.")
                await persistence_service.set_system_state("operational_status", "PAUSED_REQUIRES_MANUAL_REVIEW")
            except Exception as pause_exc:
                logger.warning(
                    "[APPROVAL] Failed to publish pause state after approval error: %s",
                    self._redact_sensitive_text(pause_exc),
                )
            return False

    def list_pending_approvals(self) -> list:
        """Return open trade-approval CIDs for dashboard/agent pollers."""
        out = []
        for cid, future in list(self.pending_approvals.items()):
            if future.done():
                continue
            out.append({
                "correlation_id": cid,
                "summary": self.pending_approval_summaries.get(cid, ""),
                "type": "approval",
            })
        return out

    def resolve_pending_approval(self, correlation_id: str, approved: bool) -> dict:
        """Resolve a pending approval future. Used by dashboard / agent APIs."""
        cid = str(correlation_id or "").strip()
        future = self.pending_approvals.pop(cid, None)
        self.pending_approval_summaries.pop(cid, None)
        if future is None:
            return {"status": "error", "message": "Invalid or expired correlation ID"}
        if not future.done():
            future.set_result(bool(approved))
        return {
            "status": "success",
            "message": "Approval processed" if approved else "Rejection processed",
            "correlation_id": cid,
            "approved": bool(approved),
        }

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
            result = self.resolve_pending_approval(cid, approved=True)
            if result.get("status") == "success":
                await self.send_message(f"✅ Dashboard Approval received for {cid}")
            else:
                print(f"TERMINAL: Approval failed. CID '{cid}' not found in {list(self.pending_approvals.keys())}")
            return result
        if command.startswith("/reject"):
            parts = command.split()
            cid = parts[1] if len(parts) > 1 else (metadata.get("correlation_id") if metadata else None)
            result = self.resolve_pending_approval(cid, approved=False)
            if result.get("status") == "success":
                await self.send_message(f"❌ Dashboard Rejection received for {cid}")
            return result
        
        elif command == "/status":
            from src.services.dashboard_service import dashboard_service
            await self.send_message(
                f"Current Status: {dashboard_service.dashboard_state.stage}\n"
                f"Details: {dashboard_service.dashboard_state.details}"
            )
            return {"status": "success", "message": "Status sent"}

        elif command.startswith("/set_threshold"):
            parts = command.split()
            if len(parts) > 1:
                try:
                    val = float(parts[1])
                    settings.APPROVAL_THRESHOLD = val
                    from src.config import save_settings_override
                    save_settings_override({"APPROVAL_THRESHOLD": val})
                    await self.send_message(f"✅ Auto-trade threshold updated to {val} EUR")
                    return {"status": "success", "message": f"Threshold set to {val}"}
                except ValueError:
                    return {"status": "error", "message": "Invalid value"}
            return {"status": "error", "message": "Missing value"}

        elif command == "/exposure":
            if settings.PAPER_TRADING:
                await self.send_message("Portfolio is currently empty.")
                return {"status": "success", "message": "Exposure report sent"}
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
