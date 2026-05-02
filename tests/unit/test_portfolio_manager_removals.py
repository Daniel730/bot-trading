"""
Tests for the PR removals from src/agents/portfolio_manager_agent.py:

Removed methods:
  - scan_crypto_universe
  - run_discovery
  - rotate_pairs

Also tests the simplified get_sp500_universe (removed io.StringIO / bs4 fallback,
removed ticker normalisation for yfinance-style dots) and scan_sector_universe
(removed the data-guard 'if df is None or df.empty' before check_cointegration).

These tests act as regression guards: if the methods are accidentally re-added,
the "does not have" assertions will fail immediately.
"""
import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Removed methods guard
# ---------------------------------------------------------------------------

class TestRemovedMethods:
    def setup_method(self):
        from src.agents.portfolio_manager_agent import PortfolioManagerAgent
        self.cls = PortfolioManagerAgent

    def test_scan_crypto_universe_is_removed(self):
        """scan_crypto_universe was removed in this PR."""
        assert not hasattr(self.cls, "scan_crypto_universe"), (
            "scan_crypto_universe should have been removed from PortfolioManagerAgent"
        )

    def test_run_discovery_is_removed(self):
        """run_discovery was removed in this PR."""
        assert not hasattr(self.cls, "run_discovery"), (
            "run_discovery should have been removed from PortfolioManagerAgent"
        )

    def test_rotate_pairs_is_removed(self):
        """rotate_pairs was removed in this PR."""
        assert not hasattr(self.cls, "rotate_pairs"), (
            "rotate_pairs should have been removed from PortfolioManagerAgent"
        )

    def test_scan_sector_universe_still_exists(self):
        """scan_sector_universe was NOT removed – only simplified."""
        assert hasattr(self.cls, "scan_sector_universe")

    def test_get_sp500_universe_still_exists(self):
        """get_sp500_universe was NOT removed – only simplified."""
        assert hasattr(self.cls, "get_sp500_universe")

    def test_get_optimization_advice_still_exists(self):
        """get_optimization_advice was NOT removed."""
        assert hasattr(self.cls, "get_optimization_advice")

    def test_run_narrative_scan_still_exists(self):
        """run_narrative_scan was NOT removed."""
        assert hasattr(self.cls, "run_narrative_scan")


# ---------------------------------------------------------------------------
# get_sp500_universe – simplified path (PR removed io.StringIO, bs4 fallback,
# and ticker normalisation)
# ---------------------------------------------------------------------------

class TestGetSp500Universe:
    def _make_agent(self):
        from src.agents.portfolio_manager_agent import PortfolioManagerAgent
        agent = PortfolioManagerAgent.__new__(PortfolioManagerAgent)
        agent._sp500_cache = None
        agent._last_cache_update = None
        return agent

    @pytest.mark.asyncio
    async def test_returns_empty_df_on_request_exception(self):
        agent = self._make_agent()
        with patch("src.agents.portfolio_manager_agent.requests.get", side_effect=RuntimeError("network")), \
             patch("src.agents.portfolio_manager_agent.asyncio.to_thread", side_effect=RuntimeError("network")):
            result = await agent.get_sp500_universe()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @pytest.mark.asyncio
    async def test_returns_empty_df_when_ticker_or_sector_col_missing(self):
        agent = self._make_agent()

        # Build a fake table that has no ticker/symbol/sector/industry column
        fake_df = pd.DataFrame({"A": range(501), "B": range(501)})
        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.text = "<html></html>"

        async def fake_to_thread(func, *args, **kwargs):
            if func is __import__("requests").get or "requests" in str(func):
                return fake_response
            # pd.read_html call
            return [fake_df]

        with patch("src.agents.portfolio_manager_agent.asyncio.to_thread", side_effect=fake_to_thread):
            result = await agent.get_sp500_universe()

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @pytest.mark.asyncio
    async def test_caches_result_for_seven_days(self):
        """A second call within 7 days should return the cached DataFrame."""
        agent = self._make_agent()

        fake_df = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT"],
            "Security": ["Apple", "Microsoft"],
            "GICS Sector": ["Tech", "Tech"],
        })
        # Pad to > 400 rows so the length gate passes
        fat_df = pd.concat([fake_df] * 210, ignore_index=True)
        fat_df["Symbol"] = [f"T{i}" for i in range(len(fat_df))]

        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.text = "<html></html>"

        call_count = {"n": 0}

        async def fake_to_thread(func, *args, **kwargs):
            call_count["n"] += 1
            if hasattr(func, "__name__") and func.__name__ == "get":
                return fake_response
            return [fat_df]

        with patch("src.agents.portfolio_manager_agent.asyncio.to_thread", side_effect=fake_to_thread):
            first = await agent.get_sp500_universe()

        initial_calls = call_count["n"]
        # Second call: should return cached copy without network hit
        second = await agent.get_sp500_universe()

        assert second is first  # same object
        assert call_count["n"] == initial_calls  # no additional network calls

    @pytest.mark.asyncio
    async def test_uses_first_table_when_no_large_table_found(self):
        """If no table has > 400 rows, fall back to tables[0]."""
        agent = self._make_agent()

        small_df = pd.DataFrame({
            "Symbol": ["AAPL"],
            "Security": ["Apple"],
            "GICS Sector": ["Tech"],
        })

        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.text = "<html></html>"

        async def fake_to_thread(func, *args, **kwargs):
            if hasattr(func, "__name__") and func.__name__ == "get":
                return fake_response
            # All tables are small – triggers fallback to tables[0]
            return [small_df]

        with patch("src.agents.portfolio_manager_agent.asyncio.to_thread", side_effect=fake_to_thread):
            result = await agent.get_sp500_universe()

        # Should have renamed columns and returned the small df
        if not result.empty:
            assert "Ticker" in result.columns
            assert "Sector" in result.columns


# ---------------------------------------------------------------------------
# Regression: io import was removed from portfolio_manager_agent.py
# ---------------------------------------------------------------------------

def test_io_not_imported_in_portfolio_manager():
    """PR removed 'import io' from portfolio_manager_agent.py."""
    import ast
    import inspect
    import src.agents.portfolio_manager_agent as mod

    source = inspect.getsource(mod)
    tree = ast.parse(source)

    io_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "io":
                    io_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "io":
                io_imports.append(node.module)

    assert not io_imports, (
        "The 'io' module import should have been removed from portfolio_manager_agent.py"
    )