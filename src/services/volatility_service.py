import numpy as np
import logging
from typing import Dict, Optional
from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)

class VolatilityService:
    def __init__(self, entropy_threshold: float = 0.8):
        self.entropy_threshold = entropy_threshold

    async def get_l2_entropy(self, ticker: str) -> float:
        """
        Calculates Shannon Entropy for L2 order book depth.
        FR-003: System MUST implement a VolatilitySwitchService that calculates Shannon Entropy on L2 snapshots.
        """
        try:
            snapshot = await redis_service.get_json(f"l2:snapshot:{ticker}")
            if not snapshot:
                # Fallback to current price if no L2 snapshot is available (neutral entropy)
                return 0.5

            bids = snapshot.get('bids', [])
            asks = snapshot.get('asks', [])
            
            # Combine sizes of all levels
            sizes = [float(b[1]) for b in bids] + [float(a[1]) for a in asks]
            if not sizes:
                return 0.5
                
            total_size = sum(sizes)
            if total_size == 0:
                return 0.5
                
            probabilities = [s / total_size for s in sizes]
            
            # Shannon Entropy: -sum(p * log2(p))
            entropy = -sum(p * np.log2(p) for p in probabilities if p > 0)
            
            # Normalize by log2(N) where N is number of price levels
            max_entropy = np.log2(len(sizes))
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
            
            return normalized_entropy
        except Exception as e:
            logger.error(f"Error calculating L2 entropy for {ticker}: {e}")
            return 0.5

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
