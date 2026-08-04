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
        quantity = float(leg["quantity"])
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
            }
        )
    return close_orders


def calculate_realized_pnl(
    signal: dict,
    *,
    prices_by_ticker: dict[str, float] | None = None,
    price_a: float | None = None,
    price_b: float | None = None,
) -> tuple[dict[str, float], float]:
    if prices_by_ticker is None:
        leg_a, leg_b = signal["legs"][0], signal["legs"][1]
        prices_by_ticker = {
            leg_a["ticker"]: float(price_a if price_a is not None else 0.0),
            leg_b["ticker"]: float(price_b if price_b is not None else 0.0),
        }
    exit_prices = {k: float(v) for k, v in prices_by_ticker.items()}
    pnl = 0.0
    for leg in signal["legs"]:
        quantity = leg["quantity"]
        entry = leg["price"]
        exit_price = exit_prices[leg["ticker"]]
        if leg["side"] == "BUY":
            pnl += (exit_price - entry) * quantity
        else:
            pnl += (entry - exit_price) * quantity
    return exit_prices, pnl
