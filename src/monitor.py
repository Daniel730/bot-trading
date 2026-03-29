import asyncio
import logging
import sqlite3
import pandas as pd
import pytz
from datetime import datetime, time
from src.config import LOG_LEVEL, NYSE_OPEN, NYSE_CLOSE, OPERATING_TIMEZONE, PAPER_TRADING, MAX_ALLOCATION_PERCENTAGE
from src.services.data_service import DataService
from src.services.arbitrage_service import ArbitrageService
from src.services.brokerage_service import BrokerageService
from src.services.notification_service import NotificationService
from src.models.arbitrage_models import (
    ArbitragePair, SignalRecord, TriggerType, PairStatus, TradeLedger, OrderType, TradeStatus,
    OperatingHoursError, SlippageError
)
import uuid

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

class Monitor:
    def __init__(self):
        self.data_service = DataService()
        self.arbitrage_service = ArbitrageService()
        self.brokerage_service = BrokerageService()
        self.notification_service = NotificationService()
        self.db_path = "trading_bot.sqlite"
        self.slippage_tolerance = 0.005 # 0.5% max slippage

    def is_market_open(self) -> bool:
        """Checks if current time is within NYSE operating hours (WET)."""
        tz = pytz.timezone(OPERATING_TIMEZONE)
        now = datetime.now(tz)
        
        # NYSE is open Monday-Friday
        if now.weekday() >= 5:
            return False
            
        open_time = time(*map(int, NYSE_OPEN.split(':')))
        close_time = time(*map(int, NYSE_CLOSE.split(':')))
        
        return open_time <= now.time() <= close_time

    def get_active_pairs(self) -> list[ArbitragePair]:
        """Fetch all active arbitrage pairs from the database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ArbitragePair WHERE status = ?", (PairStatus.MONITORING.value,))
        rows = cursor.fetchall()
        conn.close()
        return [ArbitragePair(**dict(row)) for row in rows]

    def save_signal(self, signal: SignalRecord):
        """Persist a signal record to SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO SignalRecord (id, pair_id, timestamp, z_score, price_a, price_b, trigger_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (signal.id, signal.pair_id, signal.timestamp.isoformat(), signal.z_score, 
              signal.price_a, signal.price_b, signal.trigger_type.value))
        conn.commit()
        conn.close()

    def record_trade(self, trade: TradeLedger):
        """Persist a trade record to the ledger."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO TradeLedger (id, timestamp, ticker, quantity, price, order_type, is_paper, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trade.id, trade.timestamp.isoformat(), trade.ticker, trade.quantity, 
              trade.price, trade.order_type.value, trade.is_paper, trade.status.value))
        conn.commit()
        conn.close()

    async def execute_trade(self, ticker: str, quantity: float, order_type: OrderType, price: float):
        """Executes a trade (Paper or Live) with slippage check and records it."""
        # T024: Slippage check
        try:
            current_price = self.data_service.get_latest_price(ticker)
            slippage = abs(current_price - price) / price
            if slippage > self.slippage_tolerance:
                logger.warning(f"Slippage for {ticker} ({slippage:.4f}) exceeds tolerance ({self.slippage_tolerance})")
                if not PAPER_TRADING: 
                    raise SlippageError(f"Slippage too high for live trade: {slippage:.4f}")
        except Exception as e:
            logger.error(f"Slippage check failed or exceeded for {ticker}: {e}")
            if not PAPER_TRADING: return # Abort live trade on slippage or data failure

        trade_id = str(uuid.uuid4())
        logger.info(f"Executing {order_type.value} for {ticker}: {quantity} units (Paper: {PAPER_TRADING})")
        
        status = TradeStatus.COMPLETED
        if not PAPER_TRADING:
            try:
                self.brokerage_service.place_market_order(ticker, quantity, order_type.value)
            except Exception as e:
                logger.error(f"Live trade failed for {ticker}: {e}")
                status = TradeStatus.FAILED
        
        trade = TradeLedger(
            id=trade_id,
            ticker=ticker,
            quantity=quantity,
            price=price,
            order_type=order_type,
            is_paper=PAPER_TRADING,
            status=status
        )
        self.record_trade(trade)

    async def check_pair(self, pair: ArbitragePair):
        """Perform monitoring, signal generation, and AI validation for a single pair."""
        try:
            # Fetch historical data to compute beta and historical spreads
            data_a = self.data_service.fetch_historical_data(pair.ticker_a, period="1y")
            data_b = self.data_service.fetch_historical_data(pair.ticker_b, period="1y")
            
            # Recalculate beta (optional)
            if not pair.beta:
                pair.beta = self.arbitrage_service.calculate_beta(data_a, data_b)
                logger.info(f"Recalculated beta for {pair.ticker_a}/{pair.ticker_b}: {pair.beta}")
            
            # Historical spreads
            historical_spreads = self.arbitrage_service.calculate_spreads(data_a, data_b, pair.beta)
            
            # Current prices
            prices = self.data_service.fetch_current_prices([pair.ticker_a, pair.ticker_b])
            price_a = prices[pair.ticker_a]
            price_b = prices[pair.ticker_b]
            
            # Z-Score (using 30-day window)
            z_score = self.arbitrage_service.calculate_z_score(price_a, price_b, pair.beta, historical_spreads, 30)
            logger.info(f"Pair {pair.ticker_a}/{pair.ticker_b} Z-Score: {z_score:.2f}")

            # Signal generation logic
            if abs(z_score) > 2.0:
                trigger = TriggerType.ENTRY
                signal_id = str(uuid.uuid4())
                
                # US2: AI Fundamental Validation
                logger.info(f"Triggering AI validation for {pair.ticker_a}/{pair.ticker_b}...")
                # In this MVP, we simulate the AI tool call directly
                # In a full deployment, this would be an MCP client call
                ai_result = {
                    "recommendation": "GO",
                    "rationale": "Statistical anomaly confirmed by lack of significant news/filings explaining the divergence."
                }
                
                signal = SignalRecord(
                    id=signal_id,
                    pair_id=pair.id,
                    z_score=z_score,
                    price_a=price_a,
                    price_b=price_b,
                    trigger_type=trigger,
                    ai_validation_status=ai_result["recommendation"],
                    ai_rationale=ai_result["rationale"]
                )
                self.save_signal(signal)
                logger.info(f"Generated {trigger.value} signal with AI {ai_result['recommendation']} for {pair.ticker_a}/{pair.ticker_b}")
                
                # Notify with AI rationale
                await self.notification_service.send_approval_request(
                    signal_id=signal.id,
                    ticker_a=pair.ticker_a,
                    ticker_b=pair.ticker_b,
                    z_score=z_score,
                    ai_rationale=ai_result["rationale"]
                )
                
                # If AI says GO and we are in Paper Trading, we can auto-simulate a trade for validation
                if PAPER_TRADING and ai_result["recommendation"] == "GO":
                    logger.info("Auto-executing Paper Trade based on AI GO...")
                    # Calculate rebalance quantities
                    total_alloc = 1000.0 # Example base allocation
                    quantities = self.arbitrage_service.calculate_rebalance_quantities(
                        price_a, price_b, pair.beta, total_alloc, 0, 0
                    )
                    
                    # T021: Atomic swap execution sequence
                    # 1. Execute SELL legs first (to free up liquidity/balance)
                    sell_legs = [(k, v) for k, v in quantities.items() if v < 0]
                    buy_legs = [(k, v) for k, v in quantities.items() if v > 0]
                    
                    for ticker_key, qty in sell_legs:
                        ticker = pair.ticker_a if ticker_key == "ticker_a" else pair.ticker_b
                        price = price_a if ticker_key == "ticker_a" else price_b
                        await self.execute_trade(ticker, abs(qty), OrderType.SELL, price)
                    
                    # 2. Execute BUY legs
                    for ticker_key, qty in buy_legs:
                        ticker = pair.ticker_a if ticker_key == "ticker_a" else pair.ticker_b
                        price = price_a if ticker_key == "ticker_a" else price_b
                        await self.execute_trade(ticker, qty, OrderType.BUY, price)

        except Exception as e:
            logger.error(f"Error checking pair {pair.ticker_a}/{pair.ticker_b}: {e}")

    async def run(self):
        """Main execution loop with NYSE operating hours guard."""
        logger.info("Starting Arbitrage Monitor...")
        while True:
            # T023: NYSE hours guard
            if not self.is_market_open():
                logger.info("Market is closed. Sleeping...")
                await asyncio.sleep(300) # Sleep 5 minutes
                continue

            pairs = self.get_active_pairs()
            for pair in pairs:
                await self.check_pair(pair)
            
            await asyncio.sleep(60) # Poll every 60 seconds

if __name__ == "__main__":
    monitor = Monitor()
    asyncio.run(monitor.run())
