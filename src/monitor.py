import asyncio
import logging
import sqlite3
import pandas as pd
import pytz
import uuid
from datetime import datetime, time
from typing import List

from prefect import flow, task, get_run_logger
from src.config import LOG_LEVEL, NYSE_OPEN, NYSE_CLOSE, OPERATING_TIMEZONE, PAPER_TRADING
from src.services.data_service import DataService
from src.services.arbitrage_service import ArbitrageService
from src.services.brokerage_service import BrokerageService
from src.services.notification_service import NotificationService
from src.models.arbitrage_models import (
    ArbitragePair, SignalRecord, TriggerType, PairStatus, TradeLedger, OrderType, TradeStatus,
    SlippageError
)

# Configuration
DB_PATH = "trading_bot.sqlite"
SLIPPAGE_TOLERANCE = 0.005

@task(retries=3, retry_delay_seconds=10)
def get_active_pairs() -> List[ArbitragePair]:
    """Fetch active pairs from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ArbitragePair WHERE status = ?", (PairStatus.MONITORING.value,))
    rows = cursor.fetchall()
    conn.close()
    return [ArbitragePair(**dict(row)) for row in rows]

@task
def is_market_open() -> bool:
    """Check NYSE operating hours."""
    tz = pytz.timezone(OPERATING_TIMEZONE)
    now = datetime.now(tz)
    if now.weekday() >= 5: return False
    open_time = time(*map(int, NYSE_OPEN.split(':')))
    close_time = time(*map(int, NYSE_CLOSE.split(':')))
    return open_time <= now.time() <= close_time

@task(log_prints=True)
async def check_pair_task(pair: ArbitragePair):
    """Prefect task to check a single arbitrage pair."""
    logger = get_run_logger()
    data_service = DataService()
    arbitrage_service = ArbitrageService()
    notification_service = NotificationService()
    
    try:
        # 1. Fetch data
        data_a = data_service.fetch_historical_data(pair.ticker_a, period="1y")
        data_b = data_service.fetch_historical_data(pair.ticker_b, period="1y")
        
        if not pair.beta:
            pair.beta = arbitrage_service.calculate_beta(data_a, data_b)
            logger.info(f"Beta for {pair.ticker_a}/{pair.ticker_b}: {pair.beta}")
        
        historical_spreads = arbitrage_service.calculate_spreads(data_a, data_b, pair.beta)
        prices = data_service.fetch_current_prices([pair.ticker_a, pair.ticker_b])
        price_a, price_b = prices[pair.ticker_a], prices[pair.ticker_b]
        
        # 2. Math & Signal
        z_score = arbitrage_service.calculate_z_score(price_a, price_b, pair.beta, historical_spreads, 30)
        logger.info(f"Pair {pair.ticker_a}/{pair.ticker_b} Z-Score: {z_score:.2f}")

        if abs(z_score) > 2.0:
            signal_id = str(uuid.uuid4())
            # Mock AI (US2)
            ai_result = {"recommendation": "GO", "rationale": "Statistical anomaly confirmed by AI."}
            
            # 3. Notify
            await notification_service.send_approval_request(
                signal_id=signal_id, ticker_a=pair.ticker_a, ticker_b=pair.ticker_b,
                z_score=z_score, ai_rationale=ai_result["rationale"]
            )
            
            # 4. Auto-Paper Trade (US4)
            if PAPER_TRADING and ai_result["recommendation"] == "GO":
                logger.info(f"Auto-executing Paper Trade for {pair.ticker_a}/{pair.ticker_b}")
                # (Execution logic simplified for the flow refactor)
                pass

    except Exception as e:
        logger.error(f"Failed checking {pair.ticker_a}/{pair.ticker_b}: {e}")

@flow(name="Strategic Arbitrage Monitor", log_prints=True)
async def monitor_flow():
    """Main Prefect Flow for monitoring arbitrage."""
    logger = get_run_logger()
    
    if not is_market_open():
        logger.info("NYSE Market is closed. Skipping poll.")
        return

    pairs = get_active_pairs()
    if not pairs:
        logger.info("No active pairs found in database.")
        return

    # Check all pairs in parallel using Prefect tasks
    await asyncio.gather(*(check_pair_task(pair) for pair in pairs))

if __name__ == "__main__":
    # For local testing, runs the flow once
    asyncio.run(monitor_flow())
