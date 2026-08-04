"""Helpers for automatic pair discovery and elite-squad rotation.

Keeps pair-id parsing and promotion policy in one place so the portfolio
manager scout, monitor auto-scout loop, and dashboard discover endpoint
share the same rules.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, List, Optional, Sequence, Set, Tuple


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


def select_rotation_actions(
    active_pairs: Sequence[dict],
    candidates: Sequence[dict],
    *,
    max_active_pairs: int,
    sortino_threshold: float = 0.0,
    denylist: Iterable[str] | None = None,
    max_abs_hedge: float = 25.0,
) -> dict:
    """Decide which active pairs to bench and which candidates to promote.

    Policy (in order):
    1. Bench denylisted Active pairs immediately.
    2. Fill open slots up to ``max_active_pairs`` from top candidates.
    3. Replace non-cointegrated active pairs with remaining candidates.

    Candidates on the denylist or with insane hedge ratios are never promoted.
    """
    _ = sortino_threshold  # reserved for callers that gate fill quality
    denied = normalize_denylist(denylist)
    active = list(active_pairs or [])
    scouts = list(candidates or [])

    to_bench: list[str] = []
    for pair in active:
        pair_id = str(pair.get("id") or "")
        if pair_id and is_pair_denied(pair_id=pair_id, denylist=denied):
            to_bench.append(pair_id)

    remaining_active = [p for p in active if str(p.get("id") or "") not in to_bench]
    active_ids = {str(p.get("id") or "") for p in remaining_active}

    eligible: list[dict] = []
    for candidate in scouts:
        pair_id = str(candidate.get("pair_id") or "")
        if not pair_id or pair_id in active_ids:
            continue
        if is_pair_denied(pair_id=pair_id, denylist=denied):
            continue
        hedge = candidate.get("hedge_ratio")
        if hedge is not None and not is_hedge_ratio_sane(hedge, max_abs_hedge=max_abs_hedge):
            continue
        eligible.append(candidate)

    to_promote: list[dict] = []

    open_slots = max(0, int(max_active_pairs) - len(remaining_active))
    fill, eligible = eligible[:open_slots], eligible[open_slots:]
    to_promote.extend(fill)

    broken = [p for p in remaining_active if not bool(p.get("is_cointegrated", True))]
    replace_count = min(len(broken), len(eligible))
    for i in range(replace_count):
        pair_id = str(broken[i].get("id") or "")
        if not pair_id:
            continue
        to_bench.append(pair_id)
        to_promote.append(eligible[i])

    seen_promote: set[str] = set()
    unique_promote: list[dict] = []
    for candidate in to_promote:
        pid = str(candidate.get("pair_id") or "")
        if not pid or pid in seen_promote:
            continue
        seen_promote.add(pid)
        unique_promote.append(candidate)

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
        out.append(
            {
                "id": pair_id,
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "hedge_ratio": float(candidate.get("hedge_ratio") or 0.0),
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
