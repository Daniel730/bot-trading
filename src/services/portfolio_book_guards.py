"""Portfolio overcrowding / correlation book guards (pure helpers).

These gates sit in front of execute_trade so the open book cannot:
- exceed ``MAX_OPEN_PAIRS`` concurrent signals;
- stack multiple pairs that share a leg (correlated name blowups);
- breach portfolio-level gross notional;
- push a sector past ``MAX_SECTOR_EXPOSURE`` (with consistent sector labels).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set


def canonical_book_symbol(symbol: Any) -> str:
    """Match monitor ledger canonicalization (strip / and -)."""
    return str(symbol or "").upper().replace("/", "").replace("-", "")


def normalize_sector_label(sector: Any) -> str:
    """Unify legacy defaults so cluster math does not under-count exposure."""
    raw = str(sector or "").strip()
    if not raw or raw.lower() in {"general", "unknown", "unassigned", "none", "n/a"}:
        return "Unassigned"
    return raw


def open_leg_symbols(
    open_signals: Sequence[Mapping[str, Any]] | None,
    *,
    canonicalize: Callable[[Any], str] = canonical_book_symbol,
) -> Set[str]:
    symbols: set[str] = set()
    for signal in open_signals or []:
        for leg in signal.get("legs") or []:
            if not isinstance(leg, Mapping):
                continue
            ticker = leg.get("ticker")
            if not ticker:
                continue
            canon = canonicalize(ticker)
            if canon:
                symbols.add(canon)
    return symbols


def find_shared_leg_conflict(
    ticker_a: str,
    ticker_b: str,
    open_signals: Sequence[Mapping[str, Any]] | None,
    *,
    canonicalize: Callable[[Any], str] = canonical_book_symbol,
) -> Optional[Dict[str, Any]]:
    """Return conflict metadata when either proposed leg is already open."""
    proposed = {canonicalize(ticker_a), canonicalize(ticker_b)} - {""}
    if not proposed:
        return None
    for signal in open_signals or []:
        leg_symbols = {
            canonicalize(leg.get("ticker"))
            for leg in (signal.get("legs") or [])
            if isinstance(leg, Mapping) and leg.get("ticker")
        } - {""}
        overlap = proposed & leg_symbols
        if overlap:
            return {
                "signal_id": signal.get("signal_id"),
                "overlap": sorted(overlap),
                "open_legs": sorted(leg_symbols),
            }
    return None


def check_max_open_pairs(
    open_signal_count: int,
    max_open_pairs: int,
) -> Dict[str, Any]:
    """Cap concurrent open pair signals (0 disables the gate)."""
    limit = int(max_open_pairs or 0)
    count = max(0, int(open_signal_count or 0))
    if limit <= 0:
        return {"allowed": True, "open_count": count, "limit": limit, "reason": ""}
    if count >= limit:
        return {
            "allowed": False,
            "open_count": count,
            "limit": limit,
            "reason": f"Open pairs {count} at/above MAX_OPEN_PAIRS={limit}",
        }
    return {"allowed": True, "open_count": count, "limit": limit, "reason": ""}


def check_portfolio_gross_notional(
    current_gross: float,
    new_gross: float,
    max_portfolio_gross: float,
) -> Dict[str, Any]:
    """Cap book-wide gross notional (0 disables the gate)."""
    limit = float(max_portfolio_gross or 0.0)
    current = max(0.0, float(current_gross or 0.0))
    added = max(0.0, float(new_gross or 0.0))
    projected = current + added
    if limit <= 0:
        return {
            "allowed": True,
            "current_gross": current,
            "projected_gross": projected,
            "limit": limit,
            "reason": "",
        }
    if projected > limit + 1e-9:
        return {
            "allowed": False,
            "current_gross": current,
            "projected_gross": projected,
            "limit": limit,
            "reason": (
                f"Projected book gross ${projected:.2f} exceeds "
                f"MAX_PORTFOLIO_GROSS_NOTIONAL_USD=${limit:.2f}"
            ),
        }
    return {
        "allowed": True,
        "current_gross": current,
        "projected_gross": projected,
        "limit": limit,
        "reason": "",
    }


def check_projected_sector_exposure(
    portfolio: Sequence[Mapping[str, Any]] | None,
    *,
    pair_sector: str,
    new_trade_size: float,
    sizing_base: float,
    max_sector_exposure: float,
) -> Dict[str, Any]:
    """Prospective sector cluster guard used by execute_trade."""
    sector = normalize_sector_label(pair_sector)
    holdings = list(portfolio or [])
    total_size = sum(float(p.get("size") or 0.0) for p in holdings)
    sector_size = sum(
        float(p.get("size") or 0.0)
        for p in holdings
        if normalize_sector_label(p.get("sector")) == sector
    )
    new_size = max(0.0, float(new_trade_size or 0.0))
    # Empty-portfolio trap: first trade would otherwise always look like 100%.
    denominator = max(total_size + new_size, float(sizing_base or 0.0), 1e-9)
    projected = (sector_size + new_size) / denominator
    limit = float(max_sector_exposure)
    allowed = projected <= limit + 1e-12
    reason = ""
    if not allowed:
        reason = (
            f"Projected '{sector}' exposure {projected:.1%} exceeds "
            f"MAX_SECTOR_EXPOSURE={limit:.0%} (base=${denominator:.2f})"
        )
    return {
        "allowed": allowed,
        "sector": sector,
        "projected_exposure": projected,
        "sector_size": sector_size,
        "total_size": total_size,
        "new_trade_size": new_size,
        "denominator": denominator,
        "limit": limit,
        "reason": reason,
    }


def gross_notional_from_signals(open_signals: Sequence[Mapping[str, Any]] | None) -> float:
    total = 0.0
    for signal in open_signals or []:
        try:
            total += float(signal.get("total_cost_basis") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def occupied_tickers_from_pairs(
    pairs: Iterable[Mapping[str, Any]] | None,
    *,
    id_key: str = "id",
) -> Set[str]:
    """Ticker set occupied by Active (or remaining) pairs for rotation policy."""
    from src.services.pair_discovery_helpers import parse_pair_id

    occupied: set[str] = set()
    for pair in pairs or []:
        pair_id = str(pair.get(id_key) or pair.get("pair_id") or "").strip()
        if not pair_id:
            continue
        try:
            a, b = parse_pair_id(pair_id)
        except ValueError:
            continue
        for ticker in (a, b):
            canon = canonical_book_symbol(ticker)
            if canon:
                occupied.add(canon)
    return occupied


def candidate_shares_occupied_ticker(
    candidate: Mapping[str, Any],
    occupied: Set[str],
) -> bool:
    from src.services.pair_discovery_helpers import parse_pair_id

    pair_id = str(candidate.get("pair_id") or candidate.get("id") or "").strip()
    if not pair_id or not occupied:
        return False
    try:
        a, b = parse_pair_id(pair_id)
    except ValueError:
        return False
    proposed = {canonical_book_symbol(a), canonical_book_symbol(b)} - {""}
    return bool(proposed & occupied)
