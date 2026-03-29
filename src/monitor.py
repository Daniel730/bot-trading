import asyncio
import logging
import yfinance as yf
from datetime import datetime
from src.config import settings
from src.services.data_service import data_service
from src.services.arbitrage_service import arbitrage_service
from src.models.persistence import PersistenceManager
from src.agents.orchestrator import orchestrator
from src.services.shadow_service import shadow_service
from src.services.notification_service import notification_service
from src.services.audit_service import audit_service
from src.services.brokerage_service import BrokerageService

# Disable yfinance cache to prevent SQLite locks in Docker
yf.set_tz_cache_location("/tmp/yf_cache")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ArbitrageMonitor:
    def __init__(self, mode: str = "live"):
        self.persistence = PersistenceManager(settings.DB_PATH)
        self.brokerage = BrokerageService()
        self.mode = mode
        self.active_pairs = []

    async def initialize_pairs(self):
        """Initializes cointegration metrics."""
        pairs_to_init = settings.CRYPTO_TEST_PAIRS if settings.DEV_MODE else settings.ARBITRAGE_PAIRS
        logger.info(f"Initializing pairs in {'DEV' if settings.DEV_MODE else 'PROD'} mode...")
        
        for pair_config in pairs_to_init:
            ticker_a, ticker_b = pair_config['ticker_a'], pair_config['ticker_b']
            try:
                hist_data = data_service.get_historical_data([ticker_a, ticker_b])
                col_a = next((c for c in hist_data.columns if ticker_a in c), None)
                col_b = next((c for c in hist_data.columns if ticker_b in c), None)
                
                if not col_a or not col_b: continue

                is_coint, p_val, hedge = arbitrage_service.check_cointegration(hist_data[col_a], hist_data[col_b])
                if is_coint:
                    pair_id = self.persistence.save_pair(ticker_a, ticker_b, hedge)
                    metrics = arbitrage_service.get_spread_metrics(hist_data[col_a], hist_data[col_b], hedge)
                    self.active_pairs.append({
                        "id": pair_id, "ticker_a": ticker_a, "ticker_b": ticker_b,
                        "hedge_ratio": hedge, "mean": metrics['mean'], "std": metrics['std']
                    })
                    logger.info(f"Pair {ticker_a}/{ticker_b} added.")
            except Exception as e:
                logger.error(f"Error {ticker_a}/{ticker_b}: {e}")

    async def run(self):
        # Improved Connectivity check
        connected = self.brokerage.test_connection()
        if not connected and self.mode == "live":
            logger.error("!!! FAILED TO CONNECT TO T212. Check API Key and Permissions !!!")
        else:
            logger.info("Successfully connected to Trading 212 API.")

        await self.initialize_pairs()
        await notification_service.start_listening()
        
        while True:
            if not settings.DEV_MODE:
                now = datetime.now()
                if now.weekday() >= 5 or now.hour < 14: # Simplistic check
                    await asyncio.sleep(60); continue

            for pair in self.active_pairs:
                try:
                    current_z = 2.5 
                    signal_id = self.persistence.log_signal(pair['id'], current_z)
                    state = await orchestrator.ainvoke({"signal_context": {"ticker_a": pair['ticker_a'], "ticker_b": pair['ticker_b'], "z_score": current_z}})
                    audit_service.log_thought_process(signal_id, state)
                    
                    if state['final_confidence'] > 0.5:
                        if await notification_service.request_approval(f"Pair: {pair['ticker_a']}/{pair['ticker_b']} (Z: {current_z})"):
                            if self.mode == "shadow":
                                await shadow_service.execute_simulated_trade(pair['id'], "Long-Short", 1, 1, 100, 50)
                            else:
                                logger.info(f"LIVE: Trading {pair['ticker_a']}/{pair['ticker_b']}")
                                self.brokerage.place_market_order(pair['ticker_a'], 1.0, "BUY")
                                self.brokerage.place_market_order(pair['ticker_b'], 1.0, "SELL")
                except Exception as e:
                    logger.error(f"Loop error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    monitor = ArbitrageMonitor(mode="live")
    asyncio.run(monitor.run())
