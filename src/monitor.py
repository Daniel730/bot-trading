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
from src.services.risk_service import risk_service
from src.services.brokerage_service import BrokerageService
from src.services.sec_service import sec_service
from src.services.agent_log_service import agent_logger, agent_trace
from src.services.dashboard_service import dashboard_service

# Disable yfinance cache to prevent SQLite locks in Docker
yf.set_tz_cache_location("/tmp/yf_cache")

# Global exception hook for Agent-Centric Observability
def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    agent_logger.capture_error(exc_value, context={"type": "Global Crash"})

import sys
sys.excepthook = global_exception_handler

# Configure logging
def setup_logging():
    root_logger = logging.getLogger()
    # Clear existing handlers to prevent duplication (especially in Docker/Watch mode)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    
    # Also suppress noisy third-party loggers if needed
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    
    return logging.getLogger(__name__)

logger = setup_logging()

class ArbitrageMonitor:
    def __init__(self, mode: str = "live"):
        self.persistence = PersistenceManager(settings.DB_PATH)
        self.brokerage = BrokerageService()
        self.mode = mode
        self.active_pairs = []
        self.active_signals = [] # For Dashboard US2
        self.last_dev_warning = datetime.min
        self.current_day = None
        self.daily_start_cash = 0.0
        self.daily_halted = False

    async def initialize_pairs(self):
        """Initializes cointegration metrics and Kalman filters."""
        pairs_to_init = settings.ARBITRAGE_PAIRS
        logger.info(f"Initializing pairs in {'DEV' if settings.DEV_MODE else 'PROD'} mode...")
        
        for pair_config in pairs_to_init:
            ticker_a, ticker_b = pair_config['ticker_a'], pair_config['ticker_b']
            try:
                # 1. Get historical data for initial check/seeding
                hist_data = data_service.get_historical_data([ticker_a, ticker_b])
                col_a = next((c for c in hist_data.columns if ticker_a in c), None)
                col_b = next((c for c in hist_data.columns if ticker_b in c), None)
                
                if not col_a or not col_b: continue

                is_coint, p_val, hedge = arbitrage_service.check_cointegration(hist_data[col_a], hist_data[col_b])
                
                # We always try to monitor if the pair is defined, but cointegration is a quality flag
                pair_id = self.persistence.save_pair(ticker_a, ticker_b, hedge)
                
                # 2. Check for persisted Kalman state
                saved_state = self.persistence.load_kalman_state(pair_id)
                if saved_state:
                    logger.info(f"Loading persisted Kalman state for {ticker_a}/{ticker_b}")
                    kf = arbitrage_service.get_or_create_filter(
                        pair_id, 
                        delta=settings.KALMAN_DELTA, 
                        r=settings.KALMAN_R,
                        initial_state=[saved_state['alpha'], saved_state['beta']],
                        initial_covariance=saved_state['p_matrix']
                    )
                else:
                    logger.info(f"Seeding new Kalman filter for {ticker_a}/{ticker_b} from OLS")
                    kf = arbitrage_service.get_or_create_filter(
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
        """Processes a single pair for signals and validation in a non-blocking task."""
        try:
            t_a, t_b = pair['ticker_a'], pair['ticker_b']
            if t_a not in latest_prices or t_b not in latest_prices:
                return
            
            price_a = latest_prices[t_a]
            price_b = latest_prices[t_b]

            # Feature: Daily Stop-Loss Check
            daily_limit = self.daily_start_cash * 0.25
            max_loss = daily_limit * 0.10
            
            if not self.daily_halted and self.current_day and max_loss > 0:
                daily_pnl = self.persistence.get_daily_pnl(self.current_day, is_shadow=(self.mode == "shadow"))
                if daily_pnl <= -max_loss:
                    self.daily_halted = True
                    logger.error(f"DAILY STOP-LOSS TRIGGERED: PnL ${daily_pnl:.2f} <= -${max_loss:.2f}. Halting new trades.")
                    
                    # Generate Post-Mortem
                    trades = self.persistence.get_daily_trades(self.current_day, is_shadow=(self.mode == "shadow"))
                    from src.agents.fundamental_analyst import fundamental_analyst
                    pm_analysis = await fundamental_analyst.generate_post_mortem(daily_pnl, trades)
                    
                    await notification_service.send_message(f"🚨 **DAILY STOP-LOSS HIT** 🚨\n\n{pm_analysis}")

            # Feature 008: Sector Cluster Guard & Circuit Breaker
            pair_key = f"{t_a}_{t_b}"
            sector = settings.PAIR_SECTORS.get(pair_key, "Unknown")

            if risk_service.is_sector_frozen(sector):
                if audit_service.total_cycles % 10 == 0:
                    logger.warning(f"CIRCUIT BREAKER: Sector '{sector}' is currently FROZEN. Skipping {pair_key}.")
                return

            active_portfolio = shadow_service.get_active_portfolio_with_sectors() if self.mode == "shadow" else []

            exposure_check = risk_service.check_cluster_exposure(sector, active_portfolio)
            if not exposure_check["allowed"]:
                if audit_service.total_cycles % 10 == 0:
                    logger.warning(f"VETO: Sector '{sector}' at limit. Skipping {pair_key}.")
                return

            # Feature 007: Kalman Filter Update
            kf = arbitrage_service.get_or_create_filter(pair['id'])
            state_vec, innovation_var = kf.update(price_a, price_b)
            alpha, beta = state_vec
            spread, z_score = kf.calculate_spread_and_zscore(price_a, price_b)
            
            # Persist Kalman state
            kf_state = kf.get_state_dict()
            self.persistence.save_kalman_state(
                pair_id=pair['id'],
                alpha=alpha,
                beta=beta,
                p_matrix=kf_state['p_matrix'],
                q_matrix=kf_state['q_matrix'],
                r_value=kf_state['r_value'],
                ve=innovation_var
            )

            # Feature: Trade Exit Logic
            open_trade = self.persistence.get_open_trade(pair['id'], is_shadow=(self.mode == "shadow"))
            if open_trade:
                # Exit condition: Z-score reverts to mean (e.g. abs(z) < 0.5)
                if abs(z_score) < 0.5:
                    logger.info(f"EXIT SIGNAL: Z-score for {t_a}/{t_b} reverted to {z_score:.2f}")
                    if self.mode == "shadow":
                        await shadow_service.close_simulated_trade(
                            pair_id=pair['id'],
                            trade_id=open_trade['id'],
                            direction=open_trade['direction'],
                            size_a=open_trade['size_a'],
                            size_b=open_trade['size_b'],
                            entry_price_a=open_trade['entry_price_a'],
                            entry_price_b=open_trade['entry_price_b'],
                            exit_price_a=price_a,
                            exit_price_b=price_b
                        )
                    else:
                        logger.info(f"LIVE EXIT: Closing {open_trade['direction']} for {t_a}/{t_b}")
                        # Execute counter-orders to close position
                        # If direction was "Short-Long" (Short A, Long B) -> Sell B, Buy A
                        # If direction was "Long-Short" (Long A, Short B) -> Sell A, Buy B
                        if open_trade['direction'] == "Short-Long":
                            self.brokerage.place_market_order(t_a, open_trade['size_a'], "BUY")
                            self.brokerage.place_market_order(t_b, open_trade['size_b'], "SELL")
                        else:
                            self.brokerage.place_market_order(t_a, open_trade['size_a'], "SELL")
                            self.brokerage.place_market_order(t_b, open_trade['size_b'], "BUY")
                        
                        self.persistence.close_trade(open_trade['id'], price_a, price_b, 0.0)
                # We have an open position, do not open a new one
                return

            # Only process signals if Z-score is significant
            if abs(z_score) < 2.0:
                # Cleanup if it was previously active
                self.active_signals = [s for s in self.active_signals if not (s['ticker_a'] == t_a and s['ticker_b'] == t_b)]
                return

            # Update/Add to active signals for US2
            sig_status = "Analyzing"
            signal_entry = next((s for s in self.active_signals if s['ticker_a'] == t_a and s['ticker_b'] == t_b), None)
            if not signal_entry:
                signal_entry = {"ticker_a": t_a, "ticker_b": t_b, "z_score": z_score, "status": sig_status}
                self.active_signals.append(signal_entry)
            else:
                signal_entry['z_score'] = z_score
                signal_entry['status'] = sig_status

            await dashboard_service.update_state(
                "Analyzing Pair", 
                f"Anomaly detected in {t_a}/{t_b}. Z-Score: {z_score:.2f}.",
                active_signals=self.active_signals
            )

            signal_id = self.persistence.log_signal(pair['id'], z_score)
            
            # Performance Tracking for SC-002
            start_time = datetime.now()

            signal_context = {
                "ticker_a": t_a, "ticker_b": t_b,
                "z_score": z_score, "dynamic_beta": beta,
                "sector": sector, "sector_exposure": exposure_check["exposure_pct"],
                "signal_id": signal_id
            }

            decision_state = await orchestrator.ainvoke({"signal_context": signal_context})
            latency = (datetime.now() - start_time).total_seconds()
            logger.info(f"PERF: AI Validation for {t_a}/{t_b} completed in {latency:.2f}s (Target: <30s)")
            
            audit_service.log_thought_process(signal_id, decision_state)
            
            if decision_state['final_confidence'] > 0.5:
                sig_status = "Waiting for Approval"
                if signal_entry: signal_entry['status'] = sig_status
                
                await dashboard_service.update_state(
                    "Waiting for Approval", 
                    f"AI verified trade for {t_a}/{t_b}.\nConfidence: {decision_state['final_confidence']:.2f}",
                    active_signals=self.active_signals
                )
                
                divergence_desc = "significantly out of sync" if abs(z_score) > 2.0 else "showing a clear divergence"
                
                approved = await notification_service.request_approval(
                    f"I've found a solid trading opportunity! {t_a} and {t_b} are currently {divergence_desc}, and my models suggest they will likely converge soon.\n\n"
                    f"🎯 *Verdict*: {decision_state['final_verdict']}\n\n"
                    f"--- Technical Details ---\n"
                    f"Pair: {t_a}/{t_b}\n"
                    f"Z-Score: {z_score:.2f}\n"
                    f"Beta: {beta:.2f}"
                )
                if approved:
                    sig_status = "Executing Trade"
                    if signal_entry: signal_entry['status'] = sig_status
                    
                    await dashboard_service.update_state(
                        "Executing Trade", 
                        f"Approval received. Routing market orders for {t_a} and {t_b}...",
                        active_signals=self.active_signals
                    )
                    
                    kelly_size = risk_service.calculate_kelly_size(decision_state['final_confidence'])
                    direction = "Short-Long" if z_score > 0 else "Long-Short"
                    await self.execute_trade(pair, direction, price_a, price_b, kelly_size)
                    
                    # Remove from active signals after execution starts
                    self.active_signals = [s for s in self.active_signals if not (s['ticker_a'] == t_a and s['ticker_b'] == t_b)]
                else:
                    logger.warning(f"Trade rejected or timed out for {t_a}/{t_b}")
                    sig_status = "Trade Rejected"
                    if signal_entry: signal_entry['status'] = sig_status
                    
                    await dashboard_service.update_state(
                        "Monitoring 24/7", 
                        f"Trade for {t_a}/{t_b} was rejected or timed out.",
                        active_signals=self.active_signals
                    )
            else:
                # VETO Case
                sig_status = "VETO"
                if signal_entry: signal_entry['status'] = sig_status
                await dashboard_service.update_state(
                    "Monitoring 24/7",
                    f"AI Vetoed signal for {t_a}/{t_b}: {decision_state['final_verdict']}",
                    active_signals=self.active_signals
                )
        except Exception as e:
            logger.error(f"Error processing pair {pair.get('ticker_a')}: {e}")

    async def execute_trade(self, pair, direction, price_a, price_b, size):
        """Executes a trade in either shadow or live mode."""
        t_a, t_b = pair['ticker_a'], pair['ticker_b']
        
        if self.mode == "shadow":
            size_a = max(size * 100, 1.0) 
            size_b = max((size * 100) * pair.get('hedge_ratio', 1.0), 1.0)
            await shadow_service.execute_simulated_trade(pair['id'], direction, size_a, size_b, price_a, price_b)
        else:
            # Feature: Dynamic Size Calculation for Live/Demo
            # Goal: Invest 10% of Daily Allocation (which is 25% of total cash)
            daily_limit = self.daily_start_cash * 0.25
            per_trade_limit = daily_limit * 0.10
            
            # Check if we have exceeded the daily investment limit
            daily_invested = self.persistence.get_daily_invested(self.current_day, is_shadow=(self.mode == "shadow"))
            if daily_invested + per_trade_limit > daily_limit:
                logger.warning(f"SKIPPING TRADE: Daily investment limit reached (${daily_invested:.2f} + ${per_trade_limit:.2f} > ${daily_limit:.2f})")
                return

            target_cash = per_trade_limit / 2.0 # Split between both legs
            
            # Feature 014: Fee Analyzer Integration
            # We estimate friction based on a nominal 0.5% spread + any commissions
            friction_a = risk_service.calculate_friction(target_cash, spread_pct=0.5)
            friction_b = risk_service.calculate_friction(target_cash, spread_pct=0.5)
            
            check_a = risk_service.is_trade_allowed(target_cash, friction_a['friction_pct'])
            check_b = risk_service.is_trade_allowed(target_cash, friction_b['friction_pct'])
            
            if not check_a['allowed']:
                logger.warning(f"VETO {t_a}: {check_a['reason']}")
                return
            if not check_b['allowed']:
                logger.warning(f"VETO {t_b}: {check_b['reason']}")
                return

            size_a = round(target_cash / price_a, 6)
            size_b = round(target_cash / price_b, 6)

            logger.info(f"LIVE EXECUTION: {direction} for {t_a}/{t_b} at {price_a}/{price_b} (Target: ${target_cash:.2f} per side)")
            
            # Logic: T212 Invest API does NOT support Shorting.
            # If we need to SELL, we MUST check if we own the asset.
            
            orders = []
            if direction == "Short-Long":
                orders.append({"ticker": t_a, "qty": size_a, "side": "SELL"})
                orders.append({"ticker": t_b, "qty": size_b, "side": "BUY"})
            else: # "Long-Short"
                orders.append({"ticker": t_a, "qty": size_a, "side": "BUY"})
                orders.append({"ticker": t_b, "qty": size_b, "side": "SELL"})

            cash_available = self.brokerage.get_account_cash()
            
            for order in orders:
                # Prevent duplicate pending orders
                if self.brokerage.has_pending_order(order['ticker']):
                    logger.warning(f"SKIPPING {order['side']}: {order['ticker']} already has a pending order.")
                    continue

                if order['side'] == "SELL":
                    if self.brokerage.is_ticker_owned(order['ticker']):
                        self.brokerage.place_market_order(order['ticker'], order['qty'], "SELL")
                    else:
                        logger.warning(f"SKIPPING SELL: {order['ticker']} not owned (T212 Invest does not support Shorting)")
                else: # BUY
                    cost = order['qty'] * (price_a if order['ticker'] == t_a else price_b)
                    if cash_available >= cost:
                        self.brokerage.place_market_order(order['ticker'], order['qty'], "BUY")
                        cash_available -= cost
                    else:
                        logger.error(f"INSUFFICIENT FUNDS: Need ${cost:.2f}, have ${cash_available:.2f} for {order['ticker']}")

            self.persistence.save_trade(pair['id'], direction, size_a, size_b, price_a, price_b, is_shadow=False)

    async def check_synthetic_orders(self, latest_prices: dict):
        """
        Feature 015 (FR-012): In-Memory Synthetic Trailing Stop evaluation.
        """
        with self.persistence._get_connection() as conn:
            rows = conn.execute("SELECT * FROM synthetic_orders WHERE is_active = 1").fetchall()
            for row in rows:
                order = dict(row)
                ticker = order['ticker']
                if ticker not in latest_prices:
                    continue
                
                current_price = latest_prices[ticker]
                highest = order['highest_price'] or order['activation_price']
                trail_pct = order['trailing_pct']
                
                # Update high-water mark
                if current_price > highest:
                    conn.execute("UPDATE synthetic_orders SET highest_price = ? WHERE ticker = ?", (current_price, ticker))
                    highest = current_price
                
                # Check for stop trigger: current_price < highest * (1 - trail_pct)
                stop_price = highest * (1 - trail_pct)
                if current_price <= stop_price:
                    logger.warning(f"SYNTHETIC STOP TRIGGERED: {ticker} at {current_price:.2f} (Stop: {stop_price:.2f})")
                    # Execute sell order
                    self.brokerage.place_market_order(ticker, 1.0, "SELL") # Simplified quantity
                    conn.execute("UPDATE synthetic_orders SET is_active = 0 WHERE ticker = ?", (ticker,))
            conn.commit()

    async def run(self):
        # 1. Connectivity check
        key = settings.effective_t212_key
        masked_key = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "INVALID/EMPTY"
        logger.info(f"Checking T212 connectivity (Mode: {settings.TRADING_212_MODE}, Key: {masked_key})")
        
        connected = self.brokerage.test_connection()
        if not connected and self.mode == "live":
            logger.error("!!! FAILED TO CONNECT TO T212. Check API Key and Permissions !!!")
        else:
            logger.info("Successfully connected to Trading 212 API.")

        # 2. Initial Setup
        logger.info("Initializing Dashboard Service...")
        await dashboard_service.start()
        await asyncio.sleep(1) # Give it a second to bind to port
        await dashboard_service.update_state("Initializing", "Booting up core components and establishing connections...")
        
        logger.info("Initializing Pairs...")
        await self.initialize_pairs()
        
        logger.info("Starting Telegram Listener...")
        await notification_service.start_listening()
        
        logger.info(f"Starting DCA Service for Feature 015...")
        from src.services.dca_service import dca_service
        asyncio.create_task(dca_service.process_schedules())
        
        # 4. Main Loop
        while True:
            now = datetime.now()
            
            # Feature: Daily limit reset
            current_date_str = now.date().isoformat()
            if self.current_day != current_date_str:
                self.current_day = current_date_str
                # Attempt to get cash; fallback to a reasonable default for testing if API fails
                cash = self.brokerage.get_account_cash()
                self.daily_start_cash = cash if cash > 0 else 10000.0
                self.daily_halted = False
                logger.info(f"--- New Day: {self.current_day} | Start Cash: ${self.daily_start_cash:.2f} ---")

            if settings.DEV_MODE:
                if (now - self.last_dev_warning).total_seconds() >= 300:
                    logger.warning("\n" + "!"*50 + "\n!!! DEVELOPMENT MODE ACTIVE: MONITORING 24/7 !!!\n" + "!"*50)
                    self.last_dev_warning = now
            else:
                # Market hours check (14:30 - 21:00 WET)
                if now.weekday() >= 5 or (now.hour < 14 or (now.hour == 14 and now.minute < 30)) or now.hour >= 21:
                    await dashboard_service.update_state("Market Closed", "Waiting for market hours (14:30 - 21:00 WET)")
                    await asyncio.sleep(60)
                    continue

            # Cycle tracking
            audit_service.log_cycle(success=True)
            if audit_service.total_cycles % 10 == 0:
                rate = audit_service.get_connectivity_rate()
                logger.info(f"--- Connectivity Health: {rate:.1f}% ---")

            await dashboard_service.update_state("Monitoring 24/7", f"Scanning {len(self.active_pairs)} pairs for anomalies...")

            # Fetch all latest prices in one batch
            all_tickers = []
            for p in self.active_pairs:
                all_tickers.extend([p['ticker_a'], p['ticker_b']])
            
            latest_prices = data_service.get_latest_price(list(set(all_tickers)))

            # Execute pair processing concurrently
            tasks = [self.process_pair(pair, latest_prices) for pair in self.active_pairs]
            await asyncio.gather(*tasks)
            
            # Feature 015: Check synthetic orders
            await self.check_synthetic_orders(latest_prices)
            
            await asyncio.sleep(15)

if __name__ == "__main__":
    monitor = ArbitrageMonitor(mode="live")
    asyncio.run(monitor.run())
