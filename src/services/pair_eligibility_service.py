"""Pair eligibility gate for the Kalman pairs-trading universe.

Why this exists
---------------
Adding tickers from new sessions (HK, EU, LSE) is tempting because it gives the
bot more "uptime", but most cross-region pairs do not cointegrate in any
economically useful sense - FX moves and macro regime divergence dominate the
residual that the Kalman filter is supposed to mean-revert. Even when
cointegration holds, hidden trading costs (UK stamp duty 0.5 %, FX
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
5. Operator denylist (default BTC/BCH both orders) is fail-closed so quarantine
   cannot be bypassed by a call site that forgets the scout/monitor pre-check.
6. Optional quality metrics — when callers supply hedge / correlation /
   cointegration p-value — must satisfy the same floors as pair discovery
   (`PAIR_DISCOVERY_MAX_ABS_HEDGE`, `PAIR_DISCOVERY_MIN_CORRELATION`,
   `PAIR_DISCOVERY_MAX_PVALUE`). Extreme hedge alone is also applied from
   pair dicts in ``filter_pair_universe`` (BTC/BCH-scale betas ~285).

Crypto pairs share a single 24/7 session. Broker-paper and live paths still
require both legs to be active on Alpaca before entering the scan universe.
Shadow paper (``PAPER_TRADING=true``) skips that broker asset check because
fills never hit Alpaca — otherwise placeholder/unauthorized keys empty the
entire universe and contradict paper-mode docs.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable, Optional

from src.services.venue_metadata import (
    estimate_round_trip_cost_pct,
    get_venue_profile,
    same_currency,
    same_session,
)
from src.services.brokerage_service import brokerage_service
from src.services.pair_discovery_helpers import (
    canonical_pair_id,
    is_pair_denied,
    normalize_denylist,
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


def _default_denylist() -> set[str]:
    from src.config import settings

    return set(settings.pair_denylist_ids)


def _default_max_abs_hedge(ticker_a: str = "", ticker_b: str = "") -> float:
    from src.services.pair_discovery_helpers import max_abs_hedge_limit

    if ticker_a and ticker_b:
        return max_abs_hedge_limit(ticker_a, ticker_b)
    from src.config import settings

    return float(settings.PAIR_DISCOVERY_MAX_ABS_HEDGE)


def _default_min_correlation() -> float:
    from src.config import settings

    return float(settings.PAIR_DISCOVERY_MIN_CORRELATION)


def _default_max_pvalue() -> float:
    from src.config import settings

    return float(settings.PAIR_DISCOVERY_MAX_PVALUE)


def _extreme_hedge_reason(
    hedge_ratio: float | None,
    *,
    max_abs_hedge: float,
) -> Optional[str]:
    """Reject only insane betas; leave missing/zero for later cointegration warm-up."""
    if hedge_ratio is None:
        return None
    try:
        value = float(hedge_ratio)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return "hedge_ratio_invalid:nan"
    # Zero / unset bootstrap hedges must still reach cointegration warm-up.
    if value == 0.0:
        return None
    if abs(value) > float(max_abs_hedge):
        return f"hedge_ratio_extreme:{value:.3f}>{float(max_abs_hedge):.1f}"
    return None


def _quality_rejection_reason(
    *,
    hedge_ratio: float | None,
    correlation: float | None,
    p_value: float | None,
    is_cointegrated: bool | None,
    max_abs_hedge: float,
    min_correlation: float,
    max_pvalue: float,
) -> Optional[str]:
    """Apply discovery-aligned quality gates when metrics are supplied."""
    extreme = _extreme_hedge_reason(hedge_ratio, max_abs_hedge=max_abs_hedge)
    if extreme:
        return extreme

    if correlation is not None:
        try:
            corr = float(correlation)
        except (TypeError, ValueError):
            return "correlation_invalid"
        if corr != corr:
            return "correlation_invalid:nan"
        if corr < float(min_correlation):
            return f"correlation_below_floor:{corr:.3f}<{float(min_correlation):.3f}"

    if p_value is not None:
        try:
            pval = float(p_value)
        except (TypeError, ValueError):
            return "pvalue_invalid"
        if pval != pval:
            return "pvalue_invalid:nan"
        if pval > float(max_pvalue):
            return f"pvalue_above_ceiling:{pval:.4f}>{float(max_pvalue):.4f}"

    # Only enforce when the caller explicitly asserts non-cointegration.
    # Fresh Active rows often persist is_cointegrated=False until warm-up.
    if is_cointegrated is False:
        return "not_cointegrated"

    return None


async def evaluate_pair(
    ticker_a: str,
    ticker_b: str,
    *,
    account_currency: str = "EUR",
    max_round_trip_cost_pct: float = 0.0125,
    block_cross_currency: bool = True,
    block_lse_short_hold: bool = True,
    allow_eu_continental_overlap: bool = False,
    denylist: Iterable[str] | None = None,
    hedge_ratio: float | None = None,
    correlation: float | None = None,
    p_value: float | None = None,
    is_cointegrated: bool | None = None,
    max_abs_hedge: float | None = None,
    min_correlation: float | None = None,
    max_pvalue: float | None = None,
    require_broker_active: bool | None = None,
) -> EligibilityResult:
    """Decide whether (ticker_a, ticker_b) should be admitted to the universe.

    Spec 037/038 venue + cost gates, plus discovery-aligned denylist / quality
    gates (PAIR_DENYLIST, PAIR_DISCOVERY_MAX_ABS_HEDGE,
    PAIR_DISCOVERY_MIN_CORRELATION, PAIR_DISCOVERY_MAX_PVALUE).

    Spec 038 - allow_eu_continental_overlap relaxes the session rule so XETRA,
    EURONEXT, BORSA_ITALIANA and SIX are treated as the same session group.

    ``require_broker_active`` defaults from ``not settings.PAPER_TRADING``:
    shadow paper skips Alpaca asset lookups; broker-paper/live stay fail-closed.
    """
    a = ticker_a.strip().upper()
    b = ticker_b.strip().upper()

    denied = (
        normalize_denylist(denylist)
        if denylist is not None
        else _default_denylist()
    )
    if is_pair_denied(ticker_a=a, ticker_b=b, denylist=denied):
        return EligibilityResult(
            False,
            f"denylisted:{canonical_pair_id(a, b)}",
            0.0,
        )

    hedge_cap = (
        float(max_abs_hedge)
        if max_abs_hedge is not None
        else _default_max_abs_hedge(a, b)
    )
    corr_floor = (
        float(min_correlation)
        if min_correlation is not None
        else _default_min_correlation()
    )
    pval_ceiling = (
        float(max_pvalue) if max_pvalue is not None else _default_max_pvalue()
    )
    quality_reason = _quality_rejection_reason(
        hedge_ratio=hedge_ratio,
        correlation=correlation,
        p_value=p_value,
        is_cointegrated=is_cointegrated,
        max_abs_hedge=hedge_cap,
        min_correlation=corr_floor,
        max_pvalue=pval_ceiling,
    )
    if quality_reason:
        return EligibilityResult(False, quality_reason, 0.0)

    crypto_pair = _is_crypto(a) and _is_crypto(b)

    if _is_crypto(a) ^ _is_crypto(b):
        return EligibilityResult(False, "mixed_crypto_equity_pair_not_supported", 0.0)

    if not crypto_pair and not same_session(a, b, allow_eu_continental_overlap=allow_eu_continental_overlap):
        v_a = get_venue_profile(a).market_id
        v_b = get_venue_profile(b).market_id
        return EligibilityResult(False, f"different_sessions:{v_a}_vs_{v_b}", 0.0)

    if not crypto_pair and block_cross_currency and not same_currency(a, b):
        c_a = get_venue_profile(a).currency
        c_b = get_venue_profile(b).currency
        return EligibilityResult(False, f"cross_currency:{c_a}_vs_{c_b}", 0.0)

    if not crypto_pair and block_lse_short_hold:
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

    # Spec 045: Ensure both legs are accessible in the active brokerage.
    # This prevents the "legs not working" errors during execution by failing
    # the pair earlier, before any Kalman/math is performed.
    # Shadow paper never routes to the broker; skip so placeholder / unauthorized
    # Alpaca credentials cannot wipe the scan universe (see AGENTS.md paper mode).
    if require_broker_active is None:
        from src.config import settings

        require_broker_active = not bool(settings.PAPER_TRADING)
    if require_broker_active:
        if not await brokerage_service.is_asset_active(a):
            return EligibilityResult(False, f"asset_not_active_in_brokerage:{a}", 0.0)
        if not await brokerage_service.is_asset_active(b):
            return EligibilityResult(False, f"asset_not_active_in_brokerage:{b}", 0.0)

    return EligibilityResult(True, "crypto_pair" if crypto_pair else "admitted", cost)


def _pair_metric(pair: dict, *keys: str) -> float | None:
    for key in keys:
        if key not in pair or pair[key] is None:
            continue
        try:
            return float(pair[key])
        except (TypeError, ValueError):
            continue
    return None


async def filter_pair_universe(
    pairs: list,
    *,
    account_currency: str = "EUR",
    max_round_trip_cost_pct: float = 0.0125,
    block_cross_currency: bool = True,
    block_lse_short_hold: bool = True,
    allow_eu_continental_overlap: bool = False,
    denylist: Iterable[str] | None = None,
    max_abs_hedge: float | None = None,
    min_correlation: float | None = None,
    max_pvalue: float | None = None,
    enforce_stored_cointegration: bool = False,
):
    """Split a candidate universe into (admitted, rejected) lists.

    Denylist + extreme stored hedge ratios are always enforced. Correlation /
    p-value are applied when present on the pair dict. Stored
    ``is_cointegrated=False`` is ignored unless ``enforce_stored_cointegration``
    is set, so fresh Active bootstrap rows can still warm Kalman.
    """
    admitted = []
    rejected = []
    for pair in pairs:
        hedge = _pair_metric(pair, "hedge_ratio")
        corr = _pair_metric(pair, "correlation")
        pval = _pair_metric(pair, "p_value", "pvalue")
        coint = None
        if enforce_stored_cointegration and "is_cointegrated" in pair:
            coint = bool(pair.get("is_cointegrated"))

        verdict = await evaluate_pair(
            pair["ticker_a"],
            pair["ticker_b"],
            account_currency=account_currency,
            max_round_trip_cost_pct=max_round_trip_cost_pct,
            block_cross_currency=block_cross_currency,
            block_lse_short_hold=block_lse_short_hold,
            allow_eu_continental_overlap=allow_eu_continental_overlap,
            denylist=denylist,
            hedge_ratio=hedge,
            correlation=corr,
            p_value=pval,
            is_cointegrated=coint,
            max_abs_hedge=max_abs_hedge,
            min_correlation=min_correlation,
            max_pvalue=max_pvalue,
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
