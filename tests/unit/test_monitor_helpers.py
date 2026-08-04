"""
Tests for src/monitor_helpers.py

Covers:
  - is_crypto_pair: detection based on '-USD' substring in either ticker
  - resolve_pair_sector: pair_id lookup, ticker reverse lookup, fallback to 'Unassigned'
  - compute_entry_zscore: scaling disabled, zero baseline, below baseline, above baseline,
    gradual cost ceiling scaling, cap enforcement
"""

import pytest
from src.monitor_helpers import (
    compute_entry_zscore,
    is_crypto_pair,
    is_executable_bid_ask,
    normalize_history_close_frame,
    resolve_hedge_ratio,
    resolve_history_column,
    resolve_kalman_pair_id,
    resolve_pair_sector,
    resolve_profit_guard_friction_pct,
)


# ---------------------------------------------------------------------------
# is_crypto_pair
# ---------------------------------------------------------------------------


class TestIsCryptoPair:
    def test_ticker_a_contains_usd(self):
        assert is_crypto_pair("BTC-USD", "ETH-USD") is True

    def test_ticker_a_only_contains_usd(self):
        assert is_crypto_pair("BTC-USD", "MSFT") is True

    def test_ticker_b_only_contains_usd(self):
        assert is_crypto_pair("AAPL", "ETH-USD") is True

    def test_neither_ticker_is_crypto(self):
        assert is_crypto_pair("AAPL", "MSFT") is False

    def test_empty_tickers_are_not_crypto(self):
        assert is_crypto_pair("", "") is False

    def test_case_sensitive_no_match(self):
        # '-USD' check is case-sensitive; lowercase should not match
        assert is_crypto_pair("btc-usd", "aapl") is False

    def test_substring_match_in_longer_symbol(self):
        # Ensure '-USD' anywhere in the ticker triggers the flag
        assert is_crypto_pair("XRP-USD-EXTRA", "OTHER") is True

    def test_equity_pair_with_dash_not_crypto(self):
        # BRK-B style equity should NOT match
        assert is_crypto_pair("BRK-B", "JPM") is False


# ---------------------------------------------------------------------------
# resolve_history_column / normalize_history_close_frame
# ---------------------------------------------------------------------------


class TestResolveHistoryColumn:
    def test_exact_match_case_insensitive(self):
        assert resolve_history_column(["btc-usd", "ETH-USD"], "BTC-USD") == "btc-usd"

    def test_goog_does_not_bind_googl(self):
        columns = ["GOOGL", "GOOG"]
        assert resolve_history_column(columns, "GOOG") == "GOOG"
        assert resolve_history_column(columns, "GOOGL") == "GOOGL"

    def test_substring_false_positive_rejected(self):
        # Legacy bug: "GOOG" in "GOOGL" would falsely bind the dual-class share.
        assert resolve_history_column(["GOOGL"], "GOOG") is None


class TestNormalizeHistoryCloseFrame:
    def test_flattens_multiindex_close(self):
        import pandas as pd

        arrays = [["Close", "Close"], ["GOOGL", "GOOG"]]
        cols = pd.MultiIndex.from_arrays(arrays)
        df = pd.DataFrame([[1.0, 2.0], [1.1, 2.1]], columns=cols)
        out = normalize_history_close_frame(df)
        assert list(out.columns) == ["GOOGL", "GOOG"]


# ---------------------------------------------------------------------------
# resolve_pair_sector
# ---------------------------------------------------------------------------


class TestResolvePairSector:
    def test_resolves_by_pair_id_directly(self):
        sectors = {"AAPL_MSFT": "Technology", "KO_PEP": "Consumer Staples"}
        result = resolve_pair_sector("AAPL_MSFT", "AAPL", "MSFT", sectors)
        assert result == "Technology"

    def test_falls_back_to_reversed_ticker_key(self):
        # pair_id not found, but reversed "ticker_b_ticker_a" key exists
        sectors = {"MSFT_AAPL": "Technology"}
        result = resolve_pair_sector("AAPL_MSFT", "AAPL", "MSFT", sectors)
        assert result == "Technology"

    def test_returns_unassigned_when_no_match(self):
        result = resolve_pair_sector("AAPL_MSFT", "AAPL", "MSFT", {})
        assert result == "Unassigned"

    def test_pair_id_takes_precedence_over_reversed_key(self):
        sectors = {"AAPL_MSFT": "Direct Match", "MSFT_AAPL": "Reversed Match"}
        result = resolve_pair_sector("AAPL_MSFT", "AAPL", "MSFT", sectors)
        assert result == "Direct Match"

    def test_works_with_crypto_pair_id(self):
        sectors = {"BTC-USD_ETH-USD": "Crypto"}
        result = resolve_pair_sector("BTC-USD_ETH-USD", "BTC-USD", "ETH-USD", sectors)
        assert result == "Crypto"

    def test_empty_sectors_returns_unassigned(self):
        result = resolve_pair_sector("ANY_PAIR", "ANY", "PAIR", {})
        assert result == "Unassigned"


# ---------------------------------------------------------------------------
# compute_entry_zscore
# ---------------------------------------------------------------------------


class TestComputeEntryZscore:
    def test_returns_base_when_scaling_disabled(self):
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=False,
            pair_estimated_cost_pct=0.5,
            cost_baseline=0.1,
            scaling_cap=3.0,
        )
        assert result == 2.0

    def test_returns_base_when_baseline_is_zero(self):
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.5,
            cost_baseline=0.0,
            scaling_cap=3.0,
        )
        assert result == 2.0

    def test_returns_base_when_baseline_is_negative(self):
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.5,
            cost_baseline=-0.1,
            scaling_cap=3.0,
        )
        assert result == 2.0

    def test_returns_base_when_cost_equals_baseline(self):
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.1,
            cost_baseline=0.1,
            scaling_cap=3.0,
        )
        assert result == 2.0

    def test_returns_base_when_cost_below_baseline(self):
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.05,
            cost_baseline=0.1,
            scaling_cap=3.0,
        )
        assert result == 2.0

    def test_scales_gradually_between_baseline_and_cost_ceiling(self):
        result = compute_entry_zscore(
            2.2,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.0045,
            cost_baseline=0.0015,
            scaling_cap=3.0,
            cost_ceiling=0.0125,
        )
        assert result == pytest.approx(3.4)

    def test_scales_zscore_when_cost_above_baseline(self):
        # cost_pct=0.2, baseline=0.1 → scale=2.0 → result = 2.0 * 2.0 = 4.0
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.2,
            cost_baseline=0.1,
            scaling_cap=5.0,
        )
        assert result == pytest.approx(4.0)

    def test_applies_scaling_cap(self):
        # cost_pct=1.0, baseline=0.1 → scale would be 10.0, but capped at 3.0
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=1.0,
            cost_baseline=0.1,
            scaling_cap=3.0,
        )
        assert result == pytest.approx(6.0)

    def test_scaling_exactly_at_cap(self):
        # cost_pct=0.3, baseline=0.1 → scale=3.0, cap=3.0 → scale=3.0
        result = compute_entry_zscore(
            2.0,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.3,
            cost_baseline=0.1,
            scaling_cap=3.0,
        )
        assert result == pytest.approx(6.0)

    def test_scaling_cap_of_one_returns_base(self):
        # Any scale > 1.0 gets capped to 1.0 → result = base_zscore * 1.0
        result = compute_entry_zscore(
            2.5,
            cost_scaling_enabled=True,
            pair_estimated_cost_pct=0.9,
            cost_baseline=0.1,
            scaling_cap=1.0,
        )
        assert result == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# resolve_kalman_pair_id / resolve_hedge_ratio
# ---------------------------------------------------------------------------


def test_resolve_kalman_pair_id_prefers_active_ordering():
    known = {"MSFT_AAPL", "KO_PEP"}
    assert resolve_kalman_pair_id("AAPL", "MSFT", known_ids=known) == "MSFT_AAPL"
    assert resolve_kalman_pair_id("KO", "PEP", known_ids=known) == "KO_PEP"


def test_resolve_kalman_pair_id_falls_back_to_primary():
    assert resolve_kalman_pair_id("AAPL", "MSFT", known_ids={"KO_PEP"}) == "AAPL_MSFT"


class TestResolveHedgeRatio:
    def test_prefers_kalman_beta_over_static_hedge(self):
        pair = {"hedge_ratio": 1.0, "dynamic_beta": 1.2}
        assert resolve_hedge_ratio(pair, kalman_beta=1.85) == pytest.approx(1.85)

    def test_falls_back_to_dynamic_beta_then_static(self):
        pair = {"hedge_ratio": 1.1, "dynamic_beta": 1.4}
        assert resolve_hedge_ratio(pair) == pytest.approx(1.4)
        assert resolve_hedge_ratio({"hedge_ratio": 1.1}) == pytest.approx(1.1)

    def test_invalid_values_fall_back_to_one(self):
        assert resolve_hedge_ratio({}) == 1.0
        assert resolve_hedge_ratio({"hedge_ratio": 0.0, "dynamic_beta": -1.0}) == 1.0


def test_should_take_profit_exit_covers_friction():
    from src.monitor_helpers import should_take_profit_exit

    ok, reason = should_take_profit_exit(
        abs_z_score=0.3,
        take_profit_zscore=0.5,
        directional_pnl=20.0,
        estimated_friction=10.0,
        force_exit_zscore=0.25,
    )
    assert ok is True
    assert reason == "covers_friction"


def test_should_take_profit_exit_force_mean_reversion():
    from src.monitor_helpers import should_take_profit_exit

    ok, reason = should_take_profit_exit(
        abs_z_score=0.1,
        take_profit_zscore=0.5,
        directional_pnl=1.0,
        estimated_friction=12.0,
        force_exit_zscore=0.25,
    )
    assert ok is True
    assert reason == "force_mean_reversion"


def test_should_take_profit_exit_friction_hold():
    from src.monitor_helpers import should_take_profit_exit

    ok, reason = should_take_profit_exit(
        abs_z_score=0.3,
        take_profit_zscore=0.5,
        directional_pnl=1.0,
        estimated_friction=12.0,
        force_exit_zscore=0.25,
    )
    assert ok is False
    assert reason == "friction_hold"


# ---------------------------------------------------------------------------
# executable bid/ask + profit-guard friction floor
# ---------------------------------------------------------------------------


class TestExecutableBidAsk:
    def test_accepts_tight_and_locked_quotes(self):
        assert is_executable_bid_ask(100.0, 100.05) is True
        assert is_executable_bid_ask(100.0, 100.0) is True

    def test_rejects_crossed_missing_or_non_numeric(self):
        assert is_executable_bid_ask(100.05, 100.0) is False
        assert is_executable_bid_ask(0.0, 100.0) is False
        assert is_executable_bid_ask(100.0, 0.0) is False
        assert is_executable_bid_ask("x", 100.0) is False


class TestResolveProfitGuardFrictionPct:
    def test_uses_estimated_cost_when_present(self):
        assert resolve_profit_guard_friction_pct(
            fee_friction_pct=0.00005,
            pair_estimated_cost_pct=0.002,
            gross_notional=1000.0,
            flat_order_friction_usd=0.5,
        ) == pytest.approx(0.002)

    def test_floors_to_flat_over_pair_notional_when_estimate_missing(self):
        # Portfolio-level fee_status understates pair friction; flat/notional must win.
        assert resolve_profit_guard_friction_pct(
            fee_friction_pct=0.00005,
            pair_estimated_cost_pct=0.0,
            gross_notional=500.0,
            flat_order_friction_usd=0.5,
        ) == pytest.approx(0.001)

    def test_does_not_loosen_below_fee_status(self):
        assert resolve_profit_guard_friction_pct(
            fee_friction_pct=0.01,
            pair_estimated_cost_pct=0.002,
            gross_notional=1000.0,
            flat_order_friction_usd=0.5,
        ) == pytest.approx(0.01)
