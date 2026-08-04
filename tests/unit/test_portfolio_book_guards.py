"""Unit tests for portfolio overcrowding / correlation book guards."""
from src.services.portfolio_book_guards import (
    canonical_book_symbol,
    check_max_open_pairs,
    check_portfolio_gross_notional,
    check_projected_sector_exposure,
    find_shared_leg_conflict,
    gross_notional_from_signals,
    normalize_sector_label,
)
from src.services.pair_discovery_helpers import select_rotation_actions


def test_normalize_sector_label_unifies_legacy_defaults():
    assert normalize_sector_label("General") == "Unassigned"
    assert normalize_sector_label("unknown") == "Unassigned"
    assert normalize_sector_label("") == "Unassigned"
    assert normalize_sector_label("Technology") == "Technology"


def test_canonical_book_symbol_strips_hyphens():
    assert canonical_book_symbol("BTC-USD") == "BTCUSD"
    assert canonical_book_symbol("btc/usd") == "BTCUSD"


def test_shared_leg_conflict_detects_overlap():
    open_signals = [
        {
            "signal_id": "sig-1",
            "legs": [{"ticker": "NVDA"}, {"ticker": "AMD"}],
            "total_cost_basis": 100.0,
        }
    ]
    conflict = find_shared_leg_conflict("NVDA", "INTC", open_signals)
    assert conflict is not None
    assert conflict["overlap"] == ["NVDA"]
    assert conflict["signal_id"] == "sig-1"

    assert find_shared_leg_conflict("KO", "PEP", open_signals) is None


def test_shared_leg_conflict_matches_crypto_canonical_forms():
    open_signals = [
        {
            "signal_id": "sig-crypto",
            "legs": [{"ticker": "BTC-USD"}, {"ticker": "ETH-USD"}],
            "total_cost_basis": 80.0,
        }
    ]
    conflict = find_shared_leg_conflict("BTC-USD", "SOL-USD", open_signals)
    assert conflict is not None
    assert "BTCUSD" in conflict["overlap"]


def test_max_open_pairs_blocks_at_limit():
    ok = check_max_open_pairs(3, 8)
    assert ok["allowed"] is True
    blocked = check_max_open_pairs(8, 8)
    assert blocked["allowed"] is False
    assert "MAX_OPEN_PAIRS" in blocked["reason"]
    disabled = check_max_open_pairs(99, 0)
    assert disabled["allowed"] is True


def test_portfolio_gross_notional_cap():
    ok = check_portfolio_gross_notional(400.0, 100.0, 800.0)
    assert ok["allowed"] is True
    blocked = check_portfolio_gross_notional(750.0, 100.0, 800.0)
    assert blocked["allowed"] is False
    assert blocked["projected_gross"] == 850.0
    disabled = check_portfolio_gross_notional(10_000.0, 500.0, 0.0)
    assert disabled["allowed"] is True


def test_sector_exposure_counts_general_as_unassigned():
    portfolio = [
        {"ticker": "AAA", "size": 200.0, "sector": "General"},
        {"ticker": "BBB", "size": 200.0, "sector": "Energy"},
    ]
    # Proposed Unassigned trade would otherwise miss General holdings.
    check = check_projected_sector_exposure(
        portfolio,
        pair_sector="Unassigned",
        new_trade_size=200.0,
        sizing_base=1000.0,
        max_sector_exposure=0.30,
    )
    assert check["allowed"] is False
    assert check["sector"] == "Unassigned"
    assert check["projected_exposure"] == 0.4


def test_sector_exposure_empty_portfolio_uses_sizing_base():
    check = check_projected_sector_exposure(
        [],
        pair_sector="Technology",
        new_trade_size=100.0,
        sizing_base=1000.0,
        max_sector_exposure=0.30,
    )
    assert check["allowed"] is True
    assert check["projected_exposure"] == 0.1


def test_gross_notional_from_signals_sums_cost_basis():
    total = gross_notional_from_signals(
        [
            {"total_cost_basis": 100.0},
            {"total_cost_basis": "50.5"},
            {"total_cost_basis": None},
        ]
    )
    assert total == 150.5


def test_rotation_skips_candidates_sharing_active_ticker():
    actions = select_rotation_actions(
        active_pairs=[
            {"id": "NVDA_AMD", "is_cointegrated": True, "hedge_ratio": 1.0},
        ],
        candidates=[
            {
                "pair_id": "NVDA_INTC",
                "sortino": 9.0,
                "correlation": 0.95,
                "p_value": 0.01,
                "hedge_ratio": 1.0,
            },
            {
                "pair_id": "KO_PEP",
                "sortino": 3.0,
                "correlation": 0.9,
                "p_value": 0.01,
                "hedge_ratio": 1.0,
            },
        ],
        max_active_pairs=3,
        sortino_threshold=2.0,
        min_correlation=0.70,
        max_pvalue=0.05,
    )
    assert [c["pair_id"] for c in actions["to_promote"]] == ["KO_PEP"]


def test_rotation_skips_promote_batch_internal_shared_legs():
    actions = select_rotation_actions(
        active_pairs=[],
        candidates=[
            {
                "pair_id": "MSFT_AAPL",
                "sortino": 5.0,
                "correlation": 0.9,
                "p_value": 0.01,
                "hedge_ratio": 1.0,
            },
            {
                "pair_id": "MSFT_GOOGL",
                "sortino": 4.5,
                "correlation": 0.9,
                "p_value": 0.01,
                "hedge_ratio": 1.0,
            },
            {
                "pair_id": "KO_PEP",
                "sortino": 4.0,
                "correlation": 0.9,
                "p_value": 0.01,
                "hedge_ratio": 1.0,
            },
        ],
        max_active_pairs=3,
        sortino_threshold=2.0,
        min_correlation=0.70,
        max_pvalue=0.05,
    )
    assert [c["pair_id"] for c in actions["to_promote"]] == ["MSFT_AAPL", "KO_PEP"]
