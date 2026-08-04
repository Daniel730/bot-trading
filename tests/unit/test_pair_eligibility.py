"""Spec 037: pair-eligibility gate unit tests.

These tests pin the rules that protect the live universe from cross-currency,
cross-session, LSE-stamp-duty and cost-above-ceiling pairs. They must remain
green for the strategy to be safe to expand to multi-region.
"""
import pytest

import src.services.pair_eligibility_service as pair_eligibility_service
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


@pytest.fixture(autouse=True)
def active_brokerage_assets(monkeypatch):
    async def is_asset_active(_ticker):
        return True

    monkeypatch.setattr(
        pair_eligibility_service.brokerage_service,
        "is_asset_active",
        is_asset_active,
    )


@pytest.mark.asyncio
async def test_us_pair_admitted_with_reasonable_cost():
    """Two US-listed names share session and currency; expect admit + low cost."""
    result = await evaluate_pair("AAPL", "MSFT", account_currency="EUR")
    assert result.admit is True
    assert result.reason == "admitted"
    assert result.estimated_cost_pct > 0  # FX leg present (EUR account)
    assert result.estimated_cost_pct < 0.02  # well under 2 % round-trip


@pytest.mark.asyncio
async def test_cross_currency_pair_rejected():
    """ASML.AS (EUR) paired with NVDA (USD) must be blocked.

    The eligibility checks run session-first then currency, so for this pair
    the rejection lands on the session rule (EURONEXT vs US_EQUITY). Either
    reason is sufficient — the invariant we care about is that the pair is
    not admitted.
    """
    result = await evaluate_pair("ASML.AS", "NVDA", account_currency="EUR")
    assert result.admit is False
    assert ("cross_currency" in result.reason) or ("different_sessions" in result.reason)


@pytest.mark.asyncio
async def test_cross_session_pair_rejected():
    """ASML.AS (EURONEXT) paired with 9988.HK (HKEX) — different sessions, never coíntegrate."""
    result = await evaluate_pair("ASML.AS", "9988.HK", account_currency="EUR")
    assert result.admit is False
    assert "different_sessions" in result.reason or "cross_currency" in result.reason


@pytest.mark.asyncio
async def test_lse_pair_rejected_due_to_stamp_duty():
    """SHEL.L paired with BP.L is statistically nice but stamp duty kills it."""
    result = await evaluate_pair("SHEL.L", "BP.L", account_currency="EUR")
    assert result.admit is False
    assert "lse" in result.reason.lower()


@pytest.mark.asyncio
async def test_lse_pair_admitted_when_toggle_disabled():
    """If the operator overrides BLOCK_LSE_PAIRS_FOR_SHORT_HOLD, LSE is allowed."""
    result = await evaluate_pair(
        "SHEL.L", "BP.L", account_currency="EUR", block_lse_short_hold=False
    )
    # The cost ceiling may still bite, but at least the LSE-specific block is off.
    assert "lse" not in result.reason.lower()


@pytest.mark.asyncio
async def test_crypto_pair_admitted_when_not_denylisted():
    """Crypto pairs share the 24/7 session and bypass FX/stamp-duty rules."""
    result = await evaluate_pair("ETH-USD", "BTC-USD", account_currency="EUR")
    assert result.admit is True
    assert result.reason == "crypto_pair"


@pytest.mark.asyncio
async def test_btc_bch_denylist_rejects_both_orders(monkeypatch):
    """Default PAIR_DENYLIST quarantine must reject BTC/BCH either order."""
    from src.config import Settings

    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.delenv("PAIR_DENYLIST", raising=False)
    cfg = Settings(_env_file=None)

    forward = await evaluate_pair(
        "BTC-USD",
        "BCH-USD",
        account_currency="EUR",
        denylist=cfg.pair_denylist_ids,
    )
    reverse = await evaluate_pair(
        "BCH-USD",
        "BTC-USD",
        account_currency="EUR",
        denylist=cfg.pair_denylist_ids,
    )
    assert forward.admit is False
    assert reverse.admit is False
    assert "denylisted" in forward.reason
    assert "denylisted" in reverse.reason


@pytest.mark.asyncio
async def test_extreme_hedge_ratio_rejected_even_without_denylist():
    """BTC/BCH-scale betas (~285) fail PAIR_DISCOVERY_MAX_ABS_HEDGE=25."""
    result = await evaluate_pair(
        "BTC-USD",
        "BCH-USD",
        account_currency="EUR",
        denylist=[],
        hedge_ratio=285.0,
        max_abs_hedge=25.0,
    )
    assert result.admit is False
    assert "hedge_ratio_extreme" in result.reason


@pytest.mark.asyncio
async def test_zero_hedge_does_not_block_bootstrap_warmup():
    """Persisted hedge_ratio=0 before warm-up must still reach cointegration."""
    result = await evaluate_pair(
        "KO",
        "PEP",
        account_currency="EUR",
        denylist=[],
        hedge_ratio=0.0,
        max_abs_hedge=25.0,
    )
    assert result.admit is True


@pytest.mark.asyncio
async def test_correlation_below_discovery_floor_rejected():
    """Align with restored PAIR_DISCOVERY_MIN_CORRELATION=0.70."""
    result = await evaluate_pair(
        "KO",
        "PEP",
        account_currency="EUR",
        denylist=[],
        correlation=0.40,
        min_correlation=0.70,
    )
    assert result.admit is False
    assert "correlation_below_floor" in result.reason


@pytest.mark.asyncio
async def test_pvalue_above_discovery_ceiling_rejected():
    result = await evaluate_pair(
        "KO",
        "PEP",
        account_currency="EUR",
        denylist=[],
        correlation=0.95,
        p_value=0.20,
        min_correlation=0.70,
        max_pvalue=0.05,
    )
    assert result.admit is False
    assert "pvalue_above_ceiling" in result.reason


@pytest.mark.asyncio
async def test_explicit_not_cointegrated_rejected():
    result = await evaluate_pair(
        "KO",
        "PEP",
        account_currency="EUR",
        denylist=[],
        is_cointegrated=False,
    )
    assert result.admit is False
    assert result.reason == "not_cointegrated"


@pytest.mark.asyncio
async def test_mixed_crypto_equity_rejected():
    """Pairing a crypto leg with an equity leg has no cointegration premise."""
    result = await evaluate_pair("ETH-USD", "AAPL", account_currency="EUR")
    assert result.admit is False
    assert "mixed" in result.reason.lower()


@pytest.mark.asyncio
async def test_cost_ceiling_rejects_expensive_pairs():
    """A very tight cost ceiling rejects even otherwise-clean pairs."""
    result = await evaluate_pair(
        "AAPL", "MSFT", account_currency="EUR", max_round_trip_cost_pct=0.0001
    )
    assert result.admit is False
    assert "cost_above_ceiling" in result.reason


@pytest.mark.asyncio
async def test_eu_xetra_euronext_blocked_by_session():
    """ASML.AS (EURONEXT) and SAP.DE (XETRA) trade in overlapping wall-clock
    windows but on different exchanges with different microstructure. We
    classify them as different sessions to keep the eligibility rule strict.
    """
    result = await evaluate_pair("ASML.AS", "SAP.DE", account_currency="EUR")
    assert result.admit is False
    # The rule blocks them at the session check.
    assert "different_sessions" in result.reason


@pytest.mark.asyncio
async def test_filter_pair_universe_splits_correctly():
    """Smoke test for the bulk filter used by monitor.initialize_pairs."""
    candidate = [
        {"ticker_a": "AAPL", "ticker_b": "MSFT"},
        {"ticker_a": "SHEL.L", "ticker_b": "BP.L"},
        {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD"},
        {"ticker_a": "ASML.AS", "ticker_b": "NVDA"},
        {"ticker_a": "BTC-USD", "ticker_b": "BCH-USD", "hedge_ratio": 285.0},
    ]
    admitted, rejected = await filter_pair_universe(
        candidate, account_currency="EUR", denylist=["BTC-USD_BCH-USD"]
    )
    admitted_keys = {(p["ticker_a"], p["ticker_b"]) for p in admitted}
    rejected_keys = {(p["ticker_a"], p["ticker_b"]) for p in rejected}
    assert ("AAPL", "MSFT") in admitted_keys
    assert ("ETH-USD", "BTC-USD") in admitted_keys
    assert ("SHEL.L", "BP.L") in rejected_keys
    assert ("ASML.AS", "NVDA") in rejected_keys
    assert ("BTC-USD", "BCH-USD") in rejected_keys
    # Each admitted entry should carry its cost estimate.
    for entry in admitted:
        assert "estimated_cost_pct" in entry


@pytest.mark.asyncio
async def test_filter_pair_universe_rejects_extreme_hedge_without_denylist():
    candidate = [
        {
            "ticker_a": "BTC-USD",
            "ticker_b": "BCH-USD",
            "hedge_ratio": 280.0,
            "is_cointegrated": True,
        },
        {
            "ticker_a": "KO",
            "ticker_b": "PEP",
            "hedge_ratio": 0.0,
            "is_cointegrated": False,
        },
    ]
    admitted, rejected = await filter_pair_universe(
        candidate,
        account_currency="EUR",
        denylist=[],
        max_abs_hedge=25.0,
    )
    admitted_keys = {(p["ticker_a"], p["ticker_b"]) for p in admitted}
    rejected_keys = {(p["ticker_a"], p["ticker_b"]) for p in rejected}
    assert ("BTC-USD", "BCH-USD") in rejected_keys
    # Bootstrap rows with hedge=0 / is_cointegrated=False still admit.
    assert ("KO", "PEP") in admitted_keys
    assert "hedge_ratio_extreme" in rejected[0]["rejection"]["reason"]


@pytest.mark.asyncio
async def test_filter_pair_universe_enforces_correlation_when_present():
    candidate = [
        {
            "ticker_a": "KO",
            "ticker_b": "PEP",
            "correlation": 0.55,
            "p_value": 0.01,
            "hedge_ratio": 1.1,
        },
        {
            "ticker_a": "MA",
            "ticker_b": "V",
            "correlation": 0.92,
            "p_value": 0.01,
            "hedge_ratio": 1.0,
        },
    ]
    admitted, rejected = await filter_pair_universe(
        candidate,
        account_currency="EUR",
        denylist=[],
        min_correlation=0.70,
        max_pvalue=0.05,
        max_abs_hedge=25.0,
    )
    assert [(p["ticker_a"], p["ticker_b"]) for p in admitted] == [("MA", "V")]
    assert "correlation_below_floor" in rejected[0]["rejection"]["reason"]


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


# ---- Spec 038: stamp-duty asymmetry + EU continental session group --------


def test_hk_stamp_duty_is_two_sided():
    """HK stamp duty is charged on BOTH buy and sell, so a round-trip pair
    pays 4 × stamp_duty_pct in total (2 sides × 2 legs), not 2× as the
    pre-038 model assumed.
    """
    # Pair on HKEX, account in EUR (FX leg present).
    cost = estimate_round_trip_cost_pct("9988.HK", "0700.HK", account_currency="EUR")
    # Stamp duty contribution alone: 2 legs × 2 sides × 0.0013 = 0.0052
    # Plus FX 4 × 0.0015 = 0.0060, plus spread 2 × 0.0015 = 0.0030
    # Total ~ 0.0142. Pin a lower bound that is comfortably above the
    # legacy two-sided model (which would give ~0.012).
    assert cost > 0.013


def test_swiss_stamp_duty_is_two_sided():
    """SIX Swiss stamp duty is charged per side. A pair on SIX should reflect
    the doubled stamp duty in its round-trip cost estimate.
    """
    # Synthetic Swiss pair (NESN.SW / ROG.SW) — both on SIX.
    swiss = estimate_round_trip_cost_pct("NESN.SW", "ROG.SW", account_currency="EUR")
    # Per-side stamp duty: 2 legs × 2 sides × 0.00075 = 0.003
    # Plus FX 4 × 0.0015 = 0.006, plus spread 2 × 0.0008 = 0.0016
    # Lower bound to make sure the doubling actually applies.
    assert swiss > 0.009


def test_uk_stamp_duty_remains_one_sided():
    """UK SDRT is buy-only. A round-trip pair pays 2 × 0.5 % (one buy per
    leg), not 4 × 0.5 %. The legacy model is correct here; this test pins
    the invariant so a careless refactor doesn't accidentally double UK.
    """
    cost = estimate_round_trip_cost_pct("SHEL.L", "BP.L", account_currency="EUR")
    # If UK were treated as per-side, cost would jump above 2 %. It must
    # stay below.
    assert cost < 0.018


@pytest.mark.asyncio
async def test_eu_continental_overlap_default_blocks_xetra_euronext():
    """Default behaviour (flag off): ASML.AS / SAP.DE remains blocked."""
    result = await evaluate_pair("ASML.AS", "SAP.DE", account_currency="EUR")
    assert result.admit is False
    assert "different_sessions" in result.reason


@pytest.mark.asyncio
async def test_eu_continental_overlap_admits_xetra_euronext_when_enabled():
    """Spec 038: with the EU-overlap flag on, EURONEXT and XETRA pair up."""
    result = await evaluate_pair(
        "ASML.AS",
        "SAP.DE",
        account_currency="EUR",
        allow_eu_continental_overlap=True,
    )
    assert result.admit is True
    assert result.reason == "admitted"


@pytest.mark.asyncio
async def test_eu_continental_overlap_does_not_unlock_cross_region():
    """The EU-overlap flag must NOT also let HK/EU or US/EU pairs through —
    those are still blocked by the strict session rule."""
    # HK <-> EU: still rejected even with the flag on.
    hk_eu = await evaluate_pair(
        "9988.HK",
        "ASML.AS",
        account_currency="EUR",
        allow_eu_continental_overlap=True,
    )
    assert hk_eu.admit is False
    # US <-> EU: still rejected as cross-currency / cross-session.
    us_eu = await evaluate_pair(
        "AAPL",
        "ASML.AS",
        account_currency="EUR",
        allow_eu_continental_overlap=True,
    )
    assert us_eu.admit is False


@pytest.mark.asyncio
async def test_filter_pair_universe_passes_eu_overlap_flag():
    """Bulk filter must respect the new flag end-to-end."""
    candidate = [
        {"ticker_a": "ASML.AS", "ticker_b": "SAP.DE"},
    ]
    admitted_off, _ = await filter_pair_universe(candidate, account_currency="EUR")
    admitted_on, _ = await filter_pair_universe(
        candidate, account_currency="EUR", allow_eu_continental_overlap=True
    )
    assert admitted_off == []
    assert len(admitted_on) == 1


@pytest.mark.asyncio
async def test_shadow_paper_skips_broker_asset_gate(monkeypatch):
    """PAPER_TRADING=true must not empty the universe when Alpaca is unreachable."""
    calls: list[str] = []

    async def is_asset_active(ticker: str) -> bool:
        calls.append(ticker)
        return False

    monkeypatch.setattr(pair_eligibility_service.brokerage_service, "is_asset_active", is_asset_active)
    monkeypatch.setattr(
        "src.config.settings.PAPER_TRADING",
        True,
        raising=False,
    )
    # Force default path (None) rather than fixture True via require flag.
    result = await evaluate_pair(
        "BTC-USD",
        "ETH-USD",
        account_currency="EUR",
        require_broker_active=None,
    )
    assert result.admit is True
    assert result.reason == "crypto_pair"
    assert calls == []


@pytest.mark.asyncio
async def test_broker_path_still_requires_active_assets(monkeypatch):
    """Broker-paper / live must fail closed when legs are inactive on Alpaca."""

    async def is_asset_active(_ticker: str) -> bool:
        return False

    monkeypatch.setattr(pair_eligibility_service.brokerage_service, "is_asset_active", is_asset_active)
    result = await evaluate_pair(
        "BTC-USD",
        "ETH-USD",
        account_currency="EUR",
        require_broker_active=True,
    )
    assert result.admit is False
    assert result.reason.startswith("asset_not_active_in_brokerage:")
