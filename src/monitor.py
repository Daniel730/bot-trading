import asyncio
import logging
import pandas as pd
import yfinance as yf
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
from src.services.market_regime_service import market_regime_service
from src.services.brokerage_service import BrokerageService
from src.services.persistence_service import ExitReason
from src.services.dashboard_service import dashboard_service
import uuid
import pytz

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
        self._signals_lock = asyncio.Lock()
        self.last_dev_warning = datetime.min
        self.current_day = None
        self.daily_start_cash = 0.0
        self.daily_halted = False
        # Tracks the calendar date on which each pair's cointegration was last
        # re-validated. Keyed by pair_id; value is a datetime.date object.
        self.last_cointegration_check: dict = {}

    def is_market_open(self) -> bool:
        """
        Fix M-10: Checks if the market is currently open based on America/New_York time.
        Bypassed if DEV_MODE=true or if it's a crypto pair.
        """
        if settings.DEV_MODE:
            return True

        tz = pytz.timezone(settings.MARKET_TIMEZONE)
        now = datetime.now(tz)

        # Weekend check
        if now.weekday() >= 5:
            return False

        start_time = now.replace(hour=settings.START_HOUR, minute=settings.START_MINUTE, second=0, microsecond=0)
        end_time = now.replace(hour=settings.END_HOUR, minute=settings.END_MINUTE, second=0, microsecond=0)

        return start_time <= now <= end_time

    def next_market_open(self) -> datetime:
        """
        FR-006: Returns the next NYSE open in MARKET_TIMEZONE.
        If called while the market is currently open, returns today's open timestamp.
        """
        tz = pytz.timezone(settings.MARKET_TIMEZONE)
        now = datetime.now(tz)
        candidate = now.replace(
            hour=settings.START_HOUR, minute=settings.START_MINUTE,
            second=0, microsecond=0
        )
        # If today's open has already passed, roll forward one day.
        if now > candidate:
            from datetime import timedelta
            candidate = candidate + timedelta(days=1)
        # Skip Saturday (5) and Sunday (6).
        while candidate.weekday() >= 5:
            from datetime import timedelta
            candidate = candidate + timedelta(days=1)
        return candidate

    def log_preflight(self) -> None:
        """
        FR-006: Single informative startup line so the operator immediately
        knows mode, pair universe size, and when the next trading window opens.
        """
        mode = "PAPER" if settings.PAPER_TRADING else "LIVE"
        if settings.DEV_MODE:
            pair_count = len(settings.CRYPTO_TEST_PAIRS)
            logger.info(
                f"MODE: {mode} | DEV_MODE=true (crypto test pairs, 24/7 scan, "
                f"randomised prices) | Pair universe: {pair_count} crypto pairs"
            )
        else:
            equity_count = len(settings.ARBITRAGE_PAIRS)
            crypto_count = len(settings.CRYPTO_TEST_PAIRS)
            next_open = self.next_market_open()
            logger.info(
                f"MODE: {mode} | DEV_MODE=false | Pair universe: "
                f"{equity_count} equity + {crypto_count} crypto = "
                f"{equity_count + crypto_count} total | "
                f"Equity pairs gated by NYSE hours, crypto runs 24/7 | "
                f"Next NYSE open: {next_open.strftime('%Y-%m-%d %H:%M %Z')}"
            )

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
        """Initializes cointegration metrics and Kalman filters.

        - DEV_MODE: only crypto pairs (24/7 testing with randomized prices).
        - PROD: equity pairs + crypto pairs combined. The market-hours guard
          in process_pair() pauses equity scans outside NYSE hours; crypto
          pairs (detected by '-USD' suffix) keep running on weekends and
          overnight so the bot is never idle.
        """
        if settings.LIVE_CAPITAL_DANGER:
            await self.verify_entropy_baselines()

        if settings.DEV_MODE:
            pairs_to_init = settings.CRYPTO_TEST_PAIRS
        else:
            pairs_to_init = list(settings.ARBITRAGE_PAIRS) + list(settings.CRYPTO_TEST_PAIRS)
        logger.info(
            f"Initializing {len(pairs_to_init)} pairs in "
            f"{'DEV' if settings.DEV_MODE else 'PROD'} mode "
            f"(stocks={len(settings.ARBITRAGE_PAIRS) if not settings.DEV_MODE else 0}, "
            f"crypto={len(settings.CRYPTO_TEST_PAIRS)})..."
        )

        for pair_config in pairs_to_init:
            ticker_a, ticker_b = pair_config['ticker_a'], pair_config['ticker_b']
            try:
                # Wrap sync historical data fetch
                hist_data = await asyncio.to_thread(data_service.get_historical_data, [ticker_a, ticker_b])
                if hist_data is None or hist_data.empty:
                    logger.warning(f"No historical data for {ticker_a}/{ticker_b}")
                    continue

                col_a = next((c for c in hist_data.columns if ticker_a in c), None)
                col_b = next((c for c in hist_data.columns if ticker_b in c), None)

                if not col_a or not col_b: continue

                is_coint, p_val, hedge = arbitrage_service.check_cointegration(hist_data[col_a], hist_data[col_b])

                # Bug L-01: Guard against NaN/Inf hedge ratio
                import numpy as np
                if pd.isna(hedge) or np.isinf(hedge):
                    logger.warning(f"Invalid hedge ratio for {ticker_a}/{ticker_b}: {hedge}. Using 1.0.")
                    hedge = 1.0

                pair_id = f"{ticker_a}_{ticker_b}"

                # Initialize Kalman filter.
                # Do NOT pass initial_state here — that would bypass both Redis
                # warm-start and 30-day historical pre-warming, leaving P=eye(2)*10
                # so large that the filter absorbs all price variation on tick-1
                # and every z-score collapses to 0.00 indefinitely.
                # get_or_create_filter will:
                #   1. Warm-start from Redis if a saved state exists, OR
                #   2. Pre-warm with 30d of hourly data so P has converged before
                #      the first live tick.
                kf = await arbitrage_service.get_or_create_filter(
                    pair_id,
                    delta=settings.KALMAN_DELTA,
                    r=settings.KALMAN_R
                )

                metrics = arbitrage_service.get_spread_metrics(hist_data[col_a], hist_data[col_b], hedge)
                self.active_pairs.append({
                    "id": pair_id, "ticker_a": ticker_a, "ticker_b": ticker_b,
                    "hedge_ratio": hedge, "mean": metrics['mean'], "std": metrics['std'],
                    "is_cointegrated": is_coint
                })
                # Mark the pair as already validated today so the daily re-check
                # in the scan loop doesn't immediately fire again 15 s after boot.
                self.last_cointegration_check[pair_id] = datetime.now().date()
                logger.info(f"Pair {ticker_a}/{ticker_b} initialized (Coint: {is_coint}).")
            except Exception as e:
                logger.error(f"Error initializing {ticker_a}/{ticker_b}: {e}")

    async def reload_pairs(self):
        """Hot-reload the active pair universe from the (possibly updated)
        settings. Re-uses the same logic as initialize_pairs but is safe to call
        from a running scan loop: we swap self.active_pairs only after the new
        list is built, then clear filters that no longer correspond to a live
        pair so memory doesn't leak.
        """
        async with self._signals_lock:
            old_ids = {p['id'] for p in self.active_pairs}
            # Reset and rebuild via the existing initializer.
            self.active_pairs = []
            self.last_cointegration_check = {}
            await self.initialize_pairs()
            new_ids = {p['id'] for p in self.active_pairs}

            # Forget Kalman filters for pairs that were removed so memory
            # doesn't accumulate across reloads.
            removed = old_ids - new_ids
            if removed:
                from src.services.arbitrage_service import arbitrage_service
                for pid in removed:
                    arbitrage_service.filters.pop(pid, None)
                logger.info(f"reload_pairs: dropped {len(removed)} pairs ({sorted(removed)})")
            logger.info(
                f"reload_pairs complete: {len(new_ids)} active pairs "
                f"(+{len(new_ids - old_ids)} new, -{len(removed)} removed)"
            )

    async def process_pair(self, pair: dict, latest_prices: dict) -> dict:
        """Processes a single pair for signals and validation."""
        diagnostic = {"confidence": 0.0, "verdict": "IGNORED"}
        try:
            t_a, t_b = pair['ticker_a'], pair['ticker_b']

            # Bug M-10: Market hours enforcement
            is_crypto = "-USD" in t_a or "-USD" in t_b
            if not is_crypto and not self.is_market_open():
                return diagnostic

            # Skip pairs whose cointegration has broken (detected by daily re-check).
            if not pair.get('is_cointegrated', True):
                return diagnostic

            if t_a not in latest_prices or t_b not in latest_prices:
                return diagnostic

            price_a = latest_prices[t_a]
            price_b = latest_prices[t_b]

            # Feature 007: Kalman Filter Update
            kf = await arbitrage_service.get_or_create_filter(pair['id'])
            # O2 fix: guard against None return when Redis is unavailable or pair data missing
            if kf is None:
                logger.warning("Kalman filter unavailable for pair %s — skipping tick.", pair['id'])
                return diagnostic
            state_vec, innovation_var = kf.update(price_a, price_b)
            spread, z_score = kf.calculate_spread_and_zscore(price_a, price_b)

            # Persist Kalman state to Redis
            await arbitrage_service.save_filter_state(pair['id'], kf, z_score)

            # Sprint J: Heartbeat log for pair health
            logger.info(f"SCAN [{t_a}/{t_b}] Current Z-Score: {z_score:.2f} | Beta: {state_vec[1]:.4f}")

            # Signal Generation
            if abs(z_score) > 2.0:
                signal_id = str(uuid.uuid4())
                logger.info(f"SIGNAL [{t_a}/{t_b}] z={z_score:.3f} beta={state_vec[1]:.4f} — running AI validation")

                # Update Active Signals for Dashboard
                async with self._signals_lock:
                    signal_entry = next((s for s in self.active_signals if s['ticker_a'] == t_a and s['ticker_b'] == t_b), None)
                    if not signal_entry:
                        signal_entry = {"ticker_a": t_a, "ticker_b": t_b, "z_score": z_score, "status": "Analyzing"}
                        self.active_signals.append(signal_entry)

                # AI Validation
                # Look up this pair's sector so the orchestrator uses the right beacon asset.
                pair_sector = settings.PAIR_SECTORS.get(
                    pair['id'],
                    settings.PAIR_SECTORS.get(f"{t_b}_{t_a}", "Technology")
                )
                signal_context = {
                    "ticker_a": t_a, "ticker_b": t_b,
                    "z_score": z_score, "dynamic_beta": state_vec[1],
                    "signal_id": signal_id,
                    "sector": pair_sector,
                }

                # Wrap orchestrator in a hard 8 s deadline.
                # If any LLM call or Redis read hangs, we veto the signal rather
                # than stalling the entire scan loop for all other pairs.
                try:
                    decision_state = await asyncio.wait_for(
                        orchestrator.ainvoke({"signal_context": signal_context}),
                        timeout=8.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"ORCHESTRATOR [{t_a}/{t_b}] timed out after 8 s. "
                        f"Vetoing signal to protect scan loop."
                    )
                    return diagnostic
                await audit_service.log_thought_process(signal_id, decision_state)
                logger.info(f"ORCHESTRATOR [{t_a}/{t_b}] confidence={decision_state['final_confidence']:.3f} verdict={decision_state['final_verdict']}")

                if decision_state['final_confidence'] > 0.5:
                    approved = await notification_service.request_approval(f"Opportunity in {t_a}/{t_b}. Z:{z_score:.2f}", trade_value=target_cash * 2)
                    if approved:
                        direction = "Short-Long" if z_score > 0 else "Long-Short"
                        await self.execute_trade(pair, direction, price_a, price_b, signal_id)
                        diagnostic["verdict"] = "EXECUTED"
                else:
                    logger.info(f"ORCHESTRATOR [{t_a}/{t_b}] VETOED: Confidence {decision_state['final_confidence']:.3f} too low.")
                    diagnostic["verdict"] = "VETOED"

                diagnostic["confidence"] = decision_state['final_confidence']
            else:
                # Cleanup inactive signals
                async with self._signals_lock:
                    self.active_signals = [s for s in self.active_signals if not (s['ticker_a'] == t_a and s['ticker_b'] == t_b)]

            return diagnostic

        except Exception as e:
            logger.error(f"Error processing pair {pair.get('ticker_a')}: {e}")
            return diagnostic

    async def execute_trade(self, pair, direction, price_a, price_b, signal_id):
        """Executes a trade and logs to PostgreSQL."""
        t_a, t_b = pair['ticker_a'], pair['ticker_b']

        # Sprint D.2: Bid-Ask Slippage Protection
        bid_a, ask_a = await data_service.get_bid_ask(t_a)
        bid_b, ask_b = await data_service.get_bid_ask(t_b)

        if bid_a > 0 and ask_a > 0 and bid_b > 0 and ask_b > 0:
            spread_a = (ask_a - bid_a) / bid_a if bid_a > 0 else 0
            spread_b = (ask_b - bid_b) / bid_b if bid_b > 0 else 0
            # Bug L-02: Proportional spread calculation
            total_spread = (1 + spread_a) * (1 + spread_b) - 1
            if total_spread > 0.003:
                logger.warning(f"SPREAD GUARD: Rejecting {t_a}/{t_b}. Total Spread: {total_spread*100:.3f}% > 0.3% max threshold.")
                return
        else:
            logger.warning(f"SPREAD GUARD: Could not fetch valid Bid/Ask for {t_a}/{t_b}. Proceeding with caution or paper logic.")

        # Bug H-02: Wrap sync brokerage calls in asyncio.to_thread
        total_cash = await asyncio.to_thread(self.brokerage.get_account_cash)
        if total_cash is None:
            total_cash = 2000.0  # Fallback

        # Sprint B: Risk Service validation with Half-Kelly and Max 5% Port limit
        # Bug L-03: Pass per-pair allocation (5% max) instead of full portfolio
        per_pair_alloc = total_cash * 0.05
        risk_res = risk_service.validate_trade(
            ticker=f"{t_a}_{t_b}",
            total_portfolio_cash=total_cash,
            amount_fiat=per_pair_alloc,
            win_prob=0.55,
            win_loss_ratio=1.0
        )

        if not risk_res["is_acceptable"]:
            logger.warning(f"Live execute rejected by RiskService: {risk_res.get('rejection_reason', 'Insufficient Kelly Fraction')}")
            return

        target_cash = risk_res["final_amount"]
        logger.info(f"RISK APPROVED SIZE: {target_cash:.2f} per leg for {t_a}/{t_b} (Kelly: {risk_res['kelly_fraction']:.4f})")

        size_a = round(target_cash / price_a, 6)
        size_b = round(target_cash / price_b, 6)

        # Feature 008 - Sector Cluster Guard (prospective, race-condition-safe).
        # Both legs are counted as new exposure (target_cash each) so the check
        # is evaluated BEFORE the trade is placed, not after.  This prevents two
        # signals in the same scan window from independently passing the 30 % cap
        # and then together pushing the sector to 60 %.
        pair_sector = settings.PAIR_SECTORS.get(
            pair['id'], settings.PAIR_SECTORS.get(f"{t_b}_{t_a}", "General")
        )
        current_portfolio = await shadow_service.get_active_portfolio_with_sectors()
        if current_portfolio:
            total_size = sum(p['size'] for p in current_portfolio)
            sector_size = sum(p['size'] for p in current_portfolio if p['sector'] == pair_sector)
            new_trade_size = target_cash * 2  # two legs of equal value
            projected_exposure = (sector_size + new_trade_size) / (total_size + new_trade_size)
            if projected_exposure > settings.MAX_SECTOR_EXPOSURE:
                logger.warning(
                    f"CLUSTER GUARD: Rejecting {t_a}/{t_b}. Adding this trade would push "
                    f"'{pair_sector}' exposure to {projected_exposure:.1%}, "
                    f"exceeding the {settings.MAX_SECTOR_EXPOSURE:.0%} cap."
                )
                return

        # Capture market regime for journal — logged after broker execution
        regime_info = await market_regime_service.classify_current_regime(t_a)
        if not regime_info:
            logger.warning("Regime classification unavailable for %s; defaulting to STABLE", t_a)
            regime_info = {"regime": "STABLE", "confidence": 0.5, "features": {}}

        # Determina a direcao (Side) para cada perna
        side_a = "SELL" if direction == "Short-Long" else "BUY"
        side_b = "BUY" if direction == "Short-Long" else "SELL"

        # P-07 (2026-04-26): Crypto pairs (Yahoo "-USD" symbols) cannot be
        # traded on Trading 212 - T212 has no spot crypto, only the EU-listed
        # crypto ETNs (BTCE.DE, ZETH.DE, etc.). Sending BTC-USD/SOL-USD/etc.
        # to the broker just produces malformed instrument IDs (BTC-USD_US_EQ)
        # that T212 always rejects. Force shadow execution for crypto pairs
        # regardless of PAPER_TRADING so the strategy can still be evaluated
        # without flooding the log with broker rejections.
        is_crypto_pair = "-USD" in t_a or "-USD" in t_b

        if settings.PAPER_TRADING or is_crypto_pair:
            # Em paper trading, simplesmente simulamos o trade usando o shadow_service.
            # R4 fix (2026-04-19): propagate signal_id so the shadow TradeLedger row
            # can be joined with the AgentReasoning / TradeJournal rows logged for
            # this signal. Previously shadow_service generated its own UUID and
            # decorrelated the paper-trade audit trail.
            mode_tag = "PAPER TRADING" if settings.PAPER_TRADING else "SHADOW (crypto, T212-unsupported)"
            logger.info(f"{mode_tag}: Executing shadow trade {direction} for {t_a}/{t_b}")
            await shadow_service.execute_simulated_trade(
                pair['id'], direction, size_a, size_b, price_a, price_b,
                signal_id=signal_id,
            )
            return

        # Chamada ao broker (T212 via Fractional Engine)

        exec_t_a = settings.DEV_EXECUTION_TICKERS.get(t_a, t_a) if settings.DEV_MODE else t_a
        exec_t_b = settings.DEV_EXECUTION_TICKERS.get(t_b, t_b) if settings.DEV_MODE else t_b

        logger.info(f"LIVE EXECUTION: Placing orders for {exec_t_a}/{exec_t_b} - {direction}")

        # T-02: Atomic execution guard - abort if Leg A fails; emergency-close if Leg B fails
        # Leg A
        res_a = await self.brokerage.place_value_order(exec_t_a, target_cash, side_a)
        status_a = OrderStatus.OPEN if res_a.get("status") != "error" else OrderStatus.FAILED
        order_id_a = res_a.get("order_id") or res_a.get("orderId") or str(uuid.uuid4())

        if status_a == OrderStatus.FAILED:
            # P-08 (2026-04-26): Surface the broker's actual rejection reason.
            # Previously the log discarded res_a entirely so every abort looked
            # identical and we couldn't tell auth failures from bad-symbol
            # rejections from insufficient-funds.
            broker_msg = res_a.get("message") or res_a.get("error") or res_a
            logger.error(
                f"ATOMIC ABORT: Leg A ({exec_t_a}) failed before Leg B was placed. "
                f"No position opened. Broker response: {broker_msg}"
            )
            return

        # Leg B
        res_b = await self.brokerage.place_value_order(exec_t_b, target_cash, side_b)
        status_b = OrderStatus.OPEN if res_b.get("status") != "error" else OrderStatus.FAILED
        order_id_b = res_b.get("order_id") or res_b.get("orderId") or str(uuid.uuid4())

        if status_b == OrderStatus.FAILED:
            logger.critical(
                f"ATOMIC FAILURE: Leg A ({exec_t_a}) succeeded but Leg B ({exec_t_b}) failed. "
                f"Placing emergency close on Leg A to prevent orphaned directional exposure."
            )
            close_side_a = "BUY" if side_a == "SELL" else "SELL"
            close_res = await self.brokerage.place_value_order(exec_t_a, target_cash, close_side_a)
            if close_res.get("status") == "error":
                orphan_msg = (
                    f"CRITICAL - EMERGENCY CLOSE FAILED\n"
                    f"Signal: {signal_id}\n"
                    f"Ticker: {exec_t_a} ({side_a} leg)\n"
                    f"The position is now ORPHANED. Manual intervention required.\n"
                    f"Broker response: {close_res}"
                )
                logger.critical(orphan_msg)
                # Alert operator immediately via Telegram / console
                await notification_service.send_message(orphan_msg)
                # Persist the orphan so it appears in the audit trail and
                # dashboard queries don't silently miss it.
                await persistence_service.log_trade({
                    "order_id": f"ORPHAN_{signal_id}",
                    "signal_id": uuid.UUID(signal_id),
                    "ticker": exec_t_a,
                    "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
                    "quantity": size_a,
                    "price": price_a,
                    "status": OrderStatus.FAILED,
                    "metadata": {
                        "orphaned": True,
                        "reason": "emergency_close_failed",
                        "broker_response": close_res,
                    },
                })
            else:
                logger.info(f"EMERGENCY CLOSE SUCCESS: Orphaned {exec_t_a} position closed.")
            return

        # M-05: Journal written only after both broker legs have returned successfully
        await persistence_service.log_trade_journal({
            "signal_id": uuid.UUID(signal_id),
            "entry_regime": regime_info["regime"],
            "metrics_at_entry": {
                "z_score": risk_res.get("z_score", 0.0),
                "win_prob": 0.55,
                "regime_confidence": regime_info["confidence"],
                "features": regime_info["features"]
            }
        })

        # Log Leg A
        await persistence_service.log_trade({
            "order_id": order_id_a,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_a,
            "side": OrderSide.SELL if side_a == "SELL" else OrderSide.BUY,
            "quantity": size_a,
            "price": price_a,
            "status": status_a,
            "metadata": {"broker_response": res_a}
        })

        # Log Leg B
        await persistence_service.log_trade({
            "order_id": order_id_b,
            "signal_id": uuid.UUID(signal_id),
            "ticker": t_b,
            "side": OrderSide.BUY if side_b == "BUY" else OrderSide.SELL,
            "quantity": size_b,
            "price": price_b,
            "status": status_b,
            "metadata": {"broker_response": res_b}
        })

        logger.info(f"TRADE EXECUTED: {t_a}/{t_b} {direction} | Status: A={status_a.value}, B={status_b.value}")

    async def _recheck_cointegration(self, pair: dict):
        """
        Re-validates the ADF cointegration test for a single pair using the
        last 30 days of hourly data.  Called once per calendar day per pair.

        If the p-value rises above 0.10 the pair is marked is_cointegrated=False
        and trading is suspended until the next re-check restores it.
        A Telegram/console alert is fired on both break and restore events.
        """
        t_a, t_b = pair['ticker_a'], pair['ticker_b']
        try:
            hist_data = await asyncio.to_thread(
                data_service.get_historical_data, [t_a, t_b]
            )
            if hist_data is None or hist_data.empty:
                return

            col_a = next((c for c in hist_data.columns if t_a in c), None)
            col_b = next((c for c in hist_data.columns if t_b in c), None)
            if not col_a or not col_b:
                return

            is_coint, p_val, _ = arbitrage_service.check_cointegration(
                hist_data[col_a], hist_data[col_b]
            )

            previously_coint = pair.get('is_cointegrated', True)

            if not is_coint:
                pair['is_cointegrated'] = False
                if previously_coint:
                    # Only alert on a real break (True -> False transition).
                    # If the pair was already non-cointegrated at startup, stay quiet.
                    msg = (
                        f"COINTEGRATION BREAK: {t_a}/{t_b} - "
                        f"ADF p-value={p_val:.4f} > 0.05. "
                        f"Pair suspended until cointegration is restored."
                    )
                    logger.warning(msg)
                    await notification_service.send_message(msg)
                else:
                    logger.debug(
                        f"[{t_a}/{t_b}] Still non-cointegrated (p={p_val:.4f}). "
                        f"Staying suspended."
                    )
            else:
                pair['is_cointegrated'] = True
                if not previously_coint:
                    # Alert only on a real restore (False -> True transition).
                    msg = (
                        f"COINTEGRATION RESTORED: {t_a}/{t_b} - "
                        f"ADF p-value={p_val:.4f}. Pair re-activated."
                    )
                    logger.info(msg)
                    await notification_service.send_message(msg)
                else:
                    logger.debug(
                        f"[{t_a}/{t_b}] Cointegration confirmed (p={p_val:.4f})."
                    )
        except Exception as e:
            logger.error(f"Error re-checking cointegration for {t_a}/{t_b}: {e}")

    async def run(self):
        # FR-006: Pre-flight line - operator must know mode/universe/window
        # before a single log line about infra appears.
        self.log_preflight()

        # Initial Setup
        logger.info("Initializing Databases...")
        await asyncio.gather(
            persistence_service.init_db(),
            self.initialize_pairs()
        )
        # Make this monitor instance discoverable by dashboard endpoints
        # (so /api/pairs can hot-reload, etc).
        dashboard_service.attach_monitor(self)
        await dashboard_service.start()

        # Sprint J: Start Telegram Listener (Async)
        await notification_service.start_listening()

        # Sprint C: Startup Health Checks
        logger.info("Running System Health Checks...")

        # 1. PostgreSQL Check
        try:
            async with persistence_service.engine.connect() as conn:
                pass
        except Exception as e:
            msg = f"CRITICAL INIT ERROR: PostgreSQL connection failed! {e}"
            logger.error(msg)
            await notification_service.send_alert(msg)
            return

        # 2. Redis Check
        try:
            await redis_service.client.ping()
        except Exception as e:
            msg = f"CRITICAL INIT ERROR: Redis connection failed! {e}"
            logger.error(msg)
            await notification_service.send_alert(msg)
            return

        # 3. Trading 212 API Check (if not exclusively paper/mocked)
        if not settings.PAPER_TRADING:
            await asyncio.sleep(1)  # Rate limit safety delay
            try:
                # Await async brokerage call
                test_ping = await self.brokerage.get_portfolio()
                if isinstance(test_ping, dict) and test_ping.get("status") == "error":
                    raise Exception(f"T212 error: {test_ping.get('message')}")
            except Exception as e:
                msg = f"CRITICAL INIT ERROR: Trading 212 API connection failed! {e}"
                logger.error(msg)
                await notification_service.send_alert(msg)
                return

        logger.info("All Health Checks Passed (Postgres, Redis, T212). Bot is active.")

        # Sprint J: Signal the user via Telegram that we are entering MISSION MODE
        await notification_service.send_message("System Health: All Checks Passed.\n\nMode: Continuous Scan initiated for " + f"{len(self.active_pairs)}" + " pairs.")

        # Reset circuit breaker on clean startup so a stale DEGRADED_MODE
        # from a previous crashed session doesn't silently block all signals.
        await persistence_service.set_system_state("operational_status", "NORMAL")
        await persistence_service.set_system_state("consecutive_api_timeouts", "0")
        logger.info("Circuit breaker reset to NORMAL on startup.")

        try:
            while True:
                try:
                    from src.services.performance_service import performance_service
                    p_metrics = await performance_service.get_portfolio_metrics()
                    await dashboard_service.update_metrics(p_metrics)

                    pnl = await persistence_service.get_total_pnl()
                    await dashboard_service.update(
                        stage="Monitoring",
                        details=f"Scanning {len(self.active_pairs)} pairs...",
                        pnl=pnl
                    )
                except Exception as e:
                    logger.error(f"Error pushing metrics to dashboard: {e}")
                    await dashboard_service.update("Monitoring", f"Scanning {len(self.active_pairs)} pairs...")
                # Exit Strategy Loop - M-06: run all exit evaluations concurrently
                open_signals = []
                try:
                    open_signals = await persistence_service.get_open_signals()
                    if open_signals:
                        await asyncio.gather(
                            *[self._evaluate_exit_conditions(signal) for signal in open_signals],
                            return_exceptions=True  # one signal failing doesn't block the rest
                        )
                except Exception as e:
                    logger.error(f"Error evaluating open signals for exits: {e}")

                all_tickers = []
                for p in self.active_pairs:
                    all_tickers.extend([p['ticker_a'], p['ticker_b']])

                latest_prices = await data_service.get_latest_price(list(set(all_tickers)))

                # Daily cointegration re-validation - fire background tasks so
                # historical data fetches don't block the current scan cycle.
                today = datetime.now().date()
                for pair in self.active_pairs:
                    if self.last_cointegration_check.get(pair['id']) != today:
                        asyncio.create_task(self._recheck_cointegration(pair))
                        self.last_cointegration_check[pair['id']] = today

                tasks = [self.process_pair(pair, latest_prices) for pair in self.active_pairs]
                results = await asyncio.gather(*tasks)

                # L-14: Enriched heartbeat - show analyzed vs vetoed vs open signal counts
                active_signals = [r for r in results if r and r.get('confidence', 0) > 0.6]
                vetoed = [r for r in results if r and r.get('vetoed')]
                logger.info(
                    f"--- Iteration: {len(self.active_pairs)} pairs scanned | "
                    f"{len(active_signals)} signals above threshold | "
                    f"{len(vetoed)} vetoed | "
                    f"{len(open_signals)} open positions ---"
                )

                await asyncio.sleep(15)
        except asyncio.CancelledError:
            logger.info("Shutdown signal received. Closing connections...")
        finally:
            # Graceful shutdown of database pools
            await persistence_service.engine.dispose()
            await redis_service.client.aclose()
            logger.info("Service shutdown complete.")

    async def _evaluate_exit_conditions(self, signal: dict):
        """Monitors open positions for Take Profit or Stop Loss."""
        sig_id = signal["signal_id"]
        legs = signal.get("legs", [])
        if len(legs) != 2: return

        leg_a, leg_b = legs[0], legs[1]
        t_a, t_b = leg_a["ticker"], leg_b["ticker"]

        # Get real-time prices
        prices = await data_service.get_latest_price([t_a, t_b])
        if t_a not in prices or t_b not in prices: return

        p_a, p_b = prices[t_a], prices[t_b]

        current_value = (leg_a["quantity"] * p_a) + (leg_b["quantity"] * p_b)
        cost_basis = signal["total_cost_basis"]

        # 1. Financial Kill Switch Check
        if risk_service.check_financial_kill_switch(current_value, cost_basis, max_loss_pct=0.02):
            logger.warning(f"FINANCIAL KILL SWITCH TRIGGERED for {t_a}/{t_b}. Closing position.")
            await self._close_position(signal, p_a, p_b, reason=ExitReason.KILL_SWITCH)
            return

        # 2. Statistical Stop Loss / Take profit
        pair_id = f"{t_a}_{t_b}"
        kf = await arbitrage_service.get_or_create_filter(pair_id)
        if not kf: return

        # Calculate current dynamic z-score based on latest price
        spread, z_score = kf.calculate_spread_and_zscore(p_a, p_b)

        # Statistical Take Profit (Mean Reversion complete)
        if abs(z_score) <= 0.5:
            logger.info(f"TAKE PROFIT reached for {t_a}/{t_b} (Z-Score: {z_score:.2f}).")
            await self._close_position(signal, p_a, p_b, reason=ExitReason.TAKE_PROFIT)

        # Statistical Stop Loss (Cointegration break)
        elif abs(z_score) >= 3.5:
            logger.warning(f"STATISTICAL STOP LOSS triggered for {t_a}/{t_b} (Z-Score: {z_score:.2f}). Cointegration likely lost.")
            await self._close_position(signal, p_a, p_b, reason=ExitReason.STOP_LOSS)

    async def _close_position(self, signal: dict, price_a: float, price_b: float, reason: ExitReason):
        sig_id = signal["signal_id"]
        logger.info(f"Closing position {sig_id} Reason: {reason.value}")

        for leg in signal["legs"]:
            ticker = leg["ticker"]
            qty = leg["quantity"]
            # Close order side is the opposite of the open side
            side = "SELL" if leg["side"] == "BUY" else "BUY"

            exec_t = settings.DEV_EXECUTION_TICKERS.get(ticker, ticker) if settings.DEV_MODE else ticker
            if not settings.PAPER_TRADING:
                p = price_a if ticker == signal["legs"][0]["ticker"] else price_b
                await self.brokerage.place_value_order(exec_t, float(qty * p), side)

        # M-04: Compute realized PnL from entry vs exit price per leg
        leg_a, leg_b = signal["legs"][0], signal["legs"][1]
        exit_prices = {leg_a["ticker"]: price_a, leg_b["ticker"]: price_b}
        pnl = 0.0
        for leg in signal["legs"]:
            qty = leg["quantity"]
            entry = leg["price"]
            exit_p = exit_prices[leg["ticker"]]
            pnl += (exit_p - entry) * qty if leg["side"] == "BUY" else (entry - exit_p) * qty

        # N2 fix: in paper mode, route through shadow_service so the shadow ledger
        # gets a proper close log with directional PnL breakdown.
        # shadow_service.close_simulated_trade does NOT call persistence - we handle
        # DB writes once here for both live and paper paths to preserve exit_reason.
        if settings.PAPER_TRADING:
            direction = "Short-Long" if leg_a["side"] == "SELL" else "Long-Short"
            await shadow_service.close_simulated_trade(
                pair_id=f"{leg_a['ticker']}_{leg_b['ticker']}",
                signal_id=uuid.UUID(sig_id) if isinstance(sig_id, str) else sig_id,
                direction=direction,
                size_a=leg_a["quantity"],
                size_b=leg_b["quantity"],
                entry_price_a=leg_a["price"],
                entry_price_b=leg_b["price"],
                exit_price_a=price_a,
                exit_price_b=price_b,
            )

        await persistence_service.close_trade(uuid.UUID(sig_id), exit_prices, pnl, exit_reason=reason)


if __name__ == "__main__":
    monitor = ArbitrageMonitor()
    asyncio.run(monitor.run())
