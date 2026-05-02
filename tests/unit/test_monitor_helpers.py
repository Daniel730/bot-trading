"""
Tests for src/monitor_helpers.py

Covers:
  - is_crypto_pair: detection based on '-USD' substring in either ticker
  - resolve_pair_sector: pair_id lookup, ticker reverse lookup, fallback to 'Unassigned'
  - compute_entry_zscore: scaling disabled, zero baseline, below baseline, above baseline, cap enforcement
"""

import pytest
from src.monitor_helpers import compute_entry_zscore, is_crypto_pair, resolve_pair_sector


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