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
