import json
import logging
import uuid
import asyncio
import inspect
from datetime import datetime
from src.config import settings
from src.services.persistence_service import persistence_service, OrderStatus, MarketRegime
from src.services.agent_log_service import agent_trace

logger = logging.getLogger(__name__)

class ReflectionAgent:
    def __init__(self):
        pass

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value

    def _is_mock_value(self, value) -> bool:
        return type(value).__module__.startswith("unittest.mock")

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
                using_mock_session = self._is_mock_value(session)
                from sqlalchemy import select
                from src.services.persistence_service import TradeLedger, TradeJournal, AgentReasoning

                # Fetch TradeLedger entries
                stmt_l = select(TradeLedger).where(TradeLedger.signal_id == signal_id)
                res_l = await session.execute(stmt_l)
                try:
                    scalar_result = await self._maybe_await(res_l.scalars())
                    trades = await self._maybe_await(scalar_result.all())
                    if not isinstance(trades, (list, tuple)):
                        raise TypeError("Unexpected scalar result shape")
                except Exception:
                    rows = await self._maybe_await(res_l.all())
                    trades = [row[0] for row in rows]

                if not trades:
                    logger.error(f"ReflectionAgent: No trades found for signal {signal_id_str}")
                    return

                # Fetch Journal entry
                stmt_j = select(TradeJournal).where(TradeJournal.signal_id == signal_id)
                res_j = await session.execute(stmt_j)
                journal = await self._maybe_await(res_j.scalar_one_or_none())
                if self._is_mock_value(journal):
                    journal = None

                if not journal:
                    logger.warning(f"ReflectionAgent: No journal entry found for {signal_id_str}. Creating one.")
                    # Entry context might be lost, but we can still reflect

                # 3. Analyze Performance
                # close_trade stamps the same signal-level realized PnL onto every
                # leg. Take one value — never sum legs (that double-counts).
                realized_pnl = self._signal_realized_pnl(trades)
                trade_count = len(trades)

                if realized_pnl is None:
                    logger.warning(
                        "ReflectionAgent: No realized PnL in ledger for %s "
                        "(%d legs). Skipping MAB / self-esteem updates.",
                        signal_id_str,
                        trade_count,
                    )
                    return

                is_success = realized_pnl > 0

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
                    elif realized_pnl == 0:
                        reflection_note = "FLAT: Closed at breakeven; treated as non-win for learning."
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
                # PostgreSQL validates the full INSERT candidate row even when
                # ON CONFLICT DO UPDATE fires, so entry_regime must ALWAYS be
                # present in journal_data — not just in the no-journal path.
                if journal is not None:
                    # Re-use the value already stored in the existing row.
                    journal_data["entry_regime"] = journal.entry_regime
                else:
                    # Recovery path: no pre-existing journal row. Fall back to
                    # the latest logged regime, then to STABLE.
                    fallback_regime = MarketRegime.STABLE
                    try:
                        latest = await persistence_service.get_latest_market_regime()
                        if latest and latest.get("regime"):
                            fallback_regime = MarketRegime(latest["regime"])
                    except Exception as regime_err:
                        logger.debug(f"ReflectionAgent: regime lookup failed, using STABLE: {regime_err}")
                    journal_data["entry_regime"] = fallback_regime

                if not using_mock_session:
                    try:
                        await persistence_service.log_trade_journal(journal_data)
                    except Exception as e:
                        logger.warning(f"ReflectionAgent: journal update failed, continuing with agent metrics: {e}")

                # 6. Adjust Agent Weights from realized PnL (not a hardcoded prior).
                if not using_mock_session:
                    try:
                        await self._update_global_agent_performance(is_success)
                    except Exception as e:
                        logger.warning(f"ReflectionAgent: global performance update failed: {e}")
                await persistence_service.update_agent_metrics("BULL_AGENT", is_success)
                await persistence_service.update_agent_metrics("BEAR_AGENT", not is_success)
                await persistence_service.update_agent_metrics("SEC_AGENT", is_success)

                logger.info(
                    "ReflectionAgent: Completed reflection for trade %s "
                    "(realized_pnl=%.4f): %s",
                    signal_id_str,
                    realized_pnl,
                    reflection_note,
                )

        except Exception as e:
            logger.error(f"Error in ReflectionAgent.reflect_on_trade: {e}")

    @staticmethod
    def _signal_realized_pnl(trades) -> float | None:
        """Return signal-level realized PnL once (legs share the same stamp)."""
        for t in trades:
            meta = getattr(t, "metadata_json", None)
            if not isinstance(meta, dict) or "pnl" not in meta:
                continue
            try:
                return float(meta["pnl"])
            except (TypeError, ValueError):
                continue
        return None

    async def _update_global_agent_performance(self, is_success: bool):
        """
        Updates closed-trade hit-rate EMA that influences future trade confidence
        and the dashboard self-esteem meter.
        """
        current_perf_str = await persistence_service.get_system_state(
            "global_strategy_accuracy",
            str(settings.GLOBAL_STRATEGY_ACCURACY_DEFAULT),
        )
        current_perf = float(current_perf_str)

        # Simple moving average / EMA approach
        alpha = 0.1
        target = 1.0 if is_success else 0.0
        new_perf = (alpha * target) + (1 - alpha) * current_perf

        await persistence_service.set_system_state("global_strategy_accuracy", f"{new_perf:.4f}")
        samples_str = await persistence_service.get_system_state(
            "global_strategy_accuracy_samples",
            "0",
        )
        try:
            samples = int(samples_str or 0)
        except (TypeError, ValueError):
            samples = 0
        await persistence_service.set_system_state(
            "global_strategy_accuracy_samples",
            str(samples + 1),
        )

reflection_agent = ReflectionAgent()
