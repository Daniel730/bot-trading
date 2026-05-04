from __future__ import annotations

from collections.abc import Callable

from src.monitor_helpers import is_crypto_pair


def _pair_key(pair: dict) -> tuple[str, str]:
    return (str(pair["ticker_a"]).upper(), str(pair["ticker_b"]).upper())


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
    """
    seen_crypto: set[tuple[str, str]] = set()
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

    seen_equity: set[tuple[str, str]] = set()
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
        # Note: pairs admitted with is_cointegrated=False (rolling stability fail)
        # are NOT skipped here — process_pair checks the flag and skips signal
        # generation, but we still need prices fetched so z-scores update.
        # Only skip pairs explicitly marked non-cointegrated AND non-crypto
        # (crypto pairs always need price updates for exit monitoring).
        if not is_crypto_pair(ticker_a, ticker_b):
            if not pair.get("is_cointegrated", False) and not is_market_open(ticker_a):
                continue
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


def calculate_realized_pnl(signal: dict, *, price_a: float, price_b: float) -> tuple[dict[str, float], float]:
    leg_a, leg_b = signal["legs"][0], signal["legs"][1]
    exit_prices = {leg_a["ticker"]: float(price_a), leg_b["ticker"]: float(price_b)}
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