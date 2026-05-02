from __future__ import annotations

from collections.abc import Callable

from src.monitor_helpers import is_crypto_pair


def build_scan_pairs(active_pairs: list[dict], is_market_open: Callable[[str], bool]) -> tuple[list[dict], list[str]]:
    scan_pairs: list[dict] = []
    all_tickers: list[str] = []
    for pair in active_pairs:
        ticker_a, ticker_b = pair["ticker_a"], pair["ticker_b"]
        if not pair.get("is_cointegrated", True):
            continue
        if not is_crypto_pair(ticker_a, ticker_b) and not is_market_open(ticker_a):
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
    price_a: float,
    price_b: float,
    dev_mode: bool,
    dev_execution_tickers: dict[str, str],
) -> list[dict]:
    close_orders: list[dict] = []
    first_leg_ticker = signal["legs"][0]["ticker"]
    for leg in signal["legs"]:
        ticker = leg["ticker"]
        quantity = float(leg["quantity"])
        side = "SELL" if leg["side"] == "BUY" else "BUY"
        execution_ticker = dev_execution_tickers.get(ticker, ticker) if dev_mode else ticker
        leg_price = price_a if ticker == first_leg_ticker else price_b
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
    exit_prices = {leg_a["ticker"]: price_a, leg_b["ticker"]: price_b}
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
