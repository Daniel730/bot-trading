"""
Tests for src/monitor_scan_helpers.py

Covers:
  - build_scan_pairs: filtering by cointegration, crypto market-hours bypass, equity market gate
  - summarize_scan_iteration: counting active signals and vetoed signals
  - build_close_orders: side reversal, price assignment, dev-mode ticker substitution
  - calculate_realized_pnl: long leg PnL, short leg PnL, combined two-leg PnL
"""

import pytest
from src.monitor_scan_helpers import (
    build_close_orders,
    build_scan_pairs,
    calculate_realized_pnl,
    summarize_scan_iteration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pair(ticker_a: str, ticker_b: str, is_cointegrated: bool = True) -> dict:
    return {"ticker_a": ticker_a, "ticker_b": ticker_b, "is_cointegrated": is_cointegrated}


def _signal(legs: list[dict]) -> dict:
    return {"signal_id": "sig-1", "legs": legs}


def _leg(ticker: str, side: str, quantity: float, price: float) -> dict:
    return {"ticker": ticker, "side": side, "quantity": quantity, "price": price}


# ---------------------------------------------------------------------------
# build_scan_pairs
# ---------------------------------------------------------------------------


class TestBuildScanPairs:
    def test_equity_pair_included_when_market_open(self):
        pairs = [_pair("AAPL", "MSFT")]
        scan, tickers = build_scan_pairs(pairs, is_market_open=lambda t: True)
        assert len(scan) == 1
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_equity_pair_excluded_when_market_closed(self):
        pairs = [_pair("AAPL", "MSFT")]
        scan, tickers = build_scan_pairs(pairs, is_market_open=lambda t: False)
        assert scan == []
        assert tickers == []

    def test_crypto_pair_always_included_regardless_of_market_open(self):
        pairs = [_pair("BTC-USD", "ETH-USD")]
        scan, tickers = build_scan_pairs(pairs, is_market_open=lambda t: False)
        assert len(scan) == 1
        assert "BTC-USD" in tickers
        assert "ETH-USD" in tickers

    def test_non_cointegrated_pair_excluded(self):
        pairs = [_pair("AAPL", "MSFT", is_cointegrated=False)]
        scan, tickers = build_scan_pairs(pairs, is_market_open=lambda t: True)
        assert scan == []
        assert tickers == []

    def test_mixed_pairs_filtered_correctly(self):
        pairs = [
            _pair("AAPL", "MSFT"),              # equity, market open → included
            _pair("KO", "PEP", False),           # not cointegrated → excluded
            _pair("BTC-USD", "ETH-USD"),         # crypto → included (market closed)
            _pair("JPM", "GS"),                  # equity, market closed → excluded
        ]
        open_tickers = {"AAPL", "MSFT"}
        scan, tickers = build_scan_pairs(
            pairs,
            is_market_open=lambda t: t in open_tickers,
        )
        included_a = [p["ticker_a"] for p in scan]
        assert "AAPL" in included_a
        assert "BTC-USD" in included_a
        assert "KO" not in included_a
        assert "JPM" not in included_a

    def test_default_is_cointegrated_true_when_key_missing(self):
        # Pair dict without 'is_cointegrated' key defaults to True
        pair = {"ticker_a": "AAPL", "ticker_b": "MSFT"}
        scan, _ = build_scan_pairs([pair], is_market_open=lambda t: True)
        assert len(scan) == 1

    def test_empty_active_pairs_returns_empty(self):
        scan, tickers = build_scan_pairs([], is_market_open=lambda t: True)
        assert scan == []
        assert tickers == []

    def test_tickers_list_order_matches_pair_order(self):
        pairs = [_pair("AAPL", "MSFT"), _pair("BTC-USD", "ETH-USD")]
        _, tickers = build_scan_pairs(pairs, is_market_open=lambda t: True)
        assert tickers == ["AAPL", "MSFT", "BTC-USD", "ETH-USD"]


# ---------------------------------------------------------------------------
# summarize_scan_iteration
# ---------------------------------------------------------------------------


class TestSummarizeScanIteration:
    def test_counts_active_signals_above_threshold(self):
        results = [
            {"confidence": 0.8, "verdict": "EXECUTED"},
            {"confidence": 0.6, "verdict": "APPROVED"},
            {"confidence": 0.4, "verdict": "VETOED"},
        ]
        active, vetoed = summarize_scan_iteration(results, min_ai_confidence=0.5)
        assert active == 2
        assert vetoed == 1

    def test_no_signals_when_all_below_threshold(self):
        results = [{"confidence": 0.3}, {"confidence": 0.1}]
        active, vetoed = summarize_scan_iteration(results, min_ai_confidence=0.5)
        assert active == 0

    def test_handles_none_results(self):
        results = [None, {"confidence": 0.8}, None]
        active, vetoed = summarize_scan_iteration(results, min_ai_confidence=0.5)
        assert active == 1

    def test_counts_vetoed_correctly(self):
        results = [
            {"verdict": "VETOED", "confidence": 0.2},
            {"verdict": "VETOED", "confidence": 0.3},
            {"verdict": "EXECUTED", "confidence": 0.9},
        ]
        _, vetoed = summarize_scan_iteration(results, min_ai_confidence=0.5)
        assert vetoed == 2

    def test_empty_results_returns_zeros(self):
        active, vetoed = summarize_scan_iteration([], min_ai_confidence=0.5)
        assert active == 0
        assert vetoed == 0

    def test_signal_exactly_at_threshold_not_counted(self):
        # Confidence equal to threshold → NOT above, so not counted
        results = [{"confidence": 0.5}]
        active, _ = summarize_scan_iteration(results, min_ai_confidence=0.5)
        assert active == 0

    def test_result_without_confidence_key_not_counted(self):
        results = [{"verdict": "EXECUTED"}]
        active, _ = summarize_scan_iteration(results, min_ai_confidence=0.5)
        assert active == 0


# ---------------------------------------------------------------------------
# build_close_orders
# ---------------------------------------------------------------------------


class TestBuildCloseOrders:
    def _default_signal(self):
        return _signal([
            _leg("AAPL", "BUY", 10.0, 150.0),
            _leg("MSFT", "SELL", 5.0, 300.0),
        ])

    def test_reverses_buy_to_sell(self):
        sig = self._default_signal()
        orders = build_close_orders(sig, price_a=160.0, price_b=310.0, dev_mode=False, dev_execution_tickers={})
        assert orders[0]["side"] == "SELL"

    def test_reverses_sell_to_buy(self):
        sig = self._default_signal()
        orders = build_close_orders(sig, price_a=160.0, price_b=310.0, dev_mode=False, dev_execution_tickers={})
        assert orders[1]["side"] == "BUY"

    def test_assigns_price_a_to_first_leg(self):
        sig = self._default_signal()
        orders = build_close_orders(sig, price_a=160.0, price_b=310.0, dev_mode=False, dev_execution_tickers={})
        assert orders[0]["price"] == 160.0

    def test_assigns_price_b_to_second_leg(self):
        sig = self._default_signal()
        orders = build_close_orders(sig, price_a=160.0, price_b=310.0, dev_mode=False, dev_execution_tickers={})
        assert orders[1]["price"] == 310.0

    def test_display_ticker_always_original(self):
        sig = self._default_signal()
        orders = build_close_orders(sig, price_a=160.0, price_b=310.0, dev_mode=False, dev_execution_tickers={})
        assert orders[0]["display_ticker"] == "AAPL"
        assert orders[1]["display_ticker"] == "MSFT"

    def test_dev_mode_substitutes_ticker(self):
        sig = self._default_signal()
        orders = build_close_orders(
            sig,
            price_a=160.0,
            price_b=310.0,
            dev_mode=True,
            dev_execution_tickers={"AAPL": "AAPL_DEV", "MSFT": "MSFT_DEV"},
        )
        assert orders[0]["ticker"] == "AAPL_DEV"
        assert orders[1]["ticker"] == "MSFT_DEV"

    def test_dev_mode_passes_through_unmapped_ticker(self):
        sig = self._default_signal()
        orders = build_close_orders(
            sig,
            price_a=160.0,
            price_b=310.0,
            dev_mode=True,
            dev_execution_tickers={},  # No substitution defined
        )
        assert orders[0]["ticker"] == "AAPL"

    def test_prod_mode_ignores_dev_tickers(self):
        sig = self._default_signal()
        orders = build_close_orders(
            sig,
            price_a=160.0,
            price_b=310.0,
            dev_mode=False,
            dev_execution_tickers={"AAPL": "AAPL_DEV"},
        )
        assert orders[0]["ticker"] == "AAPL"

    def test_quantity_preserved_as_float(self):
        sig = self._default_signal()
        orders = build_close_orders(sig, price_a=160.0, price_b=310.0, dev_mode=False, dev_execution_tickers={})
        assert orders[0]["quantity"] == 10.0
        assert orders[1]["quantity"] == 5.0

    def test_returns_two_orders_for_two_legs(self):
        sig = self._default_signal()
        orders = build_close_orders(sig, price_a=160.0, price_b=310.0, dev_mode=False, dev_execution_tickers={})
        assert len(orders) == 2


# ---------------------------------------------------------------------------
# calculate_realized_pnl
# ---------------------------------------------------------------------------


class TestCalculateRealizedPnl:
    def test_buy_leg_profit(self):
        # BUY at 100, exit at 110 with qty=10 → PnL = (110-100)*10 = 100
        sig = _signal([
            _leg("AAPL", "BUY", 10.0, 100.0),
            _leg("MSFT", "SELL", 5.0, 200.0),
        ])
        exit_prices, pnl = calculate_realized_pnl(sig, price_a=110.0, price_b=200.0)
        # AAPL: BUY, (110-100)*10=100; MSFT: SELL, (200-200)*5=0
        assert pnl == pytest.approx(100.0)

    def test_buy_leg_loss(self):
        sig = _signal([
            _leg("AAPL", "BUY", 10.0, 100.0),
            _leg("MSFT", "SELL", 5.0, 200.0),
        ])
        exit_prices, pnl = calculate_realized_pnl(sig, price_a=90.0, price_b=200.0)
        # AAPL: BUY, (90-100)*10=-100; MSFT: SELL, 0
        assert pnl == pytest.approx(-100.0)

    def test_sell_leg_profit(self):
        # SELL at 200, exit at 180 with qty=5 → PnL = (200-180)*5 = 100
        sig = _signal([
            _leg("AAPL", "BUY", 10.0, 100.0),
            _leg("MSFT", "SELL", 5.0, 200.0),
        ])
        exit_prices, pnl = calculate_realized_pnl(sig, price_a=100.0, price_b=180.0)
        # AAPL: BUY, 0; MSFT: SELL, (200-180)*5=100
        assert pnl == pytest.approx(100.0)

    def test_sell_leg_loss(self):
        sig = _signal([
            _leg("AAPL", "BUY", 10.0, 100.0),
            _leg("MSFT", "SELL", 5.0, 200.0),
        ])
        exit_prices, pnl = calculate_realized_pnl(sig, price_a=100.0, price_b=220.0)
        # AAPL: BUY, 0; MSFT: SELL, (200-220)*5=-100
        assert pnl == pytest.approx(-100.0)

    def test_combined_two_leg_pnl(self):
        # Short-Long pair: AAPL BUY 10@150, MSFT SELL 5@300
        # Exit: AAPL@160, MSFT@280
        # AAPL: BUY, (160-150)*10=100; MSFT: SELL, (300-280)*5=100 → total 200
        sig = _signal([
            _leg("AAPL", "BUY", 10.0, 150.0),
            _leg("MSFT", "SELL", 5.0, 300.0),
        ])
        exit_prices, pnl = calculate_realized_pnl(sig, price_a=160.0, price_b=280.0)
        assert pnl == pytest.approx(200.0)

    def test_returns_exit_prices_dict(self):
        sig = _signal([
            _leg("AAPL", "BUY", 10.0, 150.0),
            _leg("MSFT", "SELL", 5.0, 300.0),
        ])
        exit_prices, _ = calculate_realized_pnl(sig, price_a=160.0, price_b=280.0)
        assert exit_prices == {"AAPL": 160.0, "MSFT": 280.0}

    def test_zero_pnl_when_prices_unchanged(self):
        sig = _signal([
            _leg("AAPL", "BUY", 10.0, 150.0),
            _leg("MSFT", "SELL", 5.0, 300.0),
        ])
        _, pnl = calculate_realized_pnl(sig, price_a=150.0, price_b=300.0)
        assert pnl == pytest.approx(0.0)

    def test_crypto_legs_same_logic(self):
        sig = _signal([
            _leg("BTC-USD", "BUY", 0.1, 60000.0),
            _leg("ETH-USD", "SELL", 1.0, 3000.0),
        ])
        # BTC: BUY, (62000-60000)*0.1=200; ETH: SELL, (3000-2900)*1.0=100 → total 300
        _, pnl = calculate_realized_pnl(sig, price_a=62000.0, price_b=2900.0)
        assert pnl == pytest.approx(300.0)
