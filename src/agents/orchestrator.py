from typing import TypedDict
import asyncio
import numpy as np
import logging
from types import SimpleNamespace
from src.agents.bull_agent import bull_agent
from src.agents.bear_agent import bear_agent
from src.agents.whale_watcher_agent import whale_watcher_agent
from src.agents.portfolio_manager_agent import portfolio_manager_agent
from src.agents.macro_economic_agent import macro_economic_agent
from src.services.redis_service import redis_service
from src.services.telemetry_service import telemetry_service
from src.services.persistence_service import persistence_service
from src.config import settings

logger = logging.getLogger(__name__)

# Sprint J: Map of Leaders for Sector Panic Detection
BEACON_ASSETS = {
    "Technology": "NVDA",  # Sector Leader for Tech
    "Finance": "JPM",       # Sector Leader for Banking
    "Energy": "XOM",        # Sector Leader for Energy
    "Consumer": "KO"        # Sector Leader for Consumer Staples/Growth
}


def _is_crypto_symbol(ticker: str) -> bool:
    return "-USD" in str(ticker or "").upper()


class AgentState(TypedDict):
    signal_context: dict
    bull_verdict: dict
    bear_verdict: dict
    fundamental_verdict: dict
    whale_verdict: dict
    final_confidence: float
    final_verdict: str

class Orchestrator:
    """
    Refactored Orchestrator that executes the multi-agent debate
    without requiring the langgraph library.
    Now uses cached fundamental scores to avoid high latency RAG calls.
    """
    def __init__(self):
        from src.models.persistence import PersistenceManager

        self.legacy_persistence = PersistenceManager()
        self.fundamental_analyst = SimpleNamespace(analyze_ticker=lambda *args, **kwargs: None)

    async def _get_system_state(self, key: str, default=None):
        try:
            return await persistence_service.get_system_state(key, default)
        except Exception as e:
            logger.warning("Postgres system_state unavailable, using SQLite fallback: %s", e)
            return self.legacy_persistence.get_system_state(key, default)

    async def _set_system_state(self, key: str, value):
        try:
            await persistence_service.set_system_state(key, value)
        except Exception as e:
            logger.warning("Postgres system_state write unavailable, using SQLite fallback: %s", e)
            self.legacy_persistence.set_system_state(key, value)

    async def _get_agent_metrics(self, agent_name: str):
        try:
            return await persistence_service.get_agent_metrics(agent_name)
        except Exception:
            return (1, 1)

    async def ainvoke(self, input_data: dict) -> dict:
        from src.services.persistence_service import persistence_service

        # FR-004: Block new entries if in DEGRADED_MODE
        operational_status = await self._get_system_state("operational_status", "NORMAL")

        state: AgentState = {
            "signal_context": input_data["signal_context"],
            "bull_verdict": {},
            "bear_verdict": {},
            "fundamental_verdict": {},
            "whale_verdict": {},
            "final_confidence": 0.0,
            "final_verdict": ""
        }

        if operational_status == "DEGRADED_MODE":
            state["final_confidence"] = 0.0
            state["final_verdict"] = "VETO: DEGRADED_MODE active due to consecutive API failures. Entry blocked."
            return state

        ticker_a = state['signal_context']['ticker_a']
        ticker_b = state['signal_context']['ticker_b']
        pair_id = f"{ticker_a}_{ticker_b}"
        crypto_pair = _is_crypto_symbol(ticker_a) and _is_crypto_symbol(ticker_b)

        # --- PHASE 0: MACRO REGIME CHECK (FAIL-FAST) ---
        # If the Sector Leader is in a panic state, we abort before firing up the LLM Agents
        # Default sector is "Unassigned" -> SPY (market-wide beacon). Previously defaulted
        # to "Technology" -> NVDA, which silently vetoed every unmapped pair on NVDA panic
        # days (incident: 2026-04-30 NVDA -4.63%).
        sector = state['signal_context'].get('sector', 'Unassigned')
        beacon = BEACON_ASSETS.get(sector, "SPY")

        # R3 fix (2026-04-19): get_ticker_regime returns a bare string literal
        # ("BULLISH" | "BEARISH" | "EXTREME_VOLATILITY"), not a dict. Previously
        # calling .get() on a string raised AttributeError on every signal.
        regime = await macro_economic_agent.get_ticker_regime(beacon)

        if regime == "EXTREME_VOLATILITY":
            msg = f"CRITICAL VETO: Sector Leader {beacon} is {regime}. Aborting analysis to protect capital."
            logger.warning("[ORCHESTRATOR] %s - %s", pair_id, msg)
            telemetry_service.broadcast("orchestrator_veto", {"pair": pair_id, "reason": msg})
            return {"final_confidence": 0.0, "final_verdict": msg, "signal_context": state['signal_context']}

        logger.info("[ORCHESTRATOR] %s - Macro Regime OK (%s). Starting Agent Swarm...", pair_id, regime)

        # --- PHASE 1: AGENT SWARM ---
        # Evaluate bull/bear themes and fetch fundamental health scores

        score_task_a = asyncio.sleep(0, result=None) if crypto_pair else redis_service.get_fundamental_score(ticker_a)
        score_task_b = asyncio.sleep(0, result=None) if crypto_pair else redis_service.get_fundamental_score(ticker_b)
        results = await asyncio.gather(
            bull_agent.evaluate(state['signal_context']),
            bear_agent.evaluate(state['signal_context']),
            score_task_a,
            score_task_b,
            whale_watcher_agent.evaluate(state['signal_context']),
            return_exceptions=True
        )

        bull_results, bear_results, score_data_a, score_data_b, whale_results = results

        # Broadcast intermediate agent thoughts
        sig_id = state['signal_context'].get('signal_id', 'N/A')

        telemetry_service.broadcast("thought", {
            "agent_name": "BULL_AGENT",
            "signal_id": sig_id,
            "thought": str(bull_results.get("reasoning", "Analysis complete")) if not isinstance(bull_results, Exception) else f"Error: {bull_results}",
            "verdict": "BULLISH"
            if not isinstance(bull_results, Exception)
            and bull_results.get("confidence", 0) > settings.ORCH_AGENT_CONFIDENCE_THRESHOLD
            else "NEUTRAL"
        })

        telemetry_service.broadcast("thought", {
            "agent_name": "BEAR_AGENT",
            "signal_id": sig_id,
            "thought": str(bear_results.get("reasoning", "Analysis complete")) if not isinstance(bear_results, Exception) else f"Error: {bear_results}",
            "verdict": "BEARISH"
            if not isinstance(bear_results, Exception)
            and bear_results.get("confidence", 0) > settings.ORCH_AGENT_CONFIDENCE_THRESHOLD
            else "NEUTRAL"
        })

        whale_inactive = (
            not isinstance(whale_results, Exception)
            and whale_results.get("status") == "inactive"
        )
        telemetry_service.broadcast("thought", {
            "agent_name": "WHALE_WATCHER",
            "signal_id": sig_id,
            "thought": str(whale_results.get("reasoning", "Whale context read complete"))
            if not isinstance(whale_results, Exception)
            else f"Error: {whale_results}",
            "verdict": "INACTIVE"
            if whale_inactive
            else (
                "VETO"
                if not isinstance(whale_results, Exception) and whale_results.get("veto")
                else (
                    "SUPPORT"
                    if not isinstance(whale_results, Exception)
                    and whale_results.get("confidence_delta", 0.0) > 0
                    else (
                        "RISK"
                        if not isinstance(whale_results, Exception)
                        and whale_results.get("confidence_delta", 0.0) < 0
                        else "NEUTRAL"
                    )
                )
            )
        })

        # Track if any major API timeout occurred for circuit breaker
        timeout_occurred = False

        # Handle Bull Agent results
        if isinstance(bull_results, Exception):
            logger.warning("Orchestrator Bull Agent failed: %s", bull_results)
            if isinstance(bull_results, asyncio.TimeoutError): timeout_occurred = True
            state['bull_verdict'] = {"confidence": 0.0, "error": str(bull_results)}
        else:
            state['bull_verdict'] = bull_results

        # Handle Bear Agent results
        if isinstance(bear_results, Exception):
            logger.warning("Orchestrator Bear Agent failed: %s", bear_results)
            if isinstance(bear_results, asyncio.TimeoutError): timeout_occurred = True
            state['bear_verdict'] = {"confidence": 0.0, "error": str(bear_results)}
        else:
            state['bear_verdict'] = bear_results

        if isinstance(whale_results, Exception):
            logger.warning("Orchestrator Whale Watcher failed: %s", whale_results)
            if isinstance(whale_results, asyncio.TimeoutError): timeout_occurred = True
            state['whale_verdict'] = {
                "confidence_delta": 0.0,
                "confidence_multiplier": 1.0,
                "veto": False,
                "whale_score": 0.0,
                "error": str(whale_results),
            }
        else:
            state['whale_verdict'] = whale_results

        unknown_fundamental_tickers = []

        # Handle Fundamental Score A (Redis)
        score_a = settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE
        if not crypto_pair:
            if isinstance(score_data_a, Exception):
                logger.warning("Orchestrator Redis read failed for %s: %s", ticker_a, score_data_a)
                unknown_fundamental_tickers.append(ticker_a)
            elif score_data_a:
                score_a = score_data_a.get("score", settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE)
            else:
                logger.warning(
                    "CRITICAL - Fundamental cache miss for %s. Defaulting to %s.",
                    ticker_a, settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE
                )
                telemetry_service.broadcast("fundamental_cache_miss", {"ticker": ticker_a, "priority": "HIGH"})
                unknown_fundamental_tickers.append(ticker_a)

        # Handle Fundamental Score B (Redis)
        score_b = settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE
        if not crypto_pair:
            if isinstance(score_data_b, Exception):
                logger.warning("Orchestrator Redis read failed for %s: %s", ticker_b, score_data_b)
                unknown_fundamental_tickers.append(ticker_b)
            elif score_data_b:
                score_b = score_data_b.get("score", settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE)
            else:
                logger.warning(
                    "CRITICAL - Fundamental cache miss for %s. Defaulting to %s.",
                    ticker_b, settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE
                )
                telemetry_service.broadcast("fundamental_cache_miss", {"ticker": ticker_b, "priority": "HIGH"})
                unknown_fundamental_tickers.append(ticker_b)

        # Paper mode must not fail-closed on SEC cache misses — operators validate
        # execution in shadow mode without the SEC worker. LIVE_CAPITAL_DANGER
        # still enforces entropy baselines at startup; fundamental vetoes apply
        # only when real capital is at risk (PAPER_TRADING=false).
        live_fundamental_guard_active = not settings.PAPER_TRADING
        live_unknown_fundamental_state = (
            not crypto_pair
            and
            live_fundamental_guard_active
            and bool(unknown_fundamental_tickers)
        )
        low_fundamental_score = (
            not crypto_pair
            and (
            score_a < settings.ORCH_FUNDAMENTAL_VETO_SCORE
            or score_b < settings.ORCH_FUNDAMENTAL_VETO_SCORE
            )
        )
        state["fundamental_verdict"] = {
            "applicable": not crypto_pair,
            "score_a": score_a,
            "score_b": score_b,
            "missing_tickers": unknown_fundamental_tickers,
            "veto": live_unknown_fundamental_state or low_fundamental_score,
        }
        if live_unknown_fundamental_state:
            state["fundamental_verdict"]["reason"] = "unknown fundamental state in live mode"
        elif low_fundamental_score:
            state["fundamental_verdict"]["reason"] = "low structural integrity score"

        telemetry_service.broadcast("thought", {
            "agent_name": "SEC_AGENT",
            "signal_id": sig_id,
            "thought": (
                "SEC/fundamental filing score not applicable for crypto pair."
                if crypto_pair
                else f"Unknown fundamental state for {', '.join(unknown_fundamental_tickers)}"
                if live_unknown_fundamental_state
                else f"Structural Integrity Scores: {ticker_a}={score_a}, {ticker_b}={score_b}"
            ),
            "verdict": "VETO"
            if state["fundamental_verdict"]["veto"]
            else "NEUTRAL"
        })

        # FR-003: Circuit Breaker Logic (Persistent)
        consecutive_timeouts_str = await self._get_system_state("consecutive_api_timeouts", "0")
        consecutive_timeouts = int(consecutive_timeouts_str)

        if timeout_occurred:
            consecutive_timeouts += 1
            await self._set_system_state("consecutive_api_timeouts", str(consecutive_timeouts))
            if consecutive_timeouts >= 3:
                await self._set_system_state("operational_status", "DEGRADED_MODE")
                logger.critical("Circuit Breaker Tripped! Entering DEGRADED_MODE after %d consecutive timeouts.", consecutive_timeouts)
        else:
            # Reset on full successful loop. O1 fix: also restore operational_status so a
            # transient API blip earlier in the session does not freeze the bot for the day.
            await self._set_system_state("consecutive_api_timeouts", "0")
            await self._set_system_state("operational_status", "NORMAL")

        # FR-010: Feedback Loop Integration
        # Scale confidence based on recent historical performance (Global Strategy Accuracy)
        accuracy_str = await self._get_system_state(
            "global_strategy_accuracy",
            str(settings.GLOBAL_STRATEGY_ACCURACY_DEFAULT),
        )
        global_accuracy = float(accuracy_str)

        performance_multiplier = 1.0
        low_accuracy_warning = False
        if global_accuracy < settings.ORCH_ACCURACY_LOW_THRESHOLD:
            low_accuracy_warning = True
        elif global_accuracy > settings.ORCH_ACCURACY_HIGH_THRESHOLD:
            performance_multiplier = settings.ORCH_ACCURACY_HIGH_MULTIPLIER

        # 3. Aggregation Logic with VETO
        bull_conf = state['bull_verdict']['confidence']
        bear_conf = state['bear_verdict']['confidence']

        # Absolute VETO if live mode cannot prove fundamental state or integrity is too low.
        if live_unknown_fundamental_state:
            state["final_confidence"] = 0.0
            missing_tickers = ", ".join(unknown_fundamental_tickers)
            state["final_verdict"] = (
                f"VETO: Unknown fundamental state for {missing_tickers}. "
                "Entry blocked in live mode."
            )
        elif low_fundamental_score:
            state["final_confidence"] = 0.0
            veto_reason = f"VETO: Low Structural Integrity. {ticker_a}: {score_a}, {ticker_b}: {score_b}"
            state["final_verdict"] = veto_reason
        elif state["whale_verdict"].get("veto"):
            state["final_confidence"] = 0.0
            state["final_verdict"] = state["whale_verdict"].get(
                "reasoning",
                "VETO: Whale watcher flagged conflicting exchange flow.",
            )
        else:
            # --- PHASE 2: MULTI-ARMED BANDIT (ADAPTIVE LEARNING) ---
            bull_s, bull_f = await self._get_agent_metrics("BULL_AGENT")
            bear_s, bear_f = await self._get_agent_metrics("BEAR_AGENT")
            sec_s, sec_f = await self._get_agent_metrics("SEC_AGENT")

            bull_weight = np.random.beta(max(1, bull_s), max(1, bull_f))
            bear_weight = np.random.beta(max(1, bear_s), max(1, bear_f))
            sec_weight = np.random.beta(max(1, sec_s), max(1, sec_f))
            total_w = bull_weight + bear_weight if crypto_pair else bull_weight + bear_weight + sec_weight

            w_bull = bull_weight / total_w
            w_bear = bear_weight / total_w
            w_sec = 0.0 if crypto_pair else sec_weight / total_w

            logger.info(
                "[ORCHESTRATOR] %s - MAB adaptive weights: Bull=%.2f, Bear=%.2f, SEC=%s",
                pair_id,
                w_bull,
                w_bear,
                "N/A" if crypto_pair else f"{w_sec:.2f}",
            )

            avg_integrity = 0.0 if crypto_pair else (score_a + score_b) / 200.0

            # --- PHASE 3: PORTFOLIO SORTINO OPTIMIZATION ---
            p_advice_a = await portfolio_manager_agent.get_optimization_advice(ticker_a)
            p_advice_b = await portfolio_manager_agent.get_optimization_advice(ticker_b)

            agent_weight_total = bull_weight + bear_weight
            agent_consensus_conf = (
                ((bull_conf * bull_weight) + ((1 - bear_conf) * bear_weight)) / agent_weight_total
            )
            weighted_conf = (bull_conf * w_bull) + ((1 - bear_conf) * w_bear) + (avg_integrity * w_sec)
            neutral_fundamental_score = (
                not crypto_pair
                and score_a == settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE
                and score_b == settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE
            )
            base_conf = max(weighted_conf, agent_consensus_conf) if neutral_fundamental_score else weighted_conf
            final_conf = base_conf * performance_multiplier
            sec_weight_label = "N/A" if crypto_pair else f"{w_sec:.2f}"
            portfolio_warning = not p_advice_a["is_recommended"] or not p_advice_b["is_recommended"]

            if portfolio_warning:
                state["final_verdict"] = f"MAB Weighted: Bull({w_bull:.2f}), Bear({w_bear:.2f}), SEC({sec_weight_label}) | SORTINO WARNING: Pair-spread; no long-only confidence penalty (Imp A:{p_advice_a['improvement']:.3f}, B:{p_advice_b['improvement']:.3f})"
                logger.info("[ORCHESTRATOR] %s - Portfolio warning informational for pair spread.", pair_id)
            else:
                state["final_verdict"] = f"MAB Weighted: Bull({w_bull:.2f}), Bear({w_bear:.2f}), SEC({sec_weight_label}) | SORTINO OPTIMAL (+{max(p_advice_a['improvement'], p_advice_b['improvement']):.3f})"
                logger.info("[ORCHESTRATOR] %s - Portfolio Logic: Optimal addition identified.", pair_id)

            if low_accuracy_warning:
                state["final_verdict"] += (
                    f" | GLOBAL ACCURACY WARNING: {global_accuracy:.2f} below "
                    f"{settings.ORCH_ACCURACY_LOW_THRESHOLD:.2f}; no confidence penalty applied"
                )

            whale_multiplier = float(state["whale_verdict"].get("confidence_multiplier", 1.0))
            whale_delta = float(state["whale_verdict"].get("confidence_delta", 0.0))
            whale_score = float(state["whale_verdict"].get("whale_score", 0.0))
            if whale_multiplier != 1.0 or whale_delta != 0.0 or whale_score != 0.0:
                final_conf *= whale_multiplier
                state["final_verdict"] += (
                    f" | WHALE score={whale_score:.2f} delta={whale_delta:+.2f}"
                )
                logger.info(
                    "[ORCHESTRATOR] %s - Whale watcher multiplier applied: %.2f (score=%.2f)",
                    pair_id,
                    whale_multiplier,
                    whale_score,
                )

            state["final_confidence"] = max(0.0, min(1.0, final_conf))

        # FR-004, US2: Broadcast final verdict to Telemetry
        mood = "IDLE"
        if timeout_occurred:
            mood = "GLITCH"
        elif state["final_confidence"] > 0.8:
            mood = "HAPPY"
        elif state["final_confidence"] < 0.3:
            mood = "DOUBT"

        telemetry_service.broadcast("bot_state", {"state": mood})

        telemetry_service.broadcast("thought", {
            "agent_name": "ORCHESTRATOR",
            "signal_id": state['signal_context'].get('signal_id', 'N/A'),
            "ticker_pair": f"{ticker_a}_{ticker_b}",
            "thought": state["final_verdict"],
            "verdict": "EXECUTE"
            if state["final_confidence"] > settings.ORCH_AGENT_CONFIDENCE_THRESHOLD
            else "REJECT"
        })

        # Sprint H: Sector Gravity Check (Beacon Asset)
        TICKER_BEACONS = {
            "AAPL": "NVDA", "MSFT": "NVDA", "AMD": "NVDA", "TSMC": "NVDA", "SMCI": "NVDA",
            "BAC": "JPM", "GS": "JPM", "MS": "JPM", "C": "JPM",
            "CVX": "XOM", "BP": "XOM",
            "PEP": "KO", "PG": "KO",
        }

        for ticker in [ticker_a, ticker_b]:
            beacon = TICKER_BEACONS.get(ticker)
            if beacon:
                regime = await macro_economic_agent.get_ticker_regime(beacon)
                if regime == "EXTREME_VOLATILITY":
                    state["final_confidence"] = 0.0
                    state["final_verdict"] = f"CRITICAL VETO: Sector Leader {beacon} in Flash Crash! Aborting trade for {ticker}."
                    break

        return state

orchestrator = Orchestrator()
