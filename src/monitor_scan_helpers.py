from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

from src.monitor_helpers import is_crypto_pair

T = TypeVar("T")


async def gather_bounded(
    awaitables: Iterable[Awaitable[T]],
    *,
    limit: int,
    return_exceptions: bool = True,
) -> list[T | BaseException]:
    """
    Run awaitables concurrently with a hard semaphore cap.

    Preserves input order in the returned list (same contract as asyncio.gather).
    Used by the monitor scan/exit loops so Mini PC CPU/RAM cannot be saturated by
    an unbounded gather storm while every pair/signal still runs each cycle.
    """
    items = list(awaitables)
    if not items:
        return []
    concurrency = max(1, int(limit))
    semaphore = asyncio.Semaphore(concurrency)

    async def _run(awaitable: Awaitable[T]) -> T | BaseException:
        async with semaphore:
            try:
                return await awaitable
            except Exception as exc:
                if return_exceptions:
                    return exc
                raise

    return list(await asyncio.gather(*(_run(item) for item in items)))


def open_signal_tickers(open_signals: Iterable[dict]) -> list[str]:
    """Collect unique leg tickers from open ledger signals (order-preserving)."""
    tickers: list[str] = []
    seen: set[str] = set()
    for signal in open_signals:
        for leg in signal.get("legs") or []:
            ticker = leg.get("ticker")
            if not ticker:
                continue
            key = str(ticker)
            if key in seen:
                continue
            seen.add(key)
            tickers.append(key)
    return tickers


def normalize_scan_results(raw_results: Iterable[object]) -> list[dict]:
    """Drop gather exceptions so summarize_scan_iteration only sees pair diagnostics."""
    normalized: list[dict] = []
    for item in raw_results:
        if isinstance(item, Exception):
            continue
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def _pair_key(pair: dict) -> frozenset[str]:
    """Order-independent key so BTC/ETH and ETH/BTC collapse to one slot."""
    return frozenset(
        (str(pair["ticker_a"]).upper(), str(pair["ticker_b"]).upper())
    )


def build_candidate_pairs(
    base_pairs: list[dict],
    configured_crypto_pairs: list[dict],
    max_active_pairs: int,
    *,
    dev_mode: bool,
) -> list[dict]:
    """
    Build the boot-time candidate universe while reserving active slots for crypto.

    Crypto pairs run 24/7, so production mode must not let a full saved equity
    universe crowd them out. The returned list is capped at max_active_pairs.
    Reverse-oriented duplicates (ETH/BTC vs BTC/ETH) share one slot.
    """
    seen_crypto: set[frozenset[str]] = set()
    crypto_pairs: list[dict] = []
    for pair in [*base_pairs, *configured_crypto_pairs]:
        if not is_crypto_pair(pair["ticker_a"], pair["ticker_b"]):
            continue
        key = _pair_key(pair)
        if key in seen_crypto:
            continue
        seen_crypto.add(key)
        crypto_pairs.append(pair)

    effective_limit = max_active_pairs if max_active_pairs > 0 else len(crypto_pairs)
    if effective_limit <= 0:
        return []

    if dev_mode:
        return crypto_pairs[:effective_limit]

    selected_crypto = crypto_pairs[:effective_limit]
    equity_slots = max(0, effective_limit - len(selected_crypto))

    seen_equity: set[frozenset[str]] = set()
    equity_pairs: list[dict] = []
    if equity_slots > 0:
        for pair in base_pairs:
            if is_crypto_pair(pair["ticker_a"], pair["ticker_b"]):
                continue
            key = _pair_key(pair)
            if key in seen_equity:
                continue
            seen_equity.add(key)
            equity_pairs.append(pair)
            if len(equity_pairs) >= equity_slots:
                break

    return [*equity_pairs, *selected_crypto]


def build_scan_pairs(active_pairs: list[dict], is_market_open: Callable[[str], bool]) -> tuple[list[dict], list[str]]:
    scan_pairs: list[dict] = []
    all_tickers: list[str] = []
    for pair in active_pairs:
        ticker_a, ticker_b = pair["ticker_a"], pair["ticker_b"]
        if pair.get("is_cointegrated", True) is False:
            continue
        if not is_crypto_pair(ticker_a, ticker_b):
            if not is_market_open(ticker_a):
                continue
        scan_pairs.append(pair)
        all_tickers.extend([ticker_a, ticker_b])
    return scan_pairs, all_tickers


def summarize_scan_iteration(results: list[dict], min_ai_confidence: float) -> tuple[int, int]:
    active_signals = [r for r in results if r and r.get("confidence", 0) > min_ai_confidence]
    vetoed = [r for r in results if r and r.get("verdict") == "VETOED"]
    return len(active_signals), len(vetoed)


def summarize_scan_funnel(
    results: list[dict],
    *,
    active_pairs: list[dict],
    scan_pairs: list[dict],
    min_ai_confidence: float,
) -> dict[str, object]:
    """Per-iteration funnel counters for ops (near-miss / skip reasons / asset mix)."""
    active_equity = sum(
        1 for p in active_pairs if not is_crypto_pair(p["ticker_a"], p["ticker_b"])
    )
    active_crypto = sum(
        1 for p in active_pairs if is_crypto_pair(p["ticker_a"], p["ticker_b"])
    )
    skip_reasons: dict[str, int] = {}
    near_miss = 0
    entry_band_hit = 0
    approved = 0
    order_submitted = 0
    for row in results:
        if not isinstance(row, dict):
            continue
        reason = str(row.get("reason") or "")
        if reason:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        if row.get("near_miss"):
            near_miss += 1
        if reason == "entry_band" or row.get("verdict") in {"APPROVED", "EXECUTE", "EXECUTED"}:
            entry_band_hit += 1
        if row.get("approved") or row.get("verdict") == "APPROVED":
            approved += 1
        if row.get("order_submitted") or row.get("executed"):
            order_submitted += 1
    active_signals, vetoed = summarize_scan_iteration(results, min_ai_confidence)
    return {
        "active_equity": active_equity,
        "active_crypto": active_crypto,
        "scanned": len(scan_pairs),
        "active_total": len(active_pairs),
        "signals": active_signals,
        "vetoed": vetoed,
        "near_miss": near_miss,
        "entry_band_hit": entry_band_hit,
        "approved": approved,
        "order_submitted": order_submitted,
        "skip_reasons": dict(sorted(skip_reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def resolve_leg_filled_qty(leg: dict) -> float:
    """Prefer durable filled_qty (leg or metadata) over submitted quantity."""
    meta = leg.get("metadata") if isinstance(leg.get("metadata"), dict) else {}
    for source in (leg.get("filled_qty"), meta.get("filled_qty"), leg.get("quantity")):
        if source is None:
            continue
        try:
            qty = float(source)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            return qty
    return 0.0


def resolve_leg_order_id(leg: dict) -> str | None:
    """Open-leg broker/client order id for ledger fill updates."""
    meta = leg.get("metadata") if isinstance(leg.get("metadata"), dict) else {}
    for source in (leg.get("order_id"), meta.get("broker_order_id"), meta.get("client_order_id")):
        if source:
            return str(source)
    return None


def build_close_orders(
    signal: dict,
    *,
    prices_by_ticker: dict[str, float] | None = None,
    price_a: float | None = None,
    price_b: float | None = None,
    dev_mode: bool,
    dev_execution_tickers: dict[str, str],
) -> list[dict]:
    close_orders: list[dict] = []
    if prices_by_ticker is None:
        first_leg_ticker = signal["legs"][0]["ticker"]
        second_leg_ticker = signal["legs"][1]["ticker"]
        prices_by_ticker = {
            first_leg_ticker: float(price_a if price_a is not None else 0.0),
            second_leg_ticker: float(price_b if price_b is not None else 0.0),
        }
    for leg in signal["legs"]:
        ticker = leg["ticker"]
        quantity = resolve_leg_filled_qty(leg)
        side = "SELL" if leg["side"] == "BUY" else "BUY"
        execution_ticker = dev_execution_tickers.get(ticker, ticker) if dev_mode else ticker
        if ticker not in prices_by_ticker:
            raise KeyError(f"Missing close price for ticker {ticker}")
        leg_price = float(prices_by_ticker[ticker])
        close_orders.append(
            {
                "ticker": execution_ticker,
                "display_ticker": ticker,
                "side": side,
                "quantity": quantity,
                "price": float(leg_price),
                "open_order_id": resolve_leg_order_id(leg),
            }
        )
    return close_orders


def calculate_realized_pnl(
    signal: dict,
    *,
    prices_by_ticker: dict[str, float] | None = None,
    price_a: float | None = None,
    price_b: float | None = None,
    include_costs: bool = True,
    exit_fee_per_leg: float | None = None,
) -> tuple[dict[str, float], float]:
    """Directional leg PnL, optionally net of entry/exit fees and slippage.

    Costs subtracted when ``include_costs`` is True:
    - per-leg ``fee`` (entry commission / flat friction recorded at open)
    - estimated exit fee per leg (defaults to ``settings.FLAT_ORDER_FRICTION_USD``)
    - ``slippage_bps`` on entry notional when present on the leg or its metadata

    When the ledger ``price`` already embeds adverse fill slip (shadow lane),
    do not also store ``slippage_bps`` on the leg — that would double-count.
    Audit-only keys such as ``applied_slippage_bps`` are ignored here.
    """
    if prices_by_ticker is None:
        leg_a, leg_b = signal["legs"][0], signal["legs"][1]
        prices_by_ticker = {
            leg_a["ticker"]: float(price_a if price_a is not None else 0.0),
            leg_b["ticker"]: float(price_b if price_b is not None else 0.0),
        }
    exit_prices = {k: float(v) for k, v in prices_by_ticker.items()}
    pnl = 0.0
    for leg in signal["legs"]:
        quantity = resolve_leg_filled_qty(leg)
        entry = float(leg["price"])
        exit_price = exit_prices[leg["ticker"]]
        if leg["side"] == "BUY":
            pnl += (exit_price - entry) * quantity
        else:
            pnl += (entry - exit_price) * quantity

        if not include_costs:
            continue

        entry_fee = float(leg.get("fee") or 0.0)
        meta = leg.get("metadata") if isinstance(leg.get("metadata"), dict) else {}
        if entry_fee <= 0.0 and meta:
            entry_fee = float(meta.get("fee") or 0.0)
        pnl -= entry_fee

        if exit_fee_per_leg is None:
            from src.config import settings

            exit_fee = float(settings.FLAT_ORDER_FRICTION_USD)
        else:
            exit_fee = float(exit_fee_per_leg)
        pnl -= exit_fee

        slip_bps = leg.get("slippage_bps")
        if slip_bps is None and meta:
            slip_bps = meta.get("slippage_bps")
        try:
            slip_bps_f = float(slip_bps or 0.0)
        except (TypeError, ValueError):
            slip_bps_f = 0.0
        if slip_bps_f > 0.0:
            pnl -= abs(entry * quantity) * (slip_bps_f / 10_000.0)

    return exit_prices, pnl
