import json
import logging
import uuid
import asyncio
from datetime import datetime
from src.services.persistence_service import persistence_service, OrderStatus, MarketRegime
from src.services.agent_log_service import agent_trace

logger = logging.getLogger(__name__)

class ReflectionAgent:
    def __init__(self):
        pass

    @agent_trace("ReflectionAgent.reflect_on_trade")
    async def reflect_on_trade(self, signal_id_str: str):
        """
        Conducts a post-mortem on a closed trade using PostgreSQL data.
        Triggered asynchronously by persistence_service.close_trade.
        """
        try:
            # 1. Wait a bit for all legs to be processed if necessary (though close_trade should be enough)
            await asyncio.sleep(2)

            signal_id = uuid.UUID(signal_id_str)

            # 2. Fetch all trade data for this signal
            async with persistence_service.AsyncSessionLocal() as session:
                from sqlalchemy import select
                from src.services.persistence_service import TradeLedger, TradeJournal, AgentReasoning

                # Fetch TradeLedger entries
                stmt_l = select(TradeLedger).where(TradeLedger.signal_id == signal_id)
                res_l = await session.execute(stmt_l)
                trades = res_l.scalars().all()

                if not trades:
                    logger.error(f"ReflectionAgent: No trades found for signal {signal_id_str}")
                    return

                # Fetch Journal entry
                stmt_j = select(TradeJournal).where(TradeJournal.signal_id == signal_id)
                res_j = await session.execute(stmt_j)
                journal = res_j.scalar_one_or_none()

                if not journal:
                    logger.warning(f"ReflectionAgent: No journal entry found for {signal_id_str}. Creating one.")
                    # Entry context might be lost, but we can still reflect

                # 3. Analyze Performance
                total_pnl = 0.0
                total_slippage_bps = 0
                trade_count = 0

                for t in trades:
                    if t.metadata_json and "pnl" in t.metadata_json:
                        total_pnl += float(t.metadata_json["pnl"])
                    trade_count += 1

                is_success = total_pnl > 0

                # 4. Generate Reflection Tone
                reflection_note = ""
                efficiency = 1.0

                if is_success:
                    reflection_note = "SUCCESS: Mean reversion captured within expected timeframe."
                    efficiency = 0.95
                else:
                    exit_reason = journal.exit_reason.value if journal and journal.exit_reason else "UNKNOWN"
                    if exit_reason == "STOP_LOSS":
                        reflection_note = "FAILED: Statistical stop hit. Hedge ratio might have drifted or cointegration broke."
                    elif exit_reason == "KILL_SWITCH":
                        reflection_note = "CAUTION: Financial kill switch triggered. Extreme downside volatility detected."
                    else:
                        reflection_note = "FAILED: Performance below expectations."
                    efficiency = 0.2

                # 5. Update Journal
                journal_data = {
                    "signal_id": signal_id,
                    "reflection_text": reflection_note,
                    "efficiency_score": efficiency,
                }

                # P-05 (2026-04-26): TradeJournal.entry_regime is NOT NULL.
                # In the recovery path (no pre-existing journal row) the
                # ON CONFLICT DO UPDATE degenerates to a plain INSERT, which
                # blew up with NotNullViolationError. If we have no entry
                # context, fall back to the latest logged regime, then to
                # STABLE so the row can be persisted and the reflection isn't
                # lost.
                if journal is None:
                    fallback_regime = MarketRegime.STABLE
                    try:
                        latest = await persistence_service.get_latest_market_regime()
                        if latest and latest.get("regime"):
                            fallback_regime = MarketRegime(latest["regime"])
                    except Exception as regime_err:
                        logger.debug(f"ReflectionAgent: regime lookup failed, using STABLE: {regime_err}")
                    journal_data["entry_regime"] = fallback_regime

                await persistence_service.log_trade_journal(journal_data)

                # 6. Adjust Agent Weights (Conceptual update to a summary table)
                # In a real system, we'd update a Redis key or a weighted table
                # that the Orchestrator reads to adjust confidence.
                await self._update_global_agent_performance(is_success)

                logger.info(f"ReflectionAgent: Completed reflection for trade {signal_id_str}: {reflection_note}")

        except Exception as e:
            logger.error(f"Error in ReflectionAgent.reflect_on_trade: {e}")

    async def _update_global_agent_performance(self, is_success: bool):
        """
        Updates a global performance score that influences future trade confidence.
        """
        current_perf_str = await persistence_service.get_system_state("global_strategy_accuracy", "0.5")
        current_perf = float(current_perf_str)

        # Simple moving average / EMA approach
        alpha = 0.1
        target = 1.0 if is_success else 0.0
        new_perf = (alpha * target) + (1 - alpha) * current_perf

        await persistence_service.set_system_state("global_strategy_accuracy", f"{new_perf:.4f}")

reflection_agent = ReflectionAgent()
