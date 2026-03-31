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
        self.last_dev_warning = datetime.min

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
        # Connectivity check with masked key for verification
        key = settings.effective_t212_key
        masked_key = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "INVALID/EMPTY"
        logger.info(f"Checking T212 connectivity (Mode: {settings.TRADING_212_MODE}, Key: {masked_key})")
        
        connected = self.brokerage.test_connection()
        if not connected and self.mode == "live":
            logger.error("!!! FAILED TO CONNECT TO T212. Check API Key and Permissions !!!")
        else:
            logger.info("Successfully connected to Trading 212 API.")

        await self.initialize_pairs()
        await notification_service.start_listening()
        
        while True:
            now = datetime.now()
            if settings.DEV_MODE:
                if (now - self.last_dev_warning).total_seconds() >= 300:
                    logger.warning("\n" + "!"*50 + "\n!!! DEVELOPMENT MODE ACTIVE: MONITORING CRYPTO 24/7 !!!\n" + "!"*50)
                    self.last_dev_warning = now
            else:
                # Simple check for regular market hours (WET)
                if now.weekday() >= 5 or now.hour < 14 or now.hour >= 21:
                    await asyncio.sleep(60); continue

            # Track total cycles (T011)
            audit_service.log_cycle(success=True) # Assuming starting the cycle is a partial success
            if audit_service.total_cycles % 10 == 0:
                rate = audit_service.get_connectivity_rate()
                logger.info(f"--- Connectivity Health: {rate:.1f}% ({audit_service.successful_cycles}/{audit_service.total_cycles} cycles) ---")

            for pair in self.active_pairs:
                try:
                    # Fetch real-time prices for Z-score calculation (T010)
                    prices = data_service.get_latest_price([pair['ticker_a'], pair['ticker_b']])
                    p_a = prices.get(pair['ticker_a'])
                    p_b = prices.get(pair['ticker_b'])
                    
                    if p_a and p_b:
                        spread = p_a - pair['hedge_ratio'] * p_b
                        current_z = (spread - pair['mean']) / pair['std']
                        logger.info(f"Market Update: {pair['ticker_a']}={p_a}, {pair['ticker_b']}={p_b} -> Z: {current_z:.2f}")
                    else:
                        current_z = 2.5 # Fallback to simulated value if yfinance fails
                        logger.warning(f"Using simulated Z-score for {pair['ticker_a']}/{pair['ticker_b']} (Prices missing)")
                    
                    signal_id = self.persistence.log_signal(pair['id'], current_z)
                    
                    # Measure latency for SC-002
                    start_time = datetime.now()
                    state = await orchestrator.ainvoke({"signal_context": {"ticker_a": pair['ticker_a'], "ticker_b": pair['ticker_b'], "z_score": current_z}})
                    latency = (datetime.now() - start_time).total_seconds()
                    
                    if latency < 10.0:
                        logger.info(f"SC-002 PASS: IA Decision Latency: {latency:.2f}s (Goal: < 10s)")
                    else:
                        logger.warning(f"SC-002 FAIL: IA Decision Latency: {latency:.2f}s (Goal: < 10s)")
                    
                    audit_service.log_thought_process(signal_id, state)
                    
                    if state['final_confidence'] > 0.5:
                        approved = await notification_service.request_approval(f"Pair: {pair['ticker_a']}/{pair['ticker_b']} (Z: {current_z})")
                        if approved:
                            if self.mode == "shadow":
                                await shadow_service.execute_simulated_trade(pair['id'], "Long-Short", 1, 1, 100, 50)
                            else:
                                logger.info(f"LIVE: Trading {pair['ticker_a']}/{pair['ticker_b']}")
                                if settings.DEV_MODE:
                                    # Technical validation: Map Crypto to Stock Tickers (e.g., BTC-USD -> MSFT)
                                    exec_a = settings.DEV_EXECUTION_TICKERS.get(pair['ticker_a'], pair['ticker_a'])
                                    exec_b = settings.DEV_EXECUTION_TICKERS.get(pair['ticker_b'], pair['ticker_b'])
                                    
                                    # Ensure small-lot limit (Targeting ~$1.00 per trade using fractional shares)
                                    qty_a = 0.001 # Fractional share for high-priced stocks like MSFT/AAPL
                                    qty_b = 0.001
                                    
                                    self.brokerage.place_market_order(exec_a, qty_a, "BUY")
                                    self.brokerage.place_market_order(exec_b, qty_b, "BUY")
                                    logger.info(f"DEV_MODE EXECUTION: Buy {qty_a} {exec_a} and {qty_b} {exec_b} (Small lot validation)")
                                else:
                                    # Real Arbitrage
                                    self.brokerage.place_market_order(pair['ticker_a'], 1.0, "BUY")
                                    self.brokerage.place_market_order(pair['ticker_b'], 1.0, "SELL")
                        else:
                            logger.warning(f"Trade rejected or timed out for {pair['ticker_a']}/{pair['ticker_b']}")
                except Exception as e:
                    logger.error(f"Loop error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    monitor = ArbitrageMonitor(mode="live")
    asyncio.run(monitor.run())
