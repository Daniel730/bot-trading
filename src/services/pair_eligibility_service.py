"""Pair eligibility gate for the Kalman pairs-trading universe.

Why this exists
---------------
Adding tickers from new sessions (HK, EU, LSE) is tempting because it gives the
bot more "uptime", but most cross-region pairs do not cointegrate in any
economically useful sense - FX moves and macro regime divergence dominate the
residual that the Kalman filter is supposed to mean-revert. Even when
cointegration holds, hidden trading costs (UK stamp duty 0.5 %, Trading 212 FX
fee 0.15 % per conversion, wider HK spreads) often exceed the statistical
edge.

This service centralises the rules that decide whether a candidate pair is
admissible to the live universe at all, before a Kalman filter is even
allocated. The rules are:

1. Both tickers must trade in the same session (same `market_id`), unless the
   `allow_eu_continental_overlap` flag is on, in which case the EU_CONTINENTAL
   session group acts as one session.
2. Both tickers must settle in the same currency, OR cross-currency must be
   explicitly enabled via settings.
3. Estimated round-trip cost must be below the configured ceiling. This stops
   us from admitting pairs whose statistical edge would be eaten alive by
   FX + stamp duty + spread before any z-score signal can fire.
4. LSE pairs may be excluded for short-hold strategies because of the 0.5 %
   SDRT (UK stamp duty) on every buy leg.

Crypto pairs are admitted unconditionally because they share a single
24/7 session and have a different cost structure routed through Web3.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging

from src.services.venue_metadata import (
    estimate_round_trip_cost_pct,
    get_venue_profile,
    same_currency,
    same_session,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EligibilityResult:
    """Verdict for a candidate pair."""

    admit: bool
    reason: str
    estimated_cost_pct: float

    def to_dict(self) -> dict:
        return {
            "admit": self.admit,
            "reason": self.reason,
            "estimated_cost_pct": round(self.estimated_cost_pct, 6),
        }


def _is_crypto(ticker: str) -> bool:
    return "-USD" in ticker.upper()


def evaluate_pair(
    ticker_a: str,
    ticker_b: str,
    *,
    account_currency: str = "EUR",
    max_round_trip_cost_pct: float = 0.0125,
    block_cross_currency: bool = True,
    block_lse_short_hold: bool = True,
    allow_eu_continental_overlap: bool = False,
) -> EligibilityResult:
    """Decide whether (ticker_a, ticker_b) should be admitted to the universe.

    Spec 038 - allow_eu_continental_overlap relaxes the session rule so XETRA,
    EURONEXT, BORSA_ITALIANA and SIX are treated as the same session group.
    """
    a = ticker_a.strip().upper()
    b = ticker_b.strip().upper()

    if _is_crypto(a) and _is_crypto(b):
        cost = estimate_round_trip_cost_pct(a, b, account_currency=account_currency)
        return EligibilityResult(True, "crypto_pair", cost)

    if _is_crypto(a) ^ _is_crypto(b):
        return EligibilityResult(False, "mixed_crypto_equity_pair_not_supported", 0.0)

    if not same_session(a, b, allow_eu_continental_overlap=allow_eu_continental_overlap):
        v_a = get_venue_profile(a).market_id
        v_b = get_venue_profile(b).market_id
        return EligibilityResult(False, f"different_sessions:{v_a}_vs_{v_b}", 0.0)

    if block_cross_currency and not same_currency(a, b):
        c_a = get_venue_profile(a).currency
        c_b = get_venue_profile(b).currency
        return EligibilityResult(False, f"cross_currency:{c_a}_vs_{c_b}", 0.0)

    if block_lse_short_hold:
        v_a = get_venue_profile(a).market_id
        v_b = get_venue_profile(b).market_id
        if v_a == "LSE" or v_b == "LSE":
            return EligibilityResult(False, "lse_excluded_due_to_stamp_duty", 0.0)

    cost = estimate_round_trip_cost_pct(a, b, account_currency=account_currency)
    if cost > max_round_trip_cost_pct:
        return EligibilityResult(
            False,
            f"cost_above_ceiling:{cost:.4f}>{max_round_trip_cost_pct:.4f}",
            cost,
        )

    return EligibilityResult(True, "admitted", cost)


def filter_pair_universe(
    pairs: list,
    *,
    account_currency: str = "EUR",
    max_round_trip_cost_pct: float = 0.0125,
    block_cross_currency: bool = True,
    block_lse_short_hold: bool = True,
    allow_eu_continental_overlap: bool = False,
):
    """Split a candidate universe into (admitted, rejected) lists."""
    admitted = []
    rejected = []
    for pair in pairs:
        verdict = evaluate_pair(
            pair["ticker_a"],
            pair["ticker_b"],
            account_currency=account_currency,
            max_round_trip_cost_pct=max_round_trip_cost_pct,
            block_cross_currency=block_cross_currency,
            block_lse_short_hold=block_lse_short_hold,
            allow_eu_continental_overlap=allow_eu_continental_overlap,
        )
        if verdict.admit:
            enriched = dict(pair)
            enriched["estimated_cost_pct"] = verdict.estimated_cost_pct
            admitted.append(enriched)
        else:
            enriched = dict(pair)
            enriched["rejection"] = verdict.to_dict()
            rejected.append(enriched)
            logger.info(
                "PAIR ELIGIBILITY: rejected %s/%s - %s",
                pair["ticker_a"],
                pair["ticker_b"],
                verdict.reason,
            )
    return admitted, rejected


__all__ = ["EligibilityResult", "evaluate_pair", "filter_pair_universe"]
