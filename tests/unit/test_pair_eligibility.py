"""Spec 037: pair-eligibility gate unit tests.

These tests pin the rules that protect the live universe from cross-currency,
cross-session, LSE-stamp-duty and cost-above-ceiling pairs. They must remain
green for the strategy to be safe to expand to multi-region.
"""
from src.services.pair_eligibility_service import (
    EligibilityResult,
    evaluate_pair,
    filter_pair_universe,
)
from src.services.venue_metadata import (
    estimate_round_trip_cost_pct,
    get_venue_profile,
    same_currency,
    same_session,
)


def test_us_pair_admitted_with_reasonable_cost():
    """Two US-listed names share session and currency; expect admit + low cost."""
    result = evaluate_pair("AAPL", "MSFT", account_currency="EUR")
    assert result.admit is True
    assert result.reason == "admitted"
    assert result.estimated_cost_pct > 0  # FX leg present (EUR account)
    assert result.estimated_cost_pct < 0.02  # well under 2 % round-trip


def test_cross_currency_pair_rejected():
    """ASML.AS (EUR) paired with NVDA (USD) must be blocked.

    The eligibility checks run session-first then currency, so for this pair
    the rejection lands on the session rule (EURONEXT vs US_EQUITY). Either
    reason is sufficient — the invariant we care about is that the pair is
    not admitted.
    """
    result = evaluate_pair("ASML.AS", "NVDA", account_currency="EUR")
    assert result.admit is False
    assert ("cross_currency" in result.reason) or ("different_sessions" in result.reason)


def test_cross_session_pair_rejected():
    """ASML.AS (EURONEXT) paired with 9988.HK (HKEX) — different sessions, never coíntegrate."""
    result = evaluate_pair("ASML.AS", "9988.HK", account_currency="EUR")
    assert result.admit is False
    assert "different_sessions" in result.reason or "cross_currency" in result.reason


def test_lse_pair_rejected_due_to_stamp_duty():
    """SHEL.L paired with BP.L is statistically nice but stamp duty kills it."""
    result = evaluate_pair("SHEL.L", "BP.L", account_currency="EUR")
    assert result.admit is False
    assert "lse" in result.reason.lower()


def test_lse_pair_admitted_when_toggle_disabled():
    """If the operator overrides BLOCK_LSE_PAIRS_FOR_SHORT_HOLD, LSE is allowed."""
    result = evaluate_pair(
        "SHEL.L", "BP.L", account_currency="EUR", block_lse_short_hold=False
    )
    # The cost ceiling may still bite, but at least the LSE-specific block is off.
    assert "lse" not in result.reason.lower()


def test_crypto_pair_always_admitted():
    """Crypto pairs share the 24/7 session and bypass FX/stamp-duty rules."""
    result = evaluate_pair("ETH-USD", "BTC-USD", account_currency="EUR")
    assert result.admit is True
    assert result.reason == "crypto_pair"


def test_mixed_crypto_equity_rejected():
    """Pairing a crypto leg with an equity leg has no cointegration premise."""
    result = evaluate_pair("ETH-USD", "AAPL", account_currency="EUR")
    assert result.admit is False
    assert "mixed" in result.reason.lower()


def test_cost_ceiling_rejects_expensive_pairs():
    """A very tight cost ceiling rejects even otherwise-clean pairs."""
    result = evaluate_pair(
        "AAPL", "MSFT", account_currency="EUR", max_round_trip_cost_pct=0.0001
    )
    assert result.admit is False
    assert "cost_above_ceiling" in result.reason


def test_eu_xetra_euronext_blocked_by_session():
    """ASML.AS (EURONEXT) and SAP.DE (XETRA) trade in overlapping wall-clock
    windows but on different exchanges with different microstructure. We
    classify them as different sessions to keep the eligibility rule strict.
    """
    result = evaluate_pair("ASML.AS", "SAP.DE", account_currency="EUR")
    assert result.admit is False
    # The rule blocks them at the session check.
    assert "different_sessions" in result.reason


def test_filter_pair_universe_splits_correctly():
    """Smoke test for the bulk filter used by monitor.initialize_pairs."""
    candidate = [
        {"ticker_a": "AAPL", "ticker_b": "MSFT"},
        {"ticker_a": "SHEL.L", "ticker_b": "BP.L"},
        {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD"},
        {"ticker_a": "ASML.AS", "ticker_b": "NVDA"},
    ]
    admitted, rejected = filter_pair_universe(
        candidate, account_currency="EUR"
    )
    admitted_keys = {(p["ticker_a"], p["ticker_b"]) for p in admitted}
    rejected_keys = {(p["ticker_a"], p["ticker_b"]) for p in rejected}
    assert ("AAPL", "MSFT") in admitted_keys
    assert ("ETH-USD", "BTC-USD") in admitted_keys
    assert ("SHEL.L", "BP.L") in rejected_keys
    assert ("ASML.AS", "NVDA") in rejected_keys
    # Each admitted entry should carry its cost estimate.
    for entry in admitted:
        assert "estimated_cost_pct" in entry


def test_venue_metadata_helpers():
    """Direct sanity checks on the suffix-driven venue lookup."""
    assert get_venue_profile("AAPL").currency == "USD"
    assert get_venue_profile("ASML.AS").currency == "EUR"
    assert get_venue_profile("9988.HK").currency == "HKD"
    assert get_venue_profile("SHEL.L").currency == "GBP"
    assert get_venue_profile("ETH-USD").market_id == "CRYPTO_24_7"
    assert same_session("KO", "PEP") is True
    assert same_session("KO", "ASML.AS") is False
    assert same_currency("KO", "PEP") is True
    assert same_currency("KO", "ASML.AS") is False


def test_estimate_round_trip_cost_includes_stamp_duty_for_lse():
    """LSE pairs should have a cost noticeably higher than US pairs."""
    us_cost = estimate_round_trip_cost_pct("AAPL", "MSFT", account_currency="EUR")
    lse_cost = estimate_round_trip_cost_pct("SHEL.L", "BP.L", account_currency="EUR")
    # Two stamp duty legs at 0.5 % each = 1 % minimum delta.
    assert lse_cost - us_cost > 0.009
