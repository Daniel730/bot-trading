from src.services.agent_log_service import agent_trace
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ReflectionAgent:
    def __init__(self):
        pass

    @agent_trace("ReflectionAgent.reflect_on_trade")
    async def reflect_on_trade(self, signal_id: str):
        """
        Conducts a post-mortem on closed trades bound to a signal_id to identify lessons learned.
        """
        from src.services.persistence_service import persistence_service, TradeLedger, OrderStatus, OrderSide
        from sqlalchemy import select
        
        async with persistence_service.AsyncSessionLocal() as session:
            stmt = select(TradeLedger).where(TradeLedger.signal_id == signal_id).where(TradeLedger.status == OrderStatus.COMPLETED)
            result = await session.execute(stmt)
            trades = await result.all() # AsyncResult methods must be awaited
            
            if not trades:
                logger.error(f"ReflectionAgent: No COMPLETED trades found for signal {signal_id}.")
                return
            
            # Combined PnL from metadata. result.all() returns list of Row objects.
            pnl = sum([float(t[0].metadata_json.get('pnl', 0.0)) for t in trades if t[0].metadata_json])
            
            # Check the prevailing trade side to figure out who was right
            primary_side = trades[0][0].side 
            
            is_success = pnl > 0
            
            reflection_note = "✅ SUCCESS: " if is_success else "❌ FAILED: "
            if is_success:
                reflection_note += f"MAB captured alpha on {primary_side.value}."
            else:
                reflection_note += f"MAB weights misled by noise on {primary_side.value}."
            
            # Reward/Penalize agents based on outcome
            await self._update_agent_weights(primary_side, is_success)
            
            logger.info(f"ReflectionAgent: Completed reflection for signal {signal_id}: {reflection_note}")

    async def _update_agent_weights(self, primary_side, is_success: bool):
        from src.services.persistence_service import persistence_service, OrderSide
        
        # If the trade was a BUY, Bull was advocating for it. If SELL, Bear was.
        # SEC Agent supports all valid trades, so if it was a success it was right.
        if primary_side == OrderSide.BUY:
            bull_correct = is_success
            bear_correct = not is_success
        else: # SELL
            bear_correct = is_success
            bull_correct = not is_success
            
        sec_correct = is_success

        await persistence_service.update_agent_metrics("BULL_AGENT", bull_correct)
        await persistence_service.update_agent_metrics("BEAR_AGENT", bear_correct)
        await persistence_service.update_agent_metrics("SEC_AGENT", sec_correct)

    def get_explainability_scores(self, trade_id: str) -> dict:
        """
        Stub for generating SHAP-like values for which agents influenced the trade decision.
        """
        # Could read actual beta expectations via get_agent_metrics
        return {
            "bull_agent": 0.45,
            "bear_agent": -0.12,
            "news_agent": 0.67,
            "fundamental_analyst": 0.23
        }

reflection_agent = ReflectionAgent()
