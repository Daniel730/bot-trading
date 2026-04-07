import asyncio
import logging
import yfinance as yf
import pytz
from datetime import datetime
from src.config import settings
from src.services.data_service import data_service
from src.services.arbitrage_service import arbitrage_service
from src.services.persistence_service import persistence_service, OrderSide, OrderStatus
from src.services.redis_service import redis_service
from src.agents.orchestrator import orchestrator
from src.services.shadow_service import shadow_service
from src.services.notification_service import notification_service
from src.services.audit_service import audit_service
from src.services.risk_service import risk_service
from src.services.brokerage_service import BrokerageService
from src.services.agent_log_service import agent_logger
from src.services.dashboard_service import dashboard_service
import uuid

# Disable yfinance cache
yf.set_tz_cache_location("/tmp/yf_cache")

# Configure logging
def setup_logging():
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    return logging.getLogger(__name__)

logger = setup_logging()

class ArbitrageMonitor:
    def __init__(self, mode: str = "live"):
        self.brokerage = BrokerageService()
        self.mode = mode
        self.active_pairs = []
        self.active_signals = []
        self.last_dev_warning = datetime.min
        self.current_day = None
        self.daily_start_cash = 0.0
        self.daily_halted = False

    async def verify_entropy_baselines(self):
        """
        US1: Enforce mandatory startup check against Redis L2 entropy baselines.
        Refuses to boot if baselines are missing for any active pair when LIVE_CAPITAL_DANGER=True.
        """
        logger.info("VALIDATING L2 ENTROPY BASELINES (LIVE_CAPITAL_DANGER=True)...")
        missing_baselines = []
        for pair in settings.ARBITRAGE_PAIRS:
            ticker_a, ticker_b = pair['ticker_a'], pair['ticker_b']
            # Entropy service stores baselines as 'entropy_baseline:{ticker}'
            baseline_a = await redis_service.client.get(f"entropy_baseline:{ticker_a}")
            baseline_b = await redis_service.client.get(f"entropy_baseline:{ticker_b}")
            
            if not baseline_a: missing_baselines.append(ticker_a)
            if not baseline_b: missing_baselines.append(ticker_b)
            
        if missing_baselines:
            error_msg = f"CRITICAL: Missing L2 Entropy Baselines for: {list(set(missing_baselines))}. Refusing to boot in LIVE mode."
            logger.critical(error_msg)
            # Send alert before exiting
            await notification_service.send_message(error_msg)
            raise SystemExit(error_msg)
            
        logger.info("L2 ENTROPY BASELINES VALIDATED. Proceeding with Live Startup.")

    async def initialize_pairs(self):
        """Initializes cointegration metrics and Kalman filters."""
        if settings.LIVE_CAPITAL_DANGER:
            await self.verify_entropy_baselines()
            
        pairs_to_init = settings.ARBITRAGE_PAIRS
        logger.info(f"Initializing pairs in {'DEV' if settings.DEV_MODE else 'PROD'} mode...")
        
        for pair_config in pairs_to_init:
            ticker_a, ticker_b = pair_config['ticker_a'], pair_config['ticker_b']
            try:
                hist_data = data_service.get_historical_data([ticker_a, ticker_b])
                col_a = next((c for c in hist_data.columns if ticker_a in c), None)
                col_b = next((c for c in hist_data.columns if ticker_b in c), None)
                
                if not col_a or not col_b: continue

                is_coint, p_val, hedge = arbitrage_service.check_cointegration(hist_data[col_a], hist_data[col_b])
                
                pair_id = f"{ticker_a}_{ticker_b}"
                
                # Initialize Kalman filter (Warm Start from Redis)
                kf = await arbitrage_service.get_or_create_filter(
                    pair_id, 
                    delta=settings.KALMAN_DELTA, 
                    r=settings.KALMAN_R,
                    initial_state=[0.0, hedge]
                )

                metrics = arbitrage_service.get_spread_metrics(hist_data[col_a], hist_data[col_b], hedge)
                self.active_pairs.append({
                    "id": pair_id, "ticker_a": ticker_a, "ticker_b": ticker_b,
                    "hedge_ratio": hedge, "mean": metrics['mean'], "std": metrics['std'],
                    "is_cointegrated": is_coint
                })
                logger.info(f"Pair {ticker_a}/{ticker_b} initialized (Coint: {is_coint}).")
            except Exception as e:
                logger.error(f"Error initializing {ticker_a}/{ticker_b}: {e}")

    async def process_pair(self, pair: dict, latest_prices: dict):
        """Processes a single pair for signals and validation."""
        try:
            t_a, t_b = pair['ticker_a'], pair['ticker_b']
            if t_a not in latest_prices or t_b not in latest_prices:
                return
            
            price_a = latest_prices[t_a]
            price_b = latest_prices[t_b]

            # Feature 007: Kalman Filter Update
            kf = await arbitrage_service.get_or_create_filter(pair['id'])
            state_vec, innovation_var = kf.update(price_a, price_b)
            spread, z_score = kf.calculate_spread_and_zscore(price_a, price_b)
            
            # Persist Kalman state to Redis
            await arbitrage_service.save_filter_state(pair['id'], kf, z_score)

            # Signal Generation
            if abs(z_score) > 2.0:
                signal_id = str(uuid.uuid4())
                
                # Update Active Signals for Dashboard
                signal_entry = next((s for s in self.active_signals if s['ticker_a'] == t_a and s['ticker_b'] == t_b), None)
                if not signal_entry:
                    signal_entry = {"ticker_a": t_a, "ticker_b": t_b, "z_score": z_score, "status": "Analyzing"}
                    self.active_signals.append(signal_entry)
                
                # AI Validation
                signal_context = {
                    "ticker_a": t_a, "ticker_b": t_b,
                    "z_score": z_score, "dynamic_beta": state_vec[1],
                    "signal_id": signal_id
                }
                
                decision_state = await orchestrator.ainvoke({"signal_context": signal_context})
                await audit_service.log_thought_process(signal_id, decision_state)
                
                if decision_state['final_confidence'] > 0.5:
                    approved = await notification_service.request_approval(f"Opportunity in {t_a}/{t_b}. Z:{z_score:.2f}")
                    if approved:
                        direction = "Short-Long" if z_score > 0 else "Long-Short"
                        await self.execute_trade(pair, direction, price_a, price_b, signal_id)
            else:
                # Cleanup inactive signals
                self.active_signals = [s for s in self.active_signals if not (s['ticker_a'] == t_a and s['ticker_b'] == t_b)]

        except Exception as e:
            logger.error(f"Error processing pair {pair.get('ticker_a')}: {e}")

    async def execute_trade(self, pair, direction, price_a, price_b, signal_id):
        """Executes a trade and logs to PostgreSQL."""
        t_a, t_b = pair['ticker_a'], pair['ticker_b']
        
        # Sizing (Simplified for brevity)
        target_cash = 100.0 
        size_a = round(target_cash / price_a, 6)
        size_b = round(target_cash / price_b, 6)

        # Mock execution results
        order_id_a = str(uuid.uuid4())
        order_id_b = str(uuid.uuid4())

        # Log Leg A
        await persistence_service.log_trade({
            "order_id": order_id_a,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_a,
            "side": OrderSide.SELL if direction == "Short-Long" else OrderSide.BUY,
            "quantity": size_a,
            "price": price_a,
            "status": OrderStatus.COMPLETED
        })

        # Log Leg B
        await persistence_service.log_trade({
            "order_id": order_id_b,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_b,
            "side": OrderSide.BUY if direction == "Short-Long" else OrderSide.SELL,
            "quantity": size_b,
            "price": price_b,
            "status": OrderStatus.COMPLETED
        })
        
        logger.info(f"TRADE EXECUTED: {t_a}/{t_b} {direction}")

    async def run(self):
        # Initial Setup
        logger.info("Initializing Databases...")
        await asyncio.gather(
            persistence_service.init_db(),
            self.initialize_pairs()
        )
        
        try:
            while True:
                await dashboard_service.update_state("Monitoring", f"Scanning {len(self.active_pairs)} pairs...")
                
                all_tickers = []
                for p in self.active_pairs:
                    all_tickers.extend([p['ticker_a'], p['ticker_b']])
                
                latest_prices = await data_service.get_latest_price(list(set(all_tickers)))

                tasks = [self.process_pair(pair, latest_prices) for pair in self.active_pairs]
                await asyncio.gather(*tasks)
                
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            logger.info("Shutdown signal received. Closing connections...")
        finally:
            # Graceful shutdown of database pools
            await persistence_service.engine.dispose()
            await redis_service.client.close()
            logger.info("Service shutdown complete.")

if __name__ == "__main__":
    monitor = ArbitrageMonitor(mode="live")
    asyncio.run(monitor.run())
