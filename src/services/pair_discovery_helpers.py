"""Helpers for automatic pair discovery and elite-squad rotation.

Keeps pair-id parsing and promotion policy in one place so the portfolio
manager scout, monitor auto-scout loop, and dashboard discover endpoint
share the same rules.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, List, Optional, Sequence, Set, Tuple

from src.services.portfolio_book_guards import (
    candidate_shares_occupied_ticker,
    occupied_tickers_from_pairs,
)


def parse_pair_id(pair_id: str) -> Tuple[str, str]:
    """Split ``TICKER_A_TICKER_B`` into legs.

    Crypto legs use a hyphenated suffix (``BTC-USD``), so a naive
    ``split('_')`` is correct when each leg has no underscore. When the first
    leg ends with ``-USD``, split after that suffix so ``BTC-USD_ETH-USD``
    parses correctly even if either side contains additional hyphens.
    """
    raw = (pair_id or "").strip()
    if not raw:
        raise ValueError("pair_id is empty")

    upper = raw.upper()
    marker = "-USD_"
    if marker in upper:
        idx = upper.index(marker) + len("-USD")
        left, right = raw[:idx], raw[idx + 1 :]
        if left and right:
            return left, right

    if "_" not in raw:
        raise ValueError(f"pair_id missing separator: {pair_id!r}")
    left, right = raw.split("_", 1)
    if not left or not right:
        raise ValueError(f"pair_id has empty leg: {pair_id!r}")
    return left, right


def canonical_pair_id(ticker_a: str, ticker_b: str) -> str:
    """Build the canonical ``A_B`` pair id used across persistence + monitor."""
    return f"{str(ticker_a).strip().upper()}_{str(ticker_b).strip().upper()}"


def pair_id_aliases(pair_id: str) -> Set[str]:
    """Return both orderings of a pair id (A_B and B_A)."""
    try:
        a, b = parse_pair_id(pair_id)
    except ValueError:
        raw = str(pair_id or "").strip().upper()
        return {raw} if raw else set()
    return {canonical_pair_id(a, b), canonical_pair_id(b, a)}


def normalize_denylist(entries: Iterable[str] | None) -> Set[str]:
    """Expand denylist entries to both leg orderings, uppercased."""
    denied: set[str] = set()
    for entry in entries or []:
        raw = str(entry or "").strip()
        if not raw:
            continue
        denied |= pair_id_aliases(raw)
    return denied


def is_pair_denied(
    *,
    pair_id: str | None = None,
    ticker_a: str | None = None,
    ticker_b: str | None = None,
    denylist: Iterable[str] | None = None,
) -> bool:
    """True when the pair (either leg order) is on the operator denylist."""
    denied = denylist if isinstance(denylist, set) else normalize_denylist(denylist)
    if not denied:
        return False
    if pair_id:
        return bool(pair_id_aliases(pair_id) & denied)
    if ticker_a and ticker_b:
        return bool(pair_id_aliases(canonical_pair_id(ticker_a, ticker_b)) & denied)
    return False


def is_hedge_ratio_sane(hedge_ratio: float | None, *, max_abs_hedge: float) -> bool:
    """Reject extreme OLS/Kalman betas that blow up notional and spread guards."""
    try:
        value = float(hedge_ratio)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if value != value or value == 0.0:  # NaN or zero
        return False
    return abs(value) <= float(max_abs_hedge)


def candidate_pair_combos(
    tickers: Sequence[str],
    *,
    max_tickers: int = 12,
) -> List[Tuple[str, str]]:
    """Build bounded unordered ticker pairs for a sector/crypto scout pass."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for ticker in tickers:
        symbol = str(ticker or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        cleaned.append(symbol)
        if len(cleaned) >= max_tickers:
            break
    return list(combinations(cleaned, 2))


def _candidate_sortino(candidate: dict) -> float:
    try:
        return float(candidate.get("sortino") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _candidate_passes_quality(
    candidate: dict,
    *,
    sortino_threshold: float,
    min_correlation: float,
    max_pvalue: float,
    max_abs_hedge: float,
) -> bool:
    """Quality gates for promotion — keep junk out of the Active squad."""
    if _candidate_sortino(candidate) < float(sortino_threshold):
        return False

    corr = candidate.get("correlation")
    if corr is not None:
        try:
            if float(corr) < float(min_correlation):
                return False
        except (TypeError, ValueError):
            return False

    p_value = candidate.get("p_value")
    if p_value is not None:
        try:
            if float(p_value) > float(max_pvalue):
                return False
        except (TypeError, ValueError):
            return False

    hedge = candidate.get("hedge_ratio")
    if hedge is not None and not is_hedge_ratio_sane(hedge, max_abs_hedge=max_abs_hedge):
        return False
    return True


def select_rotation_actions(
    active_pairs: Sequence[dict],
    candidates: Sequence[dict],
    *,
    max_active_pairs: int,
    sortino_threshold: float = 0.0,
    denylist: Iterable[str] | None = None,
    max_abs_hedge: float = 25.0,
    min_correlation: float = 0.0,
    max_pvalue: float = 1.0,
) -> dict:
    """Decide which active pairs to bench and which candidates to promote.

    Policy (in order):
    1. Bench denylisted Active pairs immediately.
    2. Bench Active pairs with insane hedge ratios (BTC/BCH-scale betas).
    3. Bench non-cointegrated Active pairs immediately (free scan slots even
       when no replacement scout is ready).
    4. Fill open slots up to ``max_active_pairs`` from top quality candidates.

    Candidates on the denylist, below Sortino/correlation floors, above the
    cointegration p-value ceiling, or with insane hedge ratios are never promoted.
    """
    denied = normalize_denylist(denylist)
    active = list(active_pairs or [])
    scouts = sorted(list(candidates or []), key=_candidate_sortino, reverse=True)

    to_bench: list[str] = []
    for pair in active:
        pair_id = str(pair.get("id") or "")
        if not pair_id:
            continue
        if is_pair_denied(pair_id=pair_id, denylist=denied):
            to_bench.append(pair_id)
            continue
        hedge = pair.get("hedge_ratio")
        if hedge is not None and not is_hedge_ratio_sane(hedge, max_abs_hedge=max_abs_hedge):
            to_bench.append(pair_id)
            continue
        # Dead equity / broken crypto must not keep occupying Active slots
        # overnight while waiting for a replacement scout.
        if not bool(pair.get("is_cointegrated", True)):
            to_bench.append(pair_id)

    remaining_active = [p for p in active if str(p.get("id") or "") not in to_bench]
    active_ids = {str(p.get("id") or "") for p in remaining_active}
    occupied_tickers = occupied_tickers_from_pairs(remaining_active, id_key="id")

    eligible: list[dict] = []
    for candidate in scouts:
        pair_id = str(candidate.get("pair_id") or "")
        if not pair_id or pair_id in active_ids:
            continue
        if is_pair_denied(pair_id=pair_id, denylist=denied):
            continue
        if not _candidate_passes_quality(
            candidate,
            sortino_threshold=sortino_threshold,
            min_correlation=min_correlation,
            max_pvalue=max_pvalue,
            max_abs_hedge=max_abs_hedge,
        ):
            continue
        # Do not promote pairs that share a leg with remaining Active pairs —
        # that overcrowds the scan book with correlated name exposure.
        if candidate_shares_occupied_ticker(candidate, occupied_tickers):
            continue
        eligible.append(candidate)

    open_slots = max(0, int(max_active_pairs) - len(remaining_active))
    to_promote = eligible[:open_slots]

    seen_promote: set[str] = set()
    unique_promote: list[dict] = []
    promote_occupied = set(occupied_tickers)
    for candidate in to_promote:
        pid = str(candidate.get("pair_id") or "")
        if not pid or pid in seen_promote:
            continue
        if candidate_shares_occupied_ticker(candidate, promote_occupied):
            continue
        seen_promote.add(pid)
        unique_promote.append(candidate)
        promote_occupied |= occupied_tickers_from_pairs([{"pair_id": pid}], id_key="pair_id")

    # Deduplicate benches while preserving order.
    seen_bench: set[str] = set()
    unique_bench: list[str] = []
    for pair_id in to_bench:
        if pair_id in seen_bench:
            continue
        seen_bench.add(pair_id)
        unique_bench.append(pair_id)

    return {
        "to_bench": unique_bench,
        "to_promote": unique_promote,
    }


def pairs_from_promotions(candidates: Iterable[dict]) -> List[dict]:
    """Convert UniverseCandidate-like dicts into TradingPair upsert payloads."""
    out: list[dict] = []
    for candidate in candidates:
        pair_id = str(candidate.get("pair_id") or "")
        try:
            ticker_a, ticker_b = parse_pair_id(pair_id)
        except ValueError:
            continue
        try:
            hedge = float(candidate.get("hedge_ratio") or 0.0)
        except (TypeError, ValueError):
            hedge = 0.0
        out.append(
            {
                "id": pair_id,
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "hedge_ratio": hedge,
                "is_cointegrated": True,
                "status": "Active",
            }
        )
    return out


def parse_denylist_env(raw: Optional[str]) -> List[str]:
    """Parse comma/semicolon/whitespace-separated denylist env values."""
    if not raw:
        return []
    text = str(raw).replace(";", ",").replace("\n", ",")
    return [part.strip() for part in text.split(",") if part.strip()]
