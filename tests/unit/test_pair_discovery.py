"""Unit tests for automatic pair discovery helpers and rotation policy."""
from __future__ import annotations

import sys
from types import ModuleType

import pytest

from src.services.pair_discovery_helpers import (
    candidate_pair_combos,
    is_hedge_ratio_sane,
    is_pair_denied,
    normalize_denylist,
    pairs_from_promotions,
    parse_denylist_env,
    parse_pair_id,
    select_rotation_actions,
)


def test_parse_pair_id_equity_and_crypto():
    assert parse_pair_id("KO_PEP") == ("KO", "PEP")
    assert parse_pair_id("BRK-B_JPM") == ("BRK-B", "JPM")
    assert parse_pair_id("BTC-USD_ETH-USD") == ("BTC-USD", "ETH-USD")
    assert parse_pair_id("ADA-USD_AVAX-USD") == ("ADA-USD", "AVAX-USD")


def test_parse_pair_id_rejects_invalid():
    with pytest.raises(ValueError):
        parse_pair_id("")
    with pytest.raises(ValueError):
        parse_pair_id("ONLYONE")


def test_candidate_pair_combos_is_bounded_and_deduped():
    combos = candidate_pair_combos(
        ["AAPL", "msft", "AAPL", "NVDA", "AMD", "INTC"],
        max_tickers=4,
    )
    assert len(combos) == 6  # C(4, 2)
    assert ("AAPL", "MSFT") in combos
    assert ("NVDA", "AMD") in combos
    assert len({frozenset(pair) for pair in combos}) == 6


def test_btc_bch_denylist_both_orders():
    denied = normalize_denylist(["BTC-USD_BCH-USD"])
    assert is_pair_denied(pair_id="BTC-USD_BCH-USD", denylist=denied)
    assert is_pair_denied(pair_id="BCH-USD_BTC-USD", denylist=denied)
    assert is_pair_denied(ticker_a="bch-usd", ticker_b="btc-usd", denylist=denied)
    assert not is_pair_denied(pair_id="BTC-USD_ETH-USD", denylist=denied)


def test_parse_denylist_env_accepts_comma_semicolon_and_whitespace():
    assert parse_denylist_env("BTC-USD_BCH-USD, BCH-USD_BTC-USD") == [
        "BTC-USD_BCH-USD",
        "BCH-USD_BTC-USD",
    ]
    assert parse_denylist_env("KO_PEP; MA_V\nXOM_CVX") == ["KO_PEP", "MA_V", "XOM_CVX"]
    assert parse_denylist_env("") == []
    assert parse_denylist_env(None) == []


def test_select_rotation_actions_promotes_into_fully_empty_active():
    """Empty Active must fill from scouts (bootstrap / post-quarantine)."""
    actions = select_rotation_actions(
        active_pairs=[],
        candidates=[
            {"pair_id": "SOL-USD_AVAX-USD", "sortino": 2.1, "hedge_ratio": 1.1},
            {"pair_id": "BTC-USD_BCH-USD", "sortino": 99.0, "hedge_ratio": 280.0},
            {"pair_id": "KO_PEP", "sortino": 1.8, "hedge_ratio": 0.9},
        ],
        max_active_pairs=2,
        denylist=["BTC-USD_BCH-USD"],
        max_abs_hedge=25.0,
    )
    assert actions["to_bench"] == []
    assert [c["pair_id"] for c in actions["to_promote"]] == [
        "SOL-USD_AVAX-USD",
        "KO_PEP",
    ]


def test_hedge_ratio_sanity_rejects_btc_bch_scale_beta():
    assert is_hedge_ratio_sane(1.2, max_abs_hedge=25.0)
    assert is_hedge_ratio_sane(-8.0, max_abs_hedge=25.0)
    assert not is_hedge_ratio_sane(285.0, max_abs_hedge=25.0)
    assert not is_hedge_ratio_sane(0.0, max_abs_hedge=25.0)
    assert not is_hedge_ratio_sane(float("nan"), max_abs_hedge=25.0)


def test_select_rotation_actions_fills_empty_slots():
    actions = select_rotation_actions(
        active_pairs=[],
        candidates=[
            {"pair_id": "KO_PEP", "sortino": 3.0},
            {"pair_id": "MA_V", "sortino": 2.5},
            {"pair_id": "XOM_CVX", "sortino": 2.0},
        ],
        max_active_pairs=2,
    )
    assert actions["to_bench"] == []
    assert [c["pair_id"] for c in actions["to_promote"]] == ["KO_PEP", "MA_V"]


def test_select_rotation_actions_enforces_sortino_and_correlation():
    actions = select_rotation_actions(
        active_pairs=[],
        candidates=[
            {"pair_id": "WEAK_SORT", "sortino": 0.5, "correlation": 0.95, "p_value": 0.01},
            {"pair_id": "WEAK_CORR", "sortino": 3.0, "correlation": 0.40, "p_value": 0.01},
            {"pair_id": "WEAK_P", "sortino": 3.0, "correlation": 0.95, "p_value": 0.20},
            {"pair_id": "GOOD_PAIR", "sortino": 3.0, "correlation": 0.92, "p_value": 0.02, "hedge_ratio": 1.1},
        ],
        max_active_pairs=3,
        sortino_threshold=2.0,
        min_correlation=0.70,
        max_pvalue=0.05,
    )
    assert [c["pair_id"] for c in actions["to_promote"]] == ["GOOD_PAIR"]


def test_select_rotation_actions_benches_insane_active_hedge():
    actions = select_rotation_actions(
        active_pairs=[
            {"id": "BTC-USD_BCH-USD", "is_cointegrated": True, "hedge_ratio": 285.0},
            {"id": "KO_PEP", "is_cointegrated": True, "hedge_ratio": 1.2},
        ],
        candidates=[
            {"pair_id": "MA_V", "sortino": 3.0, "correlation": 0.9, "p_value": 0.01, "hedge_ratio": 1.0},
        ],
        max_active_pairs=2,
        sortino_threshold=2.0,
        min_correlation=0.70,
        max_pvalue=0.05,
        max_abs_hedge=25.0,
    )
    assert actions["to_bench"] == ["BTC-USD_BCH-USD"]
    assert [c["pair_id"] for c in actions["to_promote"]] == ["MA_V"]


def test_select_rotation_actions_replaces_non_cointegrated():
    actions = select_rotation_actions(
        active_pairs=[
            {"id": "DEAD_PAIR", "is_cointegrated": False},
            {"id": "KO_PEP", "is_cointegrated": True},
        ],
        candidates=[
            {"pair_id": "MA_V", "sortino": 4.0},
            {"pair_id": "GS_MS", "sortino": 3.0},
        ],
        max_active_pairs=2,
    )
    assert actions["to_bench"] == ["DEAD_PAIR"]
    assert [c["pair_id"] for c in actions["to_promote"]] == ["MA_V"]


def test_select_rotation_actions_benches_denylisted_and_skips_promote():
    actions = select_rotation_actions(
        active_pairs=[
            {"id": "BTC-USD_BCH-USD", "is_cointegrated": True},
            {"id": "KO_PEP", "is_cointegrated": True},
        ],
        candidates=[
            {"pair_id": "BCH-USD_BTC-USD", "sortino": 99.0},
            {"pair_id": "MA_V", "sortino": 3.0},
        ],
        max_active_pairs=2,
        denylist=["BTC-USD_BCH-USD"],
    )
    assert actions["to_bench"] == ["BTC-USD_BCH-USD"]
    assert [c["pair_id"] for c in actions["to_promote"]] == ["MA_V"]


def test_select_rotation_actions_skips_already_active_candidates():
    actions = select_rotation_actions(
        active_pairs=[{"id": "KO_PEP", "is_cointegrated": True}],
        candidates=[{"pair_id": "KO_PEP", "sortino": 9.0}, {"pair_id": "MA_V", "sortino": 2.0}],
        max_active_pairs=2,
    )
    assert actions["to_bench"] == []
    assert [c["pair_id"] for c in actions["to_promote"]] == ["MA_V"]


def test_pairs_from_promotions_builds_trading_pair_payloads():
    payloads = pairs_from_promotions(
        [{"pair_id": "BTC-USD_ETH-USD", "sortino": 1.2, "hedge_ratio": 14.5}]
    )
    assert payloads == [
        {
            "id": "BTC-USD_ETH-USD",
            "ticker_a": "BTC-USD",
            "ticker_b": "ETH-USD",
            "hedge_ratio": 14.5,
            "is_cointegrated": True,
            "status": "Active",
        }
    ]


def _stub_optional_deps() -> None:
    """Allow importing PortfolioManagerAgent without a fully populated venv."""
    # Drop incomplete stubs from earlier failed imports so a real install wins.
    for name in list(sys.modules):
        if name == "statsmodels" or name.startswith("statsmodels."):
            mod = sys.modules.get(name)
            if mod is not None and not getattr(mod, "__file__", None):
                del sys.modules[name]

    try:
        import statsmodels.api  # noqa: F401
    except Exception:
        statsmodels = ModuleType("statsmodels")
        statsmodels.__path__ = []  # mark as package
        api = ModuleType("statsmodels.api")
        api.add_constant = lambda x: x
        tsa = ModuleType("statsmodels.tsa")
        tsa.__path__ = []
        stattools = ModuleType("statsmodels.tsa.stattools")
        stattools.adfuller = lambda *a, **k: (0, 1.0, 0, 0, {}, 0)
        sys.modules["statsmodels"] = statsmodels
        sys.modules["statsmodels.api"] = api
        sys.modules["statsmodels.tsa"] = tsa
        sys.modules["statsmodels.tsa.stattools"] = stattools

    stubs = {
        "tenacity": {
            "retry": lambda *a, **k: (lambda f: f),
            "wait_exponential": lambda **k: None,
            "stop_after_attempt": lambda *a, **k: None,
            "retry_if_exception_type": lambda *a, **k: None,
        },
    }
    for name, attrs in stubs.items():
        try:
            __import__(name)
            continue
        except Exception:
            pass
        if name in sys.modules:
            continue
        mod = ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod


@pytest.fixture
def portfolio_manager_agent(monkeypatch):
    _stub_optional_deps()
    from src.agents.portfolio_manager_agent import PortfolioManagerAgent

    return PortfolioManagerAgent(db=object())


@pytest.mark.asyncio
async def test_rotate_pairs_promotes_and_benches(portfolio_manager_agent, monkeypatch):
    agent = portfolio_manager_agent
    saved: list[list[dict]] = []
    benched: list[str] = []

    async def fake_active():
        return [
            {"id": "DEAD_A_DEAD_B", "is_cointegrated": False},
            {"id": "KO_PEP", "is_cointegrated": True},
        ]

    async def fake_candidates(limit: int = 20):
        assert limit >= 2
        return [
            {"pair_id": "MA_V", "sortino": 3.5},
            {"pair_id": "GS_MS", "sortino": 3.0},
        ]

    async def fake_update(pair_id: str, status: str):
        assert status == "Benched"
        benched.append(pair_id)

    async def fake_save(pairs: list[dict]):
        saved.append(pairs)

    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.get_active_trading_pairs",
        fake_active,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.get_top_candidates",
        fake_candidates,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.update_pair_status",
        fake_update,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.save_trading_pairs",
        fake_save,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.MAX_ACTIVE_PAIRS",
        2,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.ELITE_ROTATION_SORTINO_THRESHOLD",
        0.0,
    )

    result = await agent.rotate_pairs()
    assert result["status"] == "rotated"
    assert result["benched"] == ["DEAD_A_DEAD_B"]
    assert result["promoted"] == ["MA_V"]
    assert saved and saved[0][0]["ticker_a"] == "MA"
    assert saved[0][0]["ticker_b"] == "V"


@pytest.mark.asyncio
async def test_rotate_pairs_bootstraps_from_empty_active(portfolio_manager_agent, monkeypatch):
    agent = portfolio_manager_agent
    saved: list[list[dict]] = []

    async def fake_active():
        return []

    async def fake_candidates(limit: int = 20):
        return [
            {"pair_id": "BTC-USD_ETH-USD", "sortino": 2.2},
            {"pair_id": "SOL-USD_AVAX-USD", "sortino": 1.8},
        ]

    async def fake_save(pairs: list[dict]):
        saved.append(pairs)

    async def should_not_bench(*_a, **_k):
        raise AssertionError("should not bench")

    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.get_active_trading_pairs",
        fake_active,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.get_top_candidates",
        fake_candidates,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.update_pair_status",
        should_not_bench,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.save_trading_pairs",
        fake_save,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.MAX_ACTIVE_PAIRS",
        2,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.ELITE_ROTATION_SORTINO_THRESHOLD",
        0.0,
    )

    result = await agent.rotate_pairs()
    assert result["status"] == "rotated"
    assert result["benched"] == []
    assert result["promoted"] == ["BTC-USD_ETH-USD", "SOL-USD_AVAX-USD"]
    assert saved[0][0]["ticker_a"] == "BTC-USD"
    assert saved[0][1]["ticker_b"] == "AVAX-USD"


@pytest.mark.asyncio
async def test_rotate_pairs_never_promotes_btc_bch(portfolio_manager_agent, monkeypatch):
    agent = portfolio_manager_agent
    saved: list[list[dict]] = []

    async def fake_active():
        return [{"id": "BTC-USD_BCH-USD", "is_cointegrated": True}]

    async def fake_candidates(limit: int = 20):
        return [
            {"pair_id": "BTC-USD_BCH-USD", "sortino": 50.0},
            {"pair_id": "MA_V", "sortino": 2.0},
        ]

    async def fake_update(pair_id: str, status: str):
        assert pair_id == "BTC-USD_BCH-USD"
        assert status == "Benched"

    async def fake_save(pairs: list[dict]):
        saved.append(pairs)

    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.get_active_trading_pairs",
        fake_active,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.get_top_candidates",
        fake_candidates,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.update_pair_status",
        fake_update,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.save_trading_pairs",
        fake_save,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.MAX_ACTIVE_PAIRS",
        2,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.PAIR_DENYLIST",
        "BTC-USD_BCH-USD,BCH-USD_BTC-USD",
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.ELITE_ROTATION_SORTINO_THRESHOLD",
        0.0,
    )

    result = await agent.rotate_pairs()
    assert result["status"] == "rotated"
    assert result["benched"] == ["BTC-USD_BCH-USD"]
    assert result["promoted"] == ["MA_V"]
    assert all(p["id"] != "BTC-USD_BCH-USD" for batch in saved for p in batch)


@pytest.mark.asyncio
async def test_scan_sector_persists_cointegrated_combo(portfolio_manager_agent, monkeypatch):
    agent = portfolio_manager_agent
    saved = []

    class DummyDF:
        empty = False
        columns = ["AAPL", "MSFT", "NVDA"]

        def __getitem__(self, key):
            import numpy as np
            import pandas as pd

            if isinstance(key, list):
                data = {k: np.linspace(100, 110, 80) + (i * 0.1) for i, k in enumerate(key)}
                return pd.DataFrame(data)
            return self

        def dropna(self):
            return self

    async def fake_universe():
        import pandas as pd

        return pd.DataFrame(
            {
                "Ticker": ["AAPL", "MSFT", "NVDA"],
                "Company": ["A", "M", "N"],
                "Sector": ["Information Technology"] * 3,
            }
        )

    async def fake_hist(tickers, *_a, **_k):
        return DummyDF()

    async def always_admit(*_a, **_k):
        from src.services.pair_eligibility_service import EligibilityResult

        return EligibilityResult(True, "admitted", 0.001)

    async def fake_existing(*_a, **_k):
        return []

    async def fake_save(candidates):
        saved.append(candidates)

    monkeypatch.setattr(agent, "get_sp500_universe", fake_universe)
    monkeypatch.setattr(agent.data_service, "get_historical_data_async", fake_hist)
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.evaluate_pair",
        always_admit,
    )
    monkeypatch.setattr(
        agent.arbitrage_service,
        "check_cointegration",
        lambda *_a, **_k: (True, 0.01, 1.0),
    )
    monkeypatch.setattr(
        agent,
        "calculate_sortino_ratio",
        lambda *_a, **_k: 2.5,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.get_existing_candidate_ids",
        fake_existing,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.persistence_service.save_universe_candidates",
        fake_save,
    )
    monkeypatch.setattr(
        "src.agents.portfolio_manager_agent.settings.PAIR_DISCOVERY_MAX_TICKERS",
        3,
    )

    await agent.scan_sector_universe("Information Technology")
    assert len(saved) == 1
    assert len(saved[0]) == 3  # C(3,2)
    assert {c.pair_id for c in saved[0]} == {"AAPL_MSFT", "AAPL_NVDA", "MSFT_NVDA"}
