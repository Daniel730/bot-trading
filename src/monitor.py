import sqlite3
import logging
import time
import uuid
import subprocess
from datetime import datetime
from src.config import DB_PATH
from src.services.brokerage_service import BrokerageService
from src.services.data_service import DataService
from src.services.notification_service import NotificationService
from src.services.arbitrage_service import ArbitrageService
from src.prompts import FINANCIAL_RISK_ANALYST_PROMPT
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, demo: bool = True):
        self.brokerage = BrokerageService(demo=demo)
        self.data = DataService()
        self.notifier = NotificationService()
        self.arbitrage = ArbitrageService()
        self.db_path = DB_PATH
        self.refresh_interval = 15 # Seconds
        self.market_was_open = None

    def startup_sync(self):
        """
        Re-sync current quantities and update pair parameters from historical data.
        """
        logger.info("Starting startup sequence...")
        
        # 1. Sync Portfolio
        try:
            portfolio = self.brokerage.fetch_portfolio()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE virtual_pie SET current_quantity = 0.0")
            for position in portfolio:
                cursor.execute("UPDATE virtual_pie SET current_quantity = ? WHERE ticker = ?",
                             (position.get("quantity"), position.get("ticker")))
            conn.commit()
            logger.info("Portfolio re-synced.")
        except Exception as e:
            logger.error(f"Portfolio sync failed: {e}")

        # 2. Update Cointegration Parameters
        try:
            cursor.execute("SELECT id, asset_a, asset_b FROM trading_pairs")
            pairs = cursor.fetchall()
            for pair_id, asset_a, asset_b in pairs:
                logger.info(f"Updating parameters for {pair_id}...")
                df_a = self.data.get_historical_data(asset_a, period="90d")
                df_b = self.data.get_historical_data(asset_b, period="90d")
                
                # Align data
                combined = pd.DataFrame({'asset_a': df_a['Close'], 'asset_b': df_b['Close']}).dropna()
                params = self.arbitrage.update_pair_parameters(combined)
                
                cursor.execute("""
                    UPDATE trading_pairs 
                    SET hedge_ratio = ?, mean_spread = ?, std_spread = ? 
                    WHERE id = ?
                """, (params['hedge_ratio'], params['mean_spread'], params['std_spread'], pair_id))
            conn.commit()
            conn.close()
            logger.info("Pair parameters updated.")
        except Exception as e:
            logger.error(f"Parameter update failed: {e}")
            if 'conn' in locals(): conn.close()

        self.notifier.send_message("🚀 Bot initialized and ready.")

    def monitor_once(self):
        """
        Single monitoring pass.
        """
        is_open = self.data.is_market_open()
        
        # T024: Market Open/Closed notifications
        if self.market_was_open is not None and is_open != self.market_was_open:
            status = "OPEN 🟢" if is_open else "CLOSED 🔴"
            self.notifier.send_message(f"🏛️ *Market Status:* {status}")
            logger.info(f"Market status changed to {status}")
            
        self.market_was_open = is_open

        if not is_open:
            return False

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, asset_a, asset_b, hedge_ratio, mean_spread, std_spread FROM trading_pairs")
            pairs = cursor.fetchall()
            
            # Fetch all unique tickers
            tickers = set()
            for p in pairs:
                tickers.add(p[1])
                tickers.add(p[2])
            
            prices = self.data.get_current_prices(list(tickers))
            
            triggered_signals = []
            
            for pair_id, asset_a, asset_b, hedge, mean, std in pairs:
                price_a = prices.get(asset_a)
                price_b = prices.get(asset_b)
                
                if price_a and price_b:
                    spread = self.arbitrage.calculate_spread(price_a, price_b, hedge)
                    z_score = self.arbitrage.calculate_z_score(spread, mean, std)
                    
                    logger.info(f"Pair: {pair_id} | Z-Score: {z_score:.2f}")
                    
                    # Update last Z-score in DB
                    cursor.execute("UPDATE trading_pairs SET last_z_score = ? WHERE id = ?", (z_score, pair_id))
                    
                    # Signal Trigger (|Z| > 2.0)
                    if abs(z_score) > 2.0:
                        signal_id = self.trigger_signal(pair_id, z_score, conn)
                        if signal_id:
                            triggered_signals.append((signal_id, pair_id, z_score))
            
            conn.commit()
            conn.close()
            
            # Trigger AI validation outside the DB transaction
            for signal_id, pair_id, z_score in triggered_signals:
                self.trigger_ai_validation(signal_id, pair_id, z_score)
            
        except Exception as e:
            logger.error(f"Error during monitoring pass: {e}")
            if 'conn' in locals(): conn.close()
            
        return True

    def trigger_signal(self, pair_id: str, z_score: float, conn: sqlite3.Connection) -> Optional[str]:
        """
        Creates a new signal in the DB. Returns signal_id if created, else None.
        """
        signal_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        cursor = conn.cursor()
        # Check if we already have a pending signal for this pair to avoid spam
        cursor.execute("SELECT id FROM signals WHERE pair_id = ? AND status IN ('PENDING_AI', 'PENDING_USER_CONFIRM')", (pair_id,))
        if cursor.fetchone():
            return None

        cursor.execute("""
            INSERT INTO signals (id, timestamp, pair_id, z_score, status)
            VALUES (?, ?, ?, ?, ?)
        """, (signal_id, timestamp, pair_id, z_score, 'PENDING_AI'))
        
        logger.info(f"⚠️ SIGNAL TRIGGERED: {pair_id} | Z={z_score:.2f}")
        return signal_id

    def trigger_ai_validation(self, signal_id: str, pair_id: str, z_score: float):
        """
        Calls Gemini CLI to validate the signal using the Financial Risk Analyst prompt.
        """
        instruction = f"{FINANCIAL_RISK_ANALYST_PROMPT}\n\nSignal ID: {signal_id}\nPair: {pair_id}\nZ-Score: {z_score:.2f}"
        
        logger.info(f"Triggering AI validation for signal {signal_id}...")
        
        try:
            # Call Gemini CLI in the background
            # The 'gemini' command will receive the prompt and use MCP tools
            subprocess.Popen(["gemini", instruction], start_new_session=True)
            logger.info(f"Gemini CLI process started for signal {signal_id}")
        except Exception as e:
            logger.error(f"Failed to trigger Gemini CLI: {e}")

    def run(self):
        """
        Continuous monitoring loop.
        """
        # We need pandas here for the startup_sync
        import pandas as pd
        self.startup_sync()
        
        while True:
            market_active = self.monitor_once()
            
            if not market_active:
                # Sleep for 5 minutes if market is closed to save resources
                logger.info("Market is closed. Sleeping for 5 minutes...")
                time.sleep(300)
            else:
                time.sleep(self.refresh_interval)

if __name__ == "__main__":
    bot = TradingBot(demo=True)
    bot.run()
