import numpy as np
import logging
import inspect
from src.services.redis_service import redis_service
from src.config import settings

logger = logging.getLogger(__name__)

class VolatilityService:
    def __init__(self, entropy_threshold: float = settings.VOLATILITY_ENTROPY_THRESHOLD):
        self.entropy_threshold = entropy_threshold

    async def get_l2_entropy(self, ticker: str) -> float:
        """
        Calculates Shannon Entropy for L2 order book depth.
        FR-003: System MUST implement a VolatilitySwitchService that calculates Shannon Entropy on L2 snapshots.
        """
        try:
            snapshot = redis_service.get_json(f"l2:snapshot:{ticker}")
            if inspect.isawaitable(snapshot):
                snapshot = await snapshot
            if not snapshot:
                # Fallback to current price if no L2 snapshot is available (neutral entropy)
                return settings.VOLATILITY_FALLBACK_ENTROPY

            bids = snapshot.get('bids', [])
            asks = snapshot.get('asks', [])
            
            # Combine sizes of all levels
            sizes = [float(b[1]) for b in bids] + [float(a[1]) for a in asks]
            if not sizes:
                return settings.VOLATILITY_FALLBACK_ENTROPY
                
            total_size = sum(sizes)
            if total_size == 0:
                return settings.VOLATILITY_FALLBACK_ENTROPY
                
            # V-02: A single-level book means log2(1)=0, which would return 0.0 (misread as "stable").
            # A 1-level book is the MOST illiquid state — treat it as maximum entropy (1.0).
            if len(sizes) == 1:
                logger.warning(f"Extremely thin L2 book for {ticker} (1 level). Treating as MAX entropy.")
                return 1.0

            probabilities = [s / total_size for s in sizes]

            # Shannon Entropy: -sum(p * log2(p))
            entropy = -sum(p * np.log2(p) for p in probabilities if p > 0)

            # Normalize by log2(N) where N is number of price levels
            max_entropy = np.log2(len(sizes))
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 1.0

            return normalized_entropy
        except Exception as e:
            logger.error(f"Error calculating L2 entropy for {ticker}: {e}")
            return settings.VOLATILITY_FALLBACK_ENTROPY

    async def get_volatility_status(self, ticker: str) -> str:
        """
        User Story 2: Monitor L2 entropy to detect impending volatility spikes.
        """
        entropy = await self.get_l2_entropy(ticker)
        if entropy > self.entropy_threshold:
            logger.warning(f"HIGH_VOLATILITY detected for {ticker} (Entropy: {entropy:.4f})")
            return "HIGH_VOLATILITY"
        return "NORMAL"

volatility_service = VolatilityService()
