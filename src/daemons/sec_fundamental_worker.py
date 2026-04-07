import asyncio
import os
import signal
import sys
from typing import List
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.agents.fundamental_analyst import FundamentalAnalyst
from src.services.persistence_service import persistence_service
from src.services.redis_service import redis_service

class SECFundamentalWorker:
    def __init__(self):
        self.analyst = FundamentalAnalyst()
        self.is_running = True
        self.loop_interval = 3600  # Run full universe check every hour

    async def start(self):
        print("AGENT_LOGGER: SEC Fundamental Worker starting...")
        
        # Handle shutdown signals
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, self.stop)

        while self.is_running:
            try:
                universe = await persistence_service.get_active_trading_universe()
                print(f"AGENT_LOGGER: SEC Worker processing universe: {universe}")
                
                for ticker in universe:
                    if not self.is_running:
                        break
                        
                    print(f"AGENT_LOGGER: SEC Worker analyzing {ticker}...")
                    await self.process_ticker(ticker)
                    
                    # Small delay between tickers to avoid self-rate-limiting
                    await asyncio.sleep(5)
                
                print(f"AGENT_LOGGER: SEC Worker cycle complete. Sleeping for {self.loop_interval}s.")
                await asyncio.sleep(self.loop_interval)
                
            except Exception as e:
                print(f"AGENT_LOGGER: SEC Worker error in main loop: {e}")
                await asyncio.sleep(60)

    def stop(self):
        print("AGENT_LOGGER: SEC Fundamental Worker shutting down...")
        self.is_running = False

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(Exception), # Catch broader exceptions for EDGAR issues
        reraise=True
    )
    async def process_ticker(self, ticker: str):
        """Processes a single ticker with exponential backoff for resilience."""
        # Use a dummy signal_id for background analysis
        signal_id = f"bg-worker-{ticker}-{int(asyncio.get_event_loop().time())}"
        
        try:
            signal = await self.analyst.analyze_ticker(signal_id, ticker)
            
            # Map back to dict for Redis storage
            score_data = {
                "score": signal.structural_integrity_score,
                "prosecutor_argument": signal.prosecutor_argument,
                "defender_argument": signal.defender_argument,
                "final_reasoning": signal.final_reasoning,
                "last_updated": asyncio.get_event_loop().time()
            }
            
            await redis_service.set_fundamental_score(ticker, score_data)
            print(f"AGENT_LOGGER: SEC Worker successfully cached score for {ticker}: {signal.structural_integrity_score}")
            
        except Exception as e:
            print(f"AGENT_LOGGER: SEC Worker failed to process {ticker} after retries: {e}")
            # We don't reraise here to allow the main loop to continue to the next ticker
            # after the retry policy has exhausted itself for THIS ticker.

if __name__ == "__main__":
    worker = SECFundamentalWorker()
    asyncio.run(worker.start())
