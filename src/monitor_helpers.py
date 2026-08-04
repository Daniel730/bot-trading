from __future__ import annotations

from typing import Mapping


def is_crypto_pair(ticker_a: str, ticker_b: str) -> bool:
    return "-USD" in ticker_a or "-USD" in ticker_b


def resolve_pair_sector(
    pair_id: str,
    ticker_a: str,
    ticker_b: str,
    pair_sectors: Mapping[str, str],
) -> str:
    return pair_sectors.get(pair_id, pair_sectors.get(f"{ticker_b}_{ticker_a}", "Unassigned"))


def resolve_hedge_ratio(
    pair: Mapping[str, object],
    *,
    kalman_beta: float | None = None,
) -> float:
    """Prefer live Kalman beta; fall back to pair's stored hedge ratio."""
    for candidate in (kalman_beta, pair.get("dynamic_beta"), pair.get("hedge_ratio")):
        try:
            value = float(candidate)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 1.0


def resolve_kalman_pair_id(
    ticker_a: str,
    ticker_b: str,
    *,
    known_ids: set[str] | frozenset[str] | None = None,
) -> str:
    """Return the canonical Kalman/Redis pair id for two tickers."""
    primary = f"{ticker_a}_{ticker_b}"
    if not known_ids:
        return primary
    if primary in known_ids:
        return primary
    alternate = f"{ticker_b}_{ticker_a}"
    if alternate in known_ids:
        return alternate
    return primary


def is_executable_bid_ask(bid: float, ask: float) -> bool:
    """True when both sides are positive and the quote is not crossed."""
    try:
        bid_value = float(bid)
        ask_value = float(ask)
    except (TypeError, ValueError):
        return False
    return bid_value > 0.0 and ask_value > 0.0 and ask_value >= bid_value


def resolve_profit_guard_friction_pct(
    *,
    fee_friction_pct: float,
    pair_estimated_cost_pct: float,
    gross_notional: float,
    flat_order_friction_usd: float,
) -> float:
    """Conservative friction floor for the pre-approval profit guard.

    ``validate_trade`` often computes flat friction against portfolio cash, which
    understates cost on the actual pair notional when ``estimated_cost_pct`` is
    missing. Always take the max of fee %, venue estimate, and flat/notional.
    """
    try:
        fee_pct = max(0.0, float(fee_friction_pct or 0.0))
    except (TypeError, ValueError):
        fee_pct = 0.0
    try:
        estimated_pct = max(0.0, float(pair_estimated_cost_pct or 0.0))
    except (TypeError, ValueError):
        estimated_pct = 0.0
    flat_pct = 0.0
    try:
        notional = float(gross_notional or 0.0)
        flat_usd = max(0.0, float(flat_order_friction_usd or 0.0))
        if notional > 0.0 and flat_usd > 0.0:
            flat_pct = flat_usd / notional
    except (TypeError, ValueError):
        flat_pct = 0.0
    return max(fee_pct, estimated_pct, flat_pct)


def compute_entry_zscore(
    base_entry_zscore: float,
    *,
    cost_scaling_enabled: bool,
    pair_estimated_cost_pct: float,
    cost_baseline: float,
    scaling_cap: float,
    cost_ceiling: float | None = None,
) -> float:
    if not cost_scaling_enabled or cost_baseline <= 0:
        return base_entry_zscore
    if pair_estimated_cost_pct <= cost_baseline:
        return base_entry_zscore
    if cost_ceiling is not None and cost_ceiling > cost_baseline:
        if scaling_cap <= 1:
            return base_entry_zscore
        cost_progress = (pair_estimated_cost_pct - cost_baseline) / (cost_ceiling - cost_baseline)
        scale = 1.0 + ((scaling_cap - 1.0) * min(cost_progress, 1.0))
        return base_entry_zscore * scale
    scale = min(pair_estimated_cost_pct / cost_baseline, scaling_cap)
    return base_entry_zscore * scale


def should_take_profit_exit(
    *,
    abs_z_score: float,
    take_profit_zscore: float,
    directional_pnl: float,
    estimated_friction: float,
    force_exit_zscore: float,
) -> tuple[bool, str]:
    """Decide whether a TP-band exit should close despite friction.

    Caller must already gate on ``abs_z_score <= take_profit_zscore``.
    Returns ``(should_close, reason)``.
    """
    _ = take_profit_zscore  # documented precondition for callers
    if float(directional_pnl) > float(estimated_friction):
        return True, "covers_friction"
    if float(abs_z_score) <= float(force_exit_zscore):
        return True, "force_mean_reversion"
    return False, "friction_hold"
