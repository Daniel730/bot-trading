import sqlite3
import logging
import asyncio
import time
import uuid
import pandas as pd
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from src.config import DB_PATH, PAPER_TRADING, TELEGRAM_BOT_TOKEN
from src.services.brokerage_service import BrokerageService
from src.services.data_service import DataService
from src.services.notification_service import NotificationService
from src.services.arbitrage_service import ArbitrageService
from src.models.arbitrage_models import ArbitragePair, ArbitrageStatus, TriggerType, SignalRecord, OrderType
from typing import List, Dict, Any, Optional

# Detailed logging for IA audit
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("arbitrage_audit.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ArbitrageOrchestrator")

class StrategicArbitrageBot:
    def __init__(self, demo: bool = True):
        self.brokerage = BrokerageService(demo=demo)
        self.data = DataService()
        self.notifier = NotificationService()
        self.arbitrage = ArbitrageService()
        self.db_path = DB_PATH
        self.is_paper = PAPER_TRADING
        self.refresh_interval = 12  # Seconds (Strict 5 req/min compliance)
        self.windows = [30, 60, 90]
        self.market_was_open = None
        self.telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    async def startup_re_sync(self):
        """
        T021: Implement Virtual Pie state reconciliation and startup re-sync.
        """
        logger.info(f"Initializing Strategic Arbitrage Engine (PAPER_TRADING={self.is_paper})...")
        
        try:
            # 1. Sync Quantities from Brokerage
            try:
                positions = self.brokerage.fetch_positions()
            except Exception as e:
                logger.error(f"Failed to fetch portfolio from brokerage: {e}. Starting with zero positions.")
                positions = []

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Reset all current quantities to handle closed positions
            cursor.execute("UPDATE virtual_pie_assets SET current_quantity = 0.0")
            
            for pos in positions:
                ticker = pos.get("ticker", "").split("_")[0] # Strip suffix if present
                qty = float(pos.get("quantity", 0.0))
                cursor.execute(
                    "UPDATE virtual_pie_assets SET current_quantity = ? WHERE ticker = ?",
                    (qty, ticker)
                )
            
            # 2. Update Beta/Hedge Ratio for Monitoring Pairs
            cursor.execute("SELECT id, ticker_a, ticker_b FROM arbitrage_pairs")
            pairs = cursor.fetchall()
            
            for p_id, t_a, t_b in pairs:
                logger.info(f"Recalculating hedge ratio for {t_a}/{t_b}...")
                try:
                    df_a = self.data.get_historical_data(t_a, period="180d") # Get enough for 90d rolling
                    df_b = self.data.get_historical_data(t_b, period="180d")
                    
                    # Align data
                    combined = pd.DataFrame({'a': df_a['Close'], 'b': df_b['Close']}).dropna()
                    if not combined.empty:
                        beta = self.arbitrage.calculate_hedge_ratio(combined['a'], combined['b'])
                        cursor.execute(
                            "UPDATE arbitrage_pairs SET beta = ? WHERE id = ?",
                            (beta, p_id)
                        )
                        logger.info(f"New Beta for {t_a}/{t_b}: {beta:.4f}")
                    else:
                        logger.warning(f"Could not fetch historical data for {t_a} or {t_b}")
                except Exception as e:
                    logger.error(f"Failed to update beta for {t_a}/{t_b}: {e}")

            conn.commit()
            conn.close()
            logger.info("Startup re-sync complete.")
        except Exception as e:
            logger.error(f"Startup re-sync failed unexpectedly: {e}", exc_info=True)

    async def monitor_loop(self):
        """
        T012 & T013: Core monitoring and signal generation.
        """
        while True:
            try:
                is_open = self.data.is_market_open()
                
                # Market Status Notifications
                if self.market_was_open is not None and is_open != self.market_was_open:
                    status_text = "🏛️ NYSE Market is now OPEN 🟢" if is_open else "🏛️ NYSE Market is now CLOSED 🔴"
                    await self.notifier.send_message(status_text)
                
                self.market_was_open = is_open

                if not is_open:
                    logger.info("Market is closed. Sleeping...")
                    await asyncio.sleep(60)
                    continue

                await self.process_pairs()
                
                await asyncio.sleep(self.refresh_interval)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                await asyncio.sleep(self.refresh_interval)

    async def process_pairs(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, ticker_a, ticker_b, beta, status FROM arbitrage_pairs WHERE status != 'PAUSED'")
        pairs = cursor.fetchall()
        
        tickers = set()
        for p in pairs:
            tickers.add(p[1])
            tickers.add(p[2])
        
        current_prices = self.data.get_current_prices(list(tickers))
        
        for p_id, t_a, t_b, beta, status in pairs:
            df_a = self.data.get_historical_data(t_a, period="120d")
            df_b = self.data.get_historical_data(t_b, period="120d")
            
            price_a = current_prices.get(t_a)
            price_b = current_prices.get(t_b)
            
            if price_a and price_b:
                # Append current price to history for rolling calculation
                series_a = pd.concat([df_a['Close'], pd.Series([price_a])])
                series_b = pd.concat([df_b['Close'], pd.Series([price_b])])
                
                z_scores = self.arbitrage.get_multi_window_z_scores(series_a, series_b, beta, self.windows)
                
                # Log current state
                z_30 = z_scores.get(30, 0)
                z_60 = z_scores.get(60, 0)
                z_90 = z_scores.get(90, 0)
                
                logger.info(f"AUDIT | Pair: {t_a}/{t_b} | Z30: {z_30:.2f} | Z60: {z_60:.2f} | Z90: {z_90:.2f}")
                
                # Persist history
                for win, val in z_scores.items():
                    cursor.execute(
                        "INSERT INTO zscore_history (pair_id, timestamp, window, value) VALUES (?, ?, ?, ?)",
                        (p_id, datetime.utcnow().isoformat(), win, val)
                    )
                
                # Check for signals
                primary_z = z_60
                cursor.execute("UPDATE arbitrage_pairs SET last_z_score = ? WHERE id = ?", (primary_z, p_id))
                
                if status == ArbitrageStatus.MONITORING and abs(primary_z) > 2.5:
                    sig_id = self.create_signal(p_id, primary_z, TriggerType.ENTRY, price_a, price_b, cursor)
                    if sig_id:
                        await self.trigger_ai_validation(sig_id, t_a, t_b, primary_z)
                elif status == ArbitrageStatus.ACTIVE_TRADE and abs(primary_z) < 0.5:
                    sig_id = self.create_signal(p_id, primary_z, TriggerType.EXIT, price_a, price_b, cursor)
                    if sig_id:
                        await self.trigger_ai_validation(sig_id, t_a, t_b, primary_z)

        conn.commit()
        conn.close()

    def create_signal(self, pair_id: str, z_score: float, trigger: TriggerType, 
                      price_a: float, price_b: float, cursor: sqlite3.Cursor) -> Optional[str]:
        # Check if pending signal exists
        cursor.execute(
            "SELECT id FROM signal_records WHERE pair_id = ? AND ai_validation_status = 'PENDING'",
            (pair_id,)
        )
        if cursor.fetchone():
            return None

        sig_id = str(uuid.uuid4())
        cursor.execute(
            """INSERT INTO signal_records 
               (id, pair_id, timestamp, z_score, trigger_type, price_a, price_b) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sig_id, pair_id, datetime.utcnow().isoformat(), z_score, trigger, price_a, price_b)
        )
        logger.info(f"SIGNAL | {trigger} | Pair: {pair_id} | Z: {z_score:.2f} | ID: {sig_id}")
        return sig_id

    async def trigger_ai_validation(self, signal_id: str, ticker_a: str, ticker_b: str, z_score: float):
        """
        T016: Integrate Gemini CLI validation loop.
        """
        import subprocess
        
        # Fetch context
        news = self.data.get_news_context([ticker_a, ticker_b], limit=5)
        headlines = [n.get('title', '') for n in news]
        
        prompt = (
            f"As a Financial Risk Analyst, validate this arbitrage signal.\n"
            f"Signal ID: {signal_id}\n"
            f"Pair: {ticker_a}/{ticker_b}\n"
            f"Z-Score: {z_score:.2f}\n"
            f"News Headlines: {headlines}\n\n"
            f"Use the record_ai_decision tool to provide your GO/NO_GO decision and rationale."
        )
        
        logger.info(f"AUDIT | Triggering AI Validation for {signal_id}...")
        
        try:
            # Calling Gemini CLI asynchronously in non-interactive mode
            # --yolo ensures the agent can call record_ai_decision without manual intervention
            subprocess.Popen(["gemini", "--prompt", prompt, "--yolo"], start_new_session=True)
            logger.info(f"AUDIT | Gemini CLI process spawned for {signal_id}")
        except Exception as e:
            logger.error(f"AUDIT | Failed to trigger Gemini CLI: {e}")

    async def execute_rebalance(self, signal_id: str):
        """
        T023: Conditional execution logic (Live vs Paper).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Fetch signal and pair details
        cursor.execute(
            """SELECT sr.z_score, p.ticker_a, p.ticker_b, p.beta, p.id, sr.price_a, sr.price_b 
               FROM signal_records sr 
               JOIN arbitrage_pairs p ON sr.pair_id = p.id 
               WHERE sr.id = ?""",
            (signal_id,)
        )
        row = cursor.fetchone()
        if not row:
            logger.error(f"Signal {signal_id} not found for execution.")
            conn.close()
            return
            
        z_score, t_a, t_b, beta, p_id, sig_p_a, sig_p_b = row
        
        # Get current prices for the execution
        prices = self.data.get_current_prices([t_a, t_b])
        p_a = prices.get(t_a)
        p_b = prices.get(t_b)
        
        if not p_a or not p_b:
            logger.error(f"Missing price for {t_a} or {t_b}. Aborting rebalance.")
            conn.close()
            return

        # T030: Slippage check
        if sig_p_a and sig_p_b:
            drift_a = abs(p_a - sig_p_a) / sig_p_a
            drift_b = abs(p_b - sig_p_b) / sig_p_b
            
            if drift_a > SLIPPAGE_TOLERANCE or drift_b > SLIPPAGE_TOLERANCE:
                logger.warning(f"SLIPPAGE | Signal {signal_id} aborted. Drift A: {drift_a:.4%}, B: {drift_b:.4%}")
                await self.notifier.send_message(f"⚠️ *Slippage Abort* | {t_a}/{t_b}\nDrift too high (Tolerance: {SLIPPAGE_TOLERANCE:.2%})")
                conn.close()
                return

        # Calculate orders
        orders = self.arbitrage.calculate_rebalance_orders(t_a, t_b, beta, p_a, p_b, 1000.0, z_score)
        
        logger.info(f"EXECUTING | Paper={self.is_paper} | Signal: {signal_id} | Orders: {len(orders)}")
        
        executed_orders = []
        failed_orders = []
        
        for order in orders:
            ticker = order['ticker']
            qty = order['quantity']
            price = order['price']
            o_type = order['type']
            
            if self.is_paper:
                # T022: Simulated Ledger Tracking
                ledger_record, _ = self.arbitrage.calculate_paper_trade(ticker, qty, price, o_type, 10000.0)
                
                cursor.execute(
                    """INSERT INTO trade_ledger 
                       (id, timestamp, ticker, quantity, price, order_type, is_paper, status) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ledger_record['id'], ledger_record['timestamp'], ticker, qty, price, o_type.value, True, 'COMPLETED')
                )
                logger.info(f"PAPER TRADE | {o_type.value} {ticker} | Qty: {qty} | Price: {price}")
                await self.notifier.send_trade_notification(ticker, qty, True)
                executed_orders.append(order)
            else:
                # LIVE TRADING
                try:
                    result = self.brokerage.place_market_order(ticker, qty)
                    cursor.execute(
                        """INSERT INTO trade_ledger 
                           (id, timestamp, ticker, quantity, price, order_type, is_paper, status) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (str(uuid.uuid4()), datetime.utcnow().isoformat(), ticker, qty, price, o_type.value, False, 'COMPLETED')
                    )
                    logger.info(f"LIVE TRADE | {o_type.value} {ticker} | Result: {result.get('id')}")
                    await self.notifier.send_trade_notification(ticker, qty, True)
                    executed_orders.append(order)
                except Exception as e:
                    logger.error(f"LIVE TRADE FAILED | {ticker}: {e}")
                    await self.notifier.send_trade_notification(ticker, qty, False, error=str(e))
                    failed_orders.append(order)
                    
                    # T031: Circuit Breaker - If one leg fails, we MUST stop
                    break

        # T031: Handle partial failure
        if failed_orders and executed_orders:
            logger.critical(f"CIRCUIT BREAKER | Partial swap failure for pair {p_id}. Leg(s) {executed_orders} executed, but {failed_orders} failed.")
            cursor.execute("UPDATE arbitrage_pairs SET status = ? WHERE id = ?", (ArbitrageStatus.PAUSED.value, p_id))
            await self.notifier.send_message(f"🚨 *CRITICAL FAILURE* | {t_a}/{t_b}\nPartial swap executed. Pair PAUSED for manual intervention.")
        elif failed_orders:
            logger.error(f"EXECUTION FAILED | All orders failed for pair {p_id}. Pair status unchanged.")
        else:
            # Update Pair status only if everything succeeded
            new_status = ArbitrageStatus.ACTIVE_TRADE if z_score > 2.5 or z_score < -2.5 else ArbitrageStatus.MONITORING
            cursor.execute("UPDATE arbitrage_pairs SET status = ? WHERE id = ?", (new_status.value, p_id))
        
        conn.commit()
        conn.close()

    async def run(self):
        """
        Starts the monitoring loop and the Telegram bot listener concurrently.
        """
        # Add Handlers to Telegram App
        self.telegram_app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.telegram_app.add_handler(CommandHandler("status", self.status_command))
        
        await self.startup_re_sync()
        
        # Initialize Telegram App
        await self.telegram_app.initialize()
        await self.telegram_app.start()
        await self.telegram_app.updater.start_polling()
        
        logger.info("Strategic Arbitrage Bot is now RUNNING with Telegram listener.")
        
        try:
            # Run the monitoring loop
            await self.monitor_loop()
        finally:
            # Shutdown
            if self.telegram_app.updater:
                await self.telegram_app.updater.stop()
            await self.telegram_app.stop()
            await self.telegram_app.shutdown()

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handles approval/rejection button clicks from Telegram.
        """
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if data.startswith("approve_"):
            signal_id = data.replace("approve_", "")
            logger.info(f"USER | Approved signal {signal_id}. Executing...")
            await query.edit_message_text(text=f"{query.message.text}\n\n✅ *Approved. Executing trade...*", parse_mode="Markdown")
            await self.execute_rebalance(signal_id)
            
        elif data.startswith("reject_"):
            signal_id = data.replace("reject_", "")
            logger.info(f"USER | Rejected signal {signal_id}.")
            await query.edit_message_text(text=f"{query.message.text}\n\n❌ *Rejected by user.*", parse_mode="Markdown")
            # Update DB to REJECTED if needed
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE signal_records SET user_approval_status = 'REJECTED' WHERE id = ?", (signal_id,))
            conn.commit()
            conn.close()

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handles /status command.
        """
        status_text = "🤖 Strategic Arbitrage Bot Status: RUNNING\n"
        status_text += f"Mode: {'📝 PAPER' if self.is_paper else '💰 LIVE'}\n"
        status_text += f"Market: {'🟢 OPEN' if self.market_was_open else '🔴 CLOSED'}"
        await update.message.reply_text(status_text)

if __name__ == "__main__":
    bot = StrategicArbitrageBot(demo=True)
    asyncio.run(bot.run())
