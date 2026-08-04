from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

# Terminal / low-value dashboard signal statuses safe to drop under memory pressure.
TERMINAL_SIGNAL_STATUSES = frozenset(
    {
        "VETOED",
        "VETOED_TIMEOUT",
        "VETOED_SIZE",
        "VETOED_UNPROFITABLE",
        "REJECTED",
        "EXECUTION_BLOCKED",
        "SKIPPED",
        "ALREADY_OPEN",
    }
)


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


def prune_active_signals(
    signals: Sequence[Mapping[str, object]],
    *,
    active_pair_ids: Iterable[str] | None = None,
    max_signals: int = 40,
    drop_terminal: bool = True,
) -> list[dict]:
    """Bound dashboard signal list to live pairs / non-terminal rows.

    ``active_signals`` upserts one row per pair but never forgets vetoed rows
    after the pair leaves the scan set, so the list can grow across rotations.
    """
    active_ids = {str(pid) for pid in (active_pair_ids or []) if pid}
    kept: list[dict] = []
    for raw in signals:
        entry = dict(raw)
        ticker_a = str(entry.get("ticker_a") or "")
        ticker_b = str(entry.get("ticker_b") or "")
        pair_id = str(entry.get("pair_id") or entry.get("id") or f"{ticker_a}_{ticker_b}")
        status = str(entry.get("status") or "").upper()
        if active_ids and pair_id not in active_ids and f"{ticker_b}_{ticker_a}" not in active_ids:
            # Keep only rows that still map to an Active scan pair.
            continue
        if drop_terminal and status in TERMINAL_SIGNAL_STATUSES:
            continue
        kept.append(entry)
    if max_signals > 0 and len(kept) > max_signals:
        kept = kept[-max_signals:]
    return kept


def prune_dict_to_keys(
    mapping: MutableMapping[str, object],
    keep_keys: Iterable[str],
) -> int:
    """Drop mapping keys not in *keep_keys*. Returns number of keys removed."""
    allowed = {str(k) for k in keep_keys}
    stale = [key for key in list(mapping.keys()) if str(key) not in allowed]
    for key in stale:
        mapping.pop(key, None)
    return len(stale)


def rotate_jsonl_if_large(path: Path | str, *, max_bytes: int) -> bool:
    """Rename *path* to ``.1`` when it exceeds *max_bytes*. Returns True if rotated."""
    if max_bytes <= 0:
        return False
    target = Path(path)
    try:
        size = target.stat().st_size
    except FileNotFoundError:
        return False
    except OSError:
        return False
    if size < max_bytes:
        return False
    backup = target.with_name(target.name + ".1")
    try:
        if backup.exists():
            backup.unlink()
        os.replace(target, backup)
    except OSError:
        return False
    return True


def evict_ttl_cache(
    cache: MutableMapping[str, tuple],
    *,
    now: float,
    ttl_seconds: float,
    max_entries: int,
) -> int:
    """Drop expired TTL cache entries, then oldest extras beyond *max_entries*."""
    removed = 0
    if ttl_seconds > 0:
        expired = [
            key
            for key, (ts, *_rest) in list(cache.items())
            if (now - float(ts)) > ttl_seconds
        ]
        for key in expired:
            cache.pop(key, None)
            removed += 1
    if max_entries > 0 and len(cache) > max_entries:
        # Assume tuple[0] is a monotonic/unix timestamp.
        ordered = sorted(cache.items(), key=lambda item: float(item[1][0]))
        overflow = len(cache) - max_entries
        for key, _value in ordered[:overflow]:
            cache.pop(key, None)
            removed += 1
    return removed
