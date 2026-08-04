import asyncio
import os
import signal
import sys
import time
import pytz
from datetime import datetime
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.agents.fundamental_analyst import FundamentalAnalyst
from src.config import settings
from src.services.persistence_service import persistence_service
from src.services.redis_service import redis_service
from src.services.sec_service import SECRateLimitException, SECUnreachableException


def _is_crypto_ticker(ticker: str) -> bool:
    return "-USD" in str(ticker or "").upper()


def _score_is_fresh(score_data: dict | None, *, max_age_seconds: int) -> bool:
    """True when Redis holds a usable EDGAR-backed score within the refresh window."""
    if not score_data or not isinstance(score_data, dict):
        return False
    if score_data.get("available") is False:
        return False
    # Accept edgar or legacy rows without source (pre-fix cache).
    if score_data.get("source") not in (None, "edgar"):
        return False
    ts = score_data.get("last_updated")
    if not isinstance(ts, (int, float)) or ts < 1_000_000_000:
        return False
    return (time.time() - float(ts)) <= max_age_seconds


class SECFundamentalWorker:
    def __init__(self):
        self.analyst = FundamentalAnalyst()
        self.is_running = True
        self.loop_interval = 3600  # Run full universe check every hour
        self.tz = pytz.timezone("America/New_York")
        self._consecutive_unreachable = 0

    def is_within_window(self) -> bool:
        """
        FR-005: Locked to pre-market execution only (04:00 - 09:15 EST).
        Returns True if within window, False otherwise.
        """
        now = datetime.now(self.tz)
        current_time = now.time()
        start_time = datetime.strptime("04:00", "%H:%M").time()
        end_time = datetime.strptime("09:15", "%H:%M").time()
        return start_time <= current_time <= end_time

    async def start(self):
        print("AGENT_LOGGER: SEC Fundamental Worker starting...")
        
        loop = asyncio.get_running_loop()
        # Handle shutdown signals (Linux containers; ignore if unsupported).
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except (NotImplementedError, RuntimeError):
                pass

        while self.is_running:
            try:
                if not self.is_within_window():
                    print("AGENT_LOGGER: SEC Worker outside pre-market window (04:00-09:15 EST). Waiting 1 hour...")
                    await asyncio.sleep(3600)
                    continue
                    
                universe = await persistence_service.get_active_trading_universe()
                equity_universe = [t for t in universe if not _is_crypto_ticker(t)]
                skipped_crypto = len(universe) - len(equity_universe)
                print(
                    f"AGENT_LOGGER: SEC Worker processing equity universe: {equity_universe} "
                    f"(skipped_crypto={skipped_crypto})"
                )
                
                # Pre-warm CIK cache in bulk (equity only)
                await self.analyst.sec_service.prewarm_cik_cache(equity_universe)
                
                for ticker in equity_universe:
                    if not self.is_running or not self.is_within_window():
                        if not self.is_within_window():
                            print("AGENT_LOGGER: Hard Kill threshold (09:15 EST) reached. ABORTING CYCLE.")
                        break

                    if self._consecutive_unreachable >= settings.SEC_WORKER_UNREACHABLE_THRESHOLD:
                        backoff = settings.SEC_WORKER_UNREACHABLE_BACKOFF_SECONDS
                        print(
                            "AGENT_LOGGER: SEC Worker circuit open after "
                            f"{self._consecutive_unreachable} unreachable failures. "
                            f"Backing off {backoff}s instead of hammering EDGAR."
                        )
                        await asyncio.sleep(backoff)
                        self._consecutive_unreachable = 0
                        break
                        
                    print(f"AGENT_LOGGER: SEC Worker analyzing {ticker}...")
                    await self.process_ticker(ticker)
                    
                    # Small delay between tickers to avoid self-rate-limiting
                    await asyncio.sleep(5)
                
                # Check window again before sleeping
                if self.is_within_window():
                    print(f"AGENT_LOGGER: SEC Worker cycle complete. Sleeping for {self.loop_interval}s.")
                    await asyncio.sleep(self.loop_interval)
                else:
                    print("AGENT_LOGGER: Pre-market window closed. Waiting for next window...")
                    await asyncio.sleep(3600)
                
            except Exception as e:
                print(f"AGENT_LOGGER: SEC Worker error in main loop: {e}")
                await asyncio.sleep(60)

    def stop(self):
        print("AGENT_LOGGER: SEC Fundamental Worker shutting down...")
        self.is_running = False

    async def process_ticker(self, ticker: str):
        """Refresh one equity ticker; skip fresh cache; do not cache SEC outages."""
        try:
            cached = await redis_service.get_fundamental_score(ticker)
            if _score_is_fresh(cached, max_age_seconds=settings.SEC_WORKER_REFRESH_SECONDS):
                print(
                    f"AGENT_LOGGER: SEC Worker skipping {ticker}; "
                    f"fresh cache score={cached.get('score')}"
                )
                self._consecutive_unreachable = 0
                return

            await self._analyze_and_cache(ticker)
            self._consecutive_unreachable = 0
        except SECUnreachableException as e:
            self._consecutive_unreachable += 1
            print(
                f"AGENT_LOGGER: SEC Worker unreachable for {ticker} "
                f"(streak={self._consecutive_unreachable}): {e}"
            )
        except Exception as e:
            print(f"AGENT_LOGGER: SEC Worker failed to process {ticker}: {e}")

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((SECRateLimitException, SECUnreachableException)),
        reraise=True,
    )
    async def _analyze_and_cache(self, ticker: str):
        """Analyze filings and write an EDGAR-backed score. Raises on SEC outage."""
        signal_id = f"bg-worker-{ticker}-{int(time.time())}"
        signal = await self.analyst.analyze_ticker(signal_id, ticker)

        # analyze_ticker falls back when sections are empty; never cache that as real state.
        fallback_markers = (
            "No SEC filings found",
            "due to missing SEC data",
            "Fallback to default",
        )
        reasoning = signal.final_reasoning or ""
        prosecutor = signal.prosecutor_argument or ""
        if any(marker in reasoning or marker in prosecutor for marker in fallback_markers):
            print(
                f"AGENT_LOGGER: SEC Worker no usable filings for {ticker}; "
                "leaving cache empty (orchestrator treats as unknown)."
            )
            return

        score_data = {
            "score": signal.structural_integrity_score,
            "prosecutor_argument": signal.prosecutor_argument,
            "defender_argument": signal.defender_argument,
            "final_reasoning": signal.final_reasoning,
            "source": "edgar",
            "available": True,
            "last_updated": time.time(),
        }

        await redis_service.set_fundamental_score(ticker, score_data)
        print(
            f"AGENT_LOGGER: SEC Worker successfully cached score for {ticker}: "
            f"{signal.structural_integrity_score}"
        )


if __name__ == "__main__":
    worker = SECFundamentalWorker()
    asyncio.run(worker.start())
