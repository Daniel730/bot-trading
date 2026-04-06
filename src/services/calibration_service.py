import logging
import pandas as pd
from typing import Dict, List, Optional
from src.services.persistence_service import persistence_service
from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)

from src.services.persistence_service import persistence_service, AchievabilityStatus
from datetime import datetime, timezone

class CalibrationService:
    def __init__(self):
        # FR-009: 0.5bps impact per 10% depth consumed
        self.impact_penalty_per_10pct = 0.5 

    async def run_fill_achievability_audit(self, trade_id: str, l2_snapshot: List[dict], requested_qty: float, actual_fill_price: float) -> Dict:
        """
        Audits a Shadow Mode trade against L2 liquidity reality (T012, T013).
        """
        if not l2_snapshot or len(l2_snapshot) < 1:
            logger.warning(f"Audit failed for trade {trade_id}: Insufficient L2 depth.")
            return {
                "trade_id": trade_id,
                "achievability_status": AchievabilityStatus.UNACHIEVABLE,
                "status": "INSUFFICIENT_DATA",
                "reason": "Missing L2 snapshot"
            }

        # 1. Calculate Theoretical Mid Price (Top of Book)
        try:
            best_bid = float(l2_snapshot[0]['bid_price'])
            best_ask = float(l2_snapshot[0]['ask_price'])
            theoretical_mid = (best_bid + best_ask) / 2
        except (KeyError, IndexError, ValueError):
            return {
                "trade_id": trade_id,
                "achievability_status": AchievabilityStatus.UNACHIEVABLE,
                "status": "INSUFFICIENT_DATA",
                "reason": "Malformed L2 snapshot"
            }

        # 2. Calculate "Walk the Book" VWAP (T012, CHK022)
        remaining_qty = requested_qty
        total_cost = 0
        top_level_qty = float(l2_snapshot[0].get('ask_size', 1))

        for level in l2_snapshot:
            level_price = float(level.get('ask_price', 0))
            level_qty = float(level.get('ask_size', 0))
            
            if level_qty <= 0: continue

            fill_qty = min(remaining_qty, level_qty)
            total_cost += fill_qty * level_price
            remaining_qty -= fill_qty
            
            if remaining_qty <= 0:
                break
        
        if remaining_qty > 0:
            # T013: Identify "unachievable" if we run out of book depth
            return {
                "trade_id": trade_id,
                "achievability_status": AchievabilityStatus.UNACHIEVABLE,
                "status": "UNACHIEVABLE",
                "reason": "Insufficient liquidity to fill requested quantity"
            }

        vwap_theoretical = total_cost / requested_qty

        # 3. Apply Market Impact Penalty (FR-009, CHK024)
        pct_top_depth_consumed = (requested_qty / top_level_qty) * 100
        impact_bps = (pct_top_depth_consumed / 10) * self.impact_penalty_per_10pct
        impact_adjusted_price = vwap_theoretical * (1 + impact_bps / 10000)

        # 4. Compare with Actual Fill Price (T014)
        slippage_bps = int(abs(actual_fill_price - theoretical_mid) / theoretical_mid * 10000)
        
        # Achievability logic: 
        # PERFECT if actual_fill is close to impact_adjusted_price
        # UNACHIEVABLE if actual_fill is BETTER than impact_adjusted (too good to be true)
        diff_bps = (impact_adjusted_price - actual_fill_price) / theoretical_mid * 10000
        
        if diff_bps > 2: # Actual was > 2bps better than our realistic model
            status = AchievabilityStatus.UNACHIEVABLE
        elif diff_bps < -5: # Actual was > 5bps worse than our model
            status = AchievabilityStatus.ACCEPTABLE
        else:
            status = AchievabilityStatus.PERFECT

        analysis = {
            "trade_id": trade_id,
            "theoretical_mid_price": theoretical_mid,
            "vwap_fill_price": actual_fill_price,
            "slippage_bps": slippage_bps,
            "achievability_status": status,
            "audit_timestamp": datetime.now(timezone.utc)
        }
        
        # T014: Persist to PostgreSQL (FillAnalysis table)
        # await persistence_service.log_fill_analysis(analysis)
        
        return analysis

calibration_service = CalibrationService()
