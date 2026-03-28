import sqlite3
import logging
import time
import uuid
import pandas as pd
from datetime import datetime
from src.config import DB_PATH
from src.services.brokerage_service import BrokerageService
from src.services.data_service import DataService
from src.services.notification_service import NotificationService
from src.services.arbitrage_service import ArbitrageService
from src.models.arbitrage_models import ArbitragePair, ArbitrageStatus, TriggerType, SignalRecord
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
        self.refresh_interval = 12  # Seconds (Strict 5 req/min compliance)
        self.windows = [30, 60, 90]
        self.market_was_open = None

    def startup_re_sync(self):
        """
        T021: Implement Virtual Pie state reconciliation and startup re-sync.
        """
        logger.info("Initializing Strategic Arbitrage Engine...")
        
        try:
            # 1. Sync Quantities from Brokerage
            positions = self.brokerage.fetch_positions()
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

            conn.commit()
            conn.close()
            logger.info("Startup re-sync complete.")
        except Exception as e:
            logger.error(f"Startup re-sync failed: {e}", exc_info=True)

    def monitor_loop(self):
        """
        T012 & T013: Core monitoring and signal generation.
        """
        while True:
            try:
                is_open = self.data.is_market_open()
                
                # Market Status Notifications
                if self.market_was_open is not None and is_open != self.market_was_open:
                    import asyncio
                    status_text = "🏛️ NYSE Market is now OPEN 🟢" if is_open else "🏛️ NYSE Market is now CLOSED 🔴"
                    asyncio.run(self.notifier.send_message(status_text))
                
                self.market_was_open = is_open

                if not is_open:
                    logger.info("Market is closed. Sleeping...")
                    time.sleep(60)
                    continue

                self.process_pairs()
                
                time.sleep(self.refresh_interval)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                time.sleep(self.refresh_interval)

    def process_pairs(self):
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
            # For real-time Z-score, we need historical spread + current spread
            # To avoid fetching 180d every 12s, we should ideally cache historical spreads.
            # For now, let's fetch daily data and append current price.
            
            df_a = self.data.get_historical_data(t_a, period="120d")
            df_b = self.data.get_historical_data(t_b, period="120d")
            
            price_a = current_prices.get(t_a)
            price_b = current_prices.get(t_b)
            
            if price_a and price_b:
                # Calculate multi-window Z-scores
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
                # Using 60d window as primary trigger for now
                primary_z = z_60
                cursor.execute("UPDATE arbitrage_pairs SET last_z_score = ? WHERE id = ?", (primary_z, p_id))
                
                if status == ArbitrageStatus.MONITORING and abs(primary_z) > 2.5:
                    sig_id = self.create_signal(p_id, primary_z, TriggerType.ENTRY, cursor)
                    if sig_id:
                        self.trigger_ai_validation(sig_id, t_a, t_b, primary_z)
                elif status == ArbitrageStatus.ACTIVE_TRADE and abs(primary_z) < 0.5:
                    sig_id = self.create_signal(p_id, primary_z, TriggerType.EXIT, cursor)
                    if sig_id:
                        self.trigger_ai_validation(sig_id, t_a, t_b, primary_z)

        conn.commit()
        conn.close()

    def create_signal(self, pair_id: str, z_score: float, trigger: TriggerType, cursor: sqlite3.Cursor) -> Optional[str]:
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
               (id, pair_id, timestamp, z_score, trigger_type) 
               VALUES (?, ?, ?, ?, ?)""",
            (sig_id, pair_id, datetime.utcnow().isoformat(), z_score, trigger)
        )
        logger.info(f"SIGNAL | {trigger} | Pair: {pair_id} | Z: {z_score:.2f} | ID: {sig_id}")
        return sig_id

    def trigger_ai_validation(self, signal_id: str, ticker_a: str, ticker_b: str, z_score: float):
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
            # Calling Gemini CLI asynchronously
            subprocess.Popen(["gemini", prompt], start_new_session=True)
            logger.info(f"AUDIT | Gemini CLI process spawned for {signal_id}")
        except Exception as e:
            logger.error(f"AUDIT | Failed to trigger Gemini CLI: {e}")

    def run(self):
        self.startup_re_sync()
        self.monitor_loop()

if __name__ == "__main__":
    bot = StrategicArbitrageBot(demo=True)
    bot.run()
