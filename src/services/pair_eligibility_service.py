"""Pair eligibility gate for the Kalman pairs-trading universe.

Why this exists
---------------
Adding tickers from new sessions (HK, EU, LSE) is tempting because it gives the
bot more "uptime", but most cross-region pairs do not cointegrate in any
economically useful sense — FX moves and macro regime divergence dominate the
residual that the Kalman filter is supposed to mean-revert. Even when
cointegration holds, hidden trading costs (UK stamp duty 0.5 %, Trading 212 FX
fee 0.15 % per conversion, wider HK spreads) often exceed the statistical
edge.

This service centralises the rules that decide whether a candidate pair is
admissible to the live universe at all, before a Kalman filter is even
allocated. The rules are:

1. Both tickers must trade in the same session (same `market_id`).
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
from typing import Optional

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
) -> EligibilityResult:
    """Decide whether (ticker_a, ticker_b) should be admitted to the universe.

    The function is pure (no I/O) and deterministic. It is safe to call from
    inside `initialize_pairs` or from a unit test.

    Parameters
    ----------
    account_currency:
        Settlement currency of the user's account. Used to estimate FX costs.
        Portuguese-resident T212 users typically have EUR accounts.
    max_round_trip_cost_pct:
        Hard ceiling on the estimated total round-trip cost of opening and
        closing the pair. Pairs with cost above this are rejected even if
        their cointegration p-value is great, because the strategy cannot
        beat the friction.
    block_cross_currency / block_lse_short_hold:
        Toggles wired through `Settings` so the operator can override per
        deployment.
    """
    a = ticker_a.strip().upper()
    b = ticker_b.strip().upper()

    # Crypto pairs always pass — different rule set and different venue.
    if _is_crypto(a) and _is_crypto(b):
        cost = estimate_round_trip_cost_pct(a, b, account_currency=account_currency)
        return EligibilityResult(True, "crypto_pair", cost)

    if _is_crypto(a) ^ _is_crypto(b):
        return EligibilityResult(
            False,
            "mixed_crypto_equity_pair_not_supported",
            0.0,
        )

    if not same_session(a, b):
        v_a = get_venue_profile(a).market_id
        v_b = get_venue_profile(b).market_id
        return EligibilityResult(
            False,
            f"different_sessions:{v_a}_vs_{v_b}",
            0.0,
        )

    if block_cross_currency and not same_currency(a, b):
        c_a = get_venue_profile(a).currency
        c_b = get_venue_profile(b).currency
        return EligibilityResult(
            False,
            f"cross_currency:{c_a}_vs_{c_b}",
            0.0,
        )

    if block_lse_short_hold:
        v_a = get_venue_profile(a).market_id
        v_b = get_venue_profile(b).market_id
        if v_a == "LSE" or v_b == "LSE":
            # Stamp duty 0.5 % per buy leg is brutal for sub-week holds; skip.
            return EligibilityResult(
                False,
                "lse_excluded_due_to_stamp_duty",
                0.0,
            )

    cost = estimate_round_trip_cost_pct(a, b, account_currency=account_currency)
    if cost > max_round_trip_cost_pct:
        return EligibilityResult(
            False,
            f"cost_above_ceiling:{cost:.4f}>{max_round_trip_cost_pct:.4f}",
            cost,
        )

    return EligibilityResult(True, "admitted", cost)


def filter_pair_universe(
    pairs: list[dict],
    *,
    account_currency: str = "EUR",
    max_round_trip_cost_pct: float = 0.0125,
    block_cross_currency: bool = True,
    block_lse_short_hold: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Split a candidate universe into (admitted, rejected) lists.

    Each `pairs` entry is expected to be a dict with `ticker_a` / `ticker_b`
    keys, matching the existing `settings.ARBITRAGE_PAIRS` schema. Each
    rejected entry gets a `rejection` field added with the eligibility
    verdict for downstream logging.
    """
    admitted: list[dict] = []
    rejected: list[dict] = []
    for pair in pairs:
        verdict = evaluate_pair(
            pair["ticker_a"],
            pair["ticker_b"],
            account_currency=account_currency,
            max_round_trip_cost_pct=max_round_trip_cost_pct,
            block_cross_currency=block_cross_currency,
            block_lse_short_hold=block_lse_short_hold,
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
                "PAIR ELIGIBILITY: rejected %s/%s — %s",
                pair["ticker_a"],
                pair["ticker_b"],
                verdict.reason,
            )
    return admitted, rejected


__all__ = [
    "EligibilityResult",
    "evaluate_pair",
    "filter_pair_universe",
]
