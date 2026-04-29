import logging

from src.config import settings
from src.services.telemetry_service import telemetry_service
from src.services.whale_watcher_service import whale_watcher_service

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class WhaleWatcherAgent:
    """
    Reads cached whale context and adjusts a pair signal conservatively.

    Positive single_leg_pressure_score means bullish pressure for that asset
    (exchange outflows, accumulation). Negative means sell pressure
    (exchange inflows). The agent aligns those pressures with the pair-trade
    legs inferred from z_score.
    """

    agent_name = "WHALE_WATCHER"

    def neutral(self, reasoning: str) -> dict:
        return {
            "confidence_delta": 0.0,
            "confidence_multiplier": 1.0,
            "veto": False,
            "whale_score": 0.0,
            "reasoning": reasoning,
        }

    async def evaluate(self, signal_context: dict) -> dict:
        if not settings.WHALE_WATCHER_ENABLED:
            return self.neutral("Whale watcher disabled by configuration.")

        ticker_a = signal_context.get("ticker_a", "")
        ticker_b = signal_context.get("ticker_b", "")
        if not (
            whale_watcher_service.is_crypto_ticker(ticker_a)
            and whale_watcher_service.is_crypto_ticker(ticker_b)
        ):
            return self.neutral("Whale watcher is crypto-only; no adjustment for this pair.")

        z_score = float(signal_context.get("z_score") or 0.0)
        if z_score == 0.0:
            return self.neutral("No pair direction available; whale context left neutral.")

        context = await whale_watcher_service.get_cached_pair_context(ticker_a, ticker_b)
        verdict = self._score_pair_context(ticker_a, ticker_b, z_score, context)

        telemetry_service.broadcast("whale_context", {
            "signal_id": signal_context.get("signal_id", "N/A"),
            "ticker_pair": f"{ticker_a}_{ticker_b}",
            "whale_score": verdict["whale_score"],
            "confidence_delta": verdict["confidence_delta"],
            "veto": verdict["veto"],
        })

        return verdict

    def _score_pair_context(
        self,
        ticker_a: str,
        ticker_b: str,
        z_score: float,
        context: dict,
    ) -> dict:
        summary_a = context.get("summary_a") or whale_watcher_service.empty_summary(ticker_a)
        summary_b = context.get("summary_b") or whale_watcher_service.empty_summary(ticker_b)
        stablecoin_summary = context.get("stablecoin_summary") or whale_watcher_service.empty_summary("STABLECOIN")

        if (
            summary_a.get("event_count", 0) == 0
            and summary_b.get("event_count", 0) == 0
            and stablecoin_summary.get("event_count", 0) == 0
        ):
            return self.neutral("No cached whale events inside the rolling window.")

        # z > 0 means ticker A is rich vs B, so the pair trade shorts A and longs B.
        exposure_a = -1.0 if z_score > 0 else 1.0
        exposure_b = 1.0 if z_score > 0 else -1.0
        long_leg = ticker_b if z_score > 0 else ticker_a
        short_leg = ticker_a if z_score > 0 else ticker_b

        veto_reason = self._veto_reason(long_leg, short_leg, exposure_a, exposure_b, summary_a, summary_b)
        if veto_reason:
            return {
                "confidence_delta": -1.0,
                "confidence_multiplier": 0.0,
                "veto": True,
                "whale_score": -1.0,
                "reasoning": veto_reason,
                "context": context,
            }

        pressure_a = float(summary_a.get("single_leg_pressure_score") or 0.0)
        pressure_b = float(summary_b.get("single_leg_pressure_score") or 0.0)
        alignment_a = exposure_a * pressure_a
        alignment_b = exposure_b * pressure_b
        noise_penalty = max(
            float(summary_a.get("noise_penalty") or 0.0),
            float(summary_b.get("noise_penalty") or 0.0),
        )
        stablecoin_boost = 0.15 * float(stablecoin_summary.get("stablecoin_liquidity_score") or 0.0)
        whale_score = _clamp(((alignment_a + alignment_b) / 2.0) + stablecoin_boost - (0.25 * noise_penalty), -1.0, 1.0)

        if whale_score > 0:
            confidence_delta = whale_score * (settings.WHALE_WATCHER_SUPPORT_MULTIPLIER - 1.0)
        else:
            confidence_delta = whale_score * (1.0 - settings.WHALE_WATCHER_RISK_MULTIPLIER)
        confidence_delta = _clamp(
            confidence_delta,
            -(1.0 - settings.WHALE_WATCHER_RISK_MULTIPLIER),
            settings.WHALE_WATCHER_SUPPORT_MULTIPLIER - 1.0,
        )
        confidence_multiplier = _clamp(1.0 + confidence_delta, 0.0, settings.WHALE_WATCHER_SUPPORT_MULTIPLIER)

        if whale_score < -0.05:
            stance = "penalizes"
        elif whale_score > 0.05:
            stance = "supports"
        else:
            stance = "is neutral for"

        reasoning = (
            f"Whale context {stance} proposed Long {long_leg} / Short {short_leg}. "
            f"{ticker_a} pressure={pressure_a:.2f}, {ticker_b} pressure={pressure_b:.2f}, "
            f"noise={noise_penalty:.2f}, stablecoin_liquidity={stablecoin_boost:.2f}."
        )

        return {
            "confidence_delta": confidence_delta,
            "confidence_multiplier": confidence_multiplier,
            "veto": False,
            "whale_score": whale_score,
            "reasoning": reasoning,
            "context": context,
        }

    def _veto_reason(
        self,
        long_leg: str,
        short_leg: str,
        exposure_a: float,
        exposure_b: float,
        summary_a: dict,
        summary_b: dict,
    ) -> str:
        reason_a = self._summary_veto_reason(
            ticker=summary_a.get("symbol") or "",
            display_ticker=long_leg if exposure_a > 0 else short_leg,
            exposure=exposure_a,
            summary=summary_a,
        )
        if reason_a:
            return reason_a
        return self._summary_veto_reason(
            ticker=summary_b.get("symbol") or "",
            display_ticker=long_leg if exposure_b > 0 else short_leg,
            exposure=exposure_b,
            summary=summary_b,
        )

    def _summary_veto_reason(self, ticker: str, display_ticker: str, exposure: float, summary: dict) -> str:
        min_count = int(settings.WHALE_WATCHER_VETO_MIN_EVENTS)
        extreme_value = float(settings.WHALE_WATCHER_EXTREME_VALUE_USD)
        veto_score = float(settings.WHALE_WATCHER_VETO_SCORE)

        if exposure > 0:
            if (
                int(summary.get("exchange_inflow_count") or 0) >= min_count
                and float(summary.get("exchange_inflow_value_usd") or 0.0) >= extreme_value
                and float(summary.get("whale_exchange_inflow_score") or 0.0) >= veto_score
            ):
                return (
                    f"VETO: Rolling exchange inflows conflict with proposed long {display_ticker}; "
                    f"{summary.get('exchange_inflow_count')} events totaling "
                    f"${float(summary.get('exchange_inflow_value_usd') or 0.0):,.0f}."
                )
        else:
            if (
                int(summary.get("exchange_outflow_count") or 0) >= min_count
                and float(summary.get("exchange_outflow_value_usd") or 0.0) >= extreme_value
                and float(summary.get("whale_exchange_outflow_score") or 0.0) >= veto_score
            ):
                return (
                    f"VETO: Rolling exchange outflows conflict with proposed short {display_ticker}; "
                    f"{summary.get('exchange_outflow_count')} events totaling "
                    f"${float(summary.get('exchange_outflow_value_usd') or 0.0):,.0f}."
                )
        return ""


whale_watcher_agent = WhaleWatcherAgent()
