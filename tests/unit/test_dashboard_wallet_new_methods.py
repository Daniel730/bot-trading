"""
Additional unit tests for dashboard_service changes introduced in this PR.

Covers:
- Backward-compat aliases (sync_t212_wallet_for_coint, calculate_t212_wallet_recommendations,
  buy_t212_wallet_recommendations delegate to their generic counterparts)
- _format_brokerage_ticker: returns raw ticker for ALPACA, T212 path with wallet_seed
- _build_weighted_wallet_plan: new score-proportional allocation algorithm
- _place_wallet_orders: new brokerage_service.place_value_order integration
- WalletSyncRequest / WalletRecommendationRequest / WalletRecommendationBuyRequest model aliases
- sync_wallet_for_coint raises 409 when monitor is None
- sync_wallet_for_coint raises 400 when brokerage test_connection() fails
- sync_wallet_for_coint raises 400 when no active tickers configured
- calculate_wallet_recommendations raises 400 when brokerage not connected
- buy_wallet_recommendations raises 400 for truly unknown tickers
"""
import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import HTTPException

from src.config import settings
from src.services.dashboard_service import (
    T212WalletRecommendationBuyRequest,
    T212WalletRecommendationRequest,
    T212WalletSyncRequest,
    WalletRecommendationBuyRequest,
    WalletRecommendationRequest,
    WalletSyncRequest,
    dashboard_service,
    dashboard_state,
)


# ---------------------------------------------------------------------------
# Shared fixture (mirrors wallet_context from test_dashboard_wallet_sync.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def wallet_context(monkeypatch):
    import src.services.dashboard_service as dashboard_module

    original_monitor = dashboard_state.monitor
    original_provider_name = dashboard_module.brokerage_service.provider_name
    original_budget = settings.T212_BUDGET_USD

    settings.T212_BUDGET_USD = 0.0
    dashboard_state.monitor = SimpleNamespace(
        active_pairs=[
            {"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT", "is_cointegrated": True},
            {"id": "KO_PEP", "ticker_a": "KO", "ticker_b": "PEP", "is_cointegrated": False},
            {"id": "BTC_ETH", "ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "is_cointegrated": True},
            {"id": "GOOG_GOOGL", "ticker_a": "GOOG", "ticker_b": "GOOGL", "is_cointegrated": True},
        ]
    )

    def build(provider_name: str):
        brokerage = dashboard_module.brokerage_service
        brokerage.provider_name = provider_name

        monkeypatch.setattr(brokerage, "test_connection", lambda: True)
        monkeypatch.setattr(
            brokerage,
            "get_venue",
            lambda ticker: "WEB3" if "-USD" in str(ticker).upper() else provider_name,
        )
        monkeypatch.setattr(brokerage, "get_account_cash", lambda: 100.0)
        monkeypatch.setattr(brokerage, "get_pending_orders_value", AsyncMock(return_value=0.0))
        monkeypatch.setattr(brokerage, "get_positions", lambda: [])
        monkeypatch.setattr(brokerage, "get_pending_orders", AsyncMock(return_value=[]))
        monkeypatch.setattr(dashboard_state, "add_message", AsyncMock())

        async def fake_place_value_order(ticker, amount, side, *args, **kwargs):
            return {"status": "success", "order_id": f"{provider_name.lower()}-{ticker}"}

        place_value_order = AsyncMock(side_effect=fake_place_value_order)
        monkeypatch.setattr(brokerage, "place_value_order", place_value_order)

        return SimpleNamespace(
            brokerage=brokerage,
            place_value_order=place_value_order,
        )

    yield build

    dashboard_state.monitor = original_monitor
    dashboard_module.brokerage_service.provider_name = original_provider_name
    settings.T212_BUDGET_USD = original_budget


# ---------------------------------------------------------------------------
# Model alias tests
# ---------------------------------------------------------------------------

class TestRequestModelAliases:
    def test_t212_wallet_sync_request_is_alias_for_wallet_sync_request(self):
        assert T212WalletSyncRequest is WalletSyncRequest

    def test_t212_wallet_recommendation_request_is_alias(self):
        assert T212WalletRecommendationRequest is WalletRecommendationRequest

    def test_t212_wallet_recommendation_buy_request_is_alias(self):
        assert T212WalletRecommendationBuyRequest is WalletRecommendationBuyRequest

    def test_wallet_sync_request_requires_positive_budget(self):
        with pytest.raises(Exception):
            WalletSyncRequest(budget=-1.0)

    def test_wallet_sync_request_default_delay(self):
        req = WalletSyncRequest(budget=50.0)
        assert req.delay_seconds == 0.5

    def test_wallet_recommendation_buy_request_inherits_fields(self):
        req = WalletRecommendationBuyRequest(budget=100.0, tickers=["AAPL", "MSFT"], delay_seconds=0)
        assert req.budget == 100.0
        assert req.tickers == ["AAPL", "MSFT"]
        assert req.delay_seconds == 0


# ---------------------------------------------------------------------------
# Backward-compat method aliases
# ---------------------------------------------------------------------------

class TestLegacyMethodAliases:
    @pytest.mark.asyncio
    async def test_sync_t212_wallet_for_coint_delegates(self, wallet_context):
        wallet_context("T212")
        result = await dashboard_service.sync_t212_wallet_for_coint(
            WalletSyncRequest(budget=20.0, delay_seconds=0)
        )
        assert result["status"] == "ok"
        assert result["mode"] == "T212"

    @pytest.mark.asyncio
    async def test_calculate_t212_wallet_recommendations_delegates(self, wallet_context, monkeypatch):
        wallet_context("T212")
        monkeypatch.setattr(
            dashboard_service,
            "_wallet_pair_z_scores",
            AsyncMock(return_value={}),
        )
        result = await dashboard_service.calculate_t212_wallet_recommendations(
            WalletRecommendationRequest(budget=40.0)
        )
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_buy_t212_wallet_recommendations_delegates(self, wallet_context, monkeypatch):
        ctx = wallet_context("T212")
        monkeypatch.setattr(
            dashboard_service,
            "_wallet_pair_z_scores",
            AsyncMock(return_value={"AAPL_MSFT": 2.4, "GOOG_GOOGL": 1.2}),
        )
        result = await dashboard_service.buy_t212_wallet_recommendations(
            WalletRecommendationBuyRequest(budget=20.0, tickers=["AAPL", "MSFT"], delay_seconds=0)
        )
        assert result["status"] == "ok"
        assert ctx.place_value_order.await_count == 2


# ---------------------------------------------------------------------------
# _format_brokerage_ticker
# ---------------------------------------------------------------------------

class TestFormatBrokerageTicker:
    def test_returns_raw_ticker_for_alpaca(self, monkeypatch):
        import src.services.dashboard_service as dm

        original = dm.brokerage_service.provider_name
        dm.brokerage_service.provider_name = "ALPACA"
        try:
            result = dm._format_brokerage_ticker("aapl")
        finally:
            dm.brokerage_service.provider_name = original

        assert result == "AAPL"

    def test_returns_raw_ticker_for_t212_when_wallet_seed_unavailable(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_provider = dm.brokerage_service.provider_name
        original_seed = dm.wallet_seed
        dm.brokerage_service.provider_name = "T212"
        dm.wallet_seed = None
        try:
            result = dm._format_brokerage_ticker("ko")
        finally:
            dm.brokerage_service.provider_name = original_provider
            dm.wallet_seed = original_seed

        assert result == "KO"

    def test_delegates_to_wallet_seed_for_t212(self, monkeypatch):
        import src.services.dashboard_service as dm

        fake_seed = MagicMock()
        fake_seed.format_t212_ticker.return_value = "KO_US_EQ"

        original_provider = dm.brokerage_service.provider_name
        original_seed = dm.wallet_seed
        dm.brokerage_service.provider_name = "T212"
        dm.wallet_seed = fake_seed
        try:
            result = dm._format_brokerage_ticker("ko")
        finally:
            dm.brokerage_service.provider_name = original_provider
            dm.wallet_seed = original_seed

        fake_seed.format_t212_ticker.assert_called_once_with("KO")
        assert result == "KO_US_EQ"

    def test_strips_and_uppercases_input(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_provider = dm.brokerage_service.provider_name
        original_seed = dm.wallet_seed
        dm.brokerage_service.provider_name = "ALPACA"
        dm.wallet_seed = None
        try:
            result = dm._format_brokerage_ticker("  msft  ")
        finally:
            dm.brokerage_service.provider_name = original_provider
            dm.wallet_seed = original_seed

        assert result == "MSFT"


# ---------------------------------------------------------------------------
# _build_weighted_wallet_plan  (new allocation algorithm)
# ---------------------------------------------------------------------------

class TestBuildWeightedWalletPlan:
    def test_equal_scores_split_budget_evenly(self):
        recs = [
            {"ticker": "AAPL", "score": 1.0},
            {"ticker": "MSFT", "score": 1.0},
            {"ticker": "GOOG", "score": 1.0},
            {"ticker": "GOOGL", "score": 1.0},
        ]
        plan = dashboard_service._build_weighted_wallet_plan(20.0, recs)
        tickers = [t for t, _ in plan]
        amounts = [float(a) for _, a in plan]

        assert tickers == ["AAPL", "MSFT", "GOOG", "GOOGL"]
        assert sum(amounts) == pytest.approx(20.0, abs=0.01)
        assert all(a == pytest.approx(5.0, abs=0.01) for a in amounts)

    def test_higher_score_gets_more_allocation(self):
        recs = [
            {"ticker": "HIGH", "score": 3.0},
            {"ticker": "LOW", "score": 1.0},
        ]
        plan = dashboard_service._build_weighted_wallet_plan(20.0, recs)
        amounts = {t: float(a) for t, a in plan}

        assert amounts["HIGH"] > amounts["LOW"]
        assert sum(amounts.values()) == pytest.approx(20.0, abs=0.01)

    def test_total_allocation_equals_budget(self):
        recs = [{"ticker": f"T{i}", "score": float(i + 1)} for i in range(7)]
        plan = dashboard_service._build_weighted_wallet_plan(33.33, recs)
        total = sum(float(a) for _, a in plan)
        assert total == pytest.approx(33.33, abs=0.01)

    def test_empty_recommendations_returns_empty_plan(self):
        plan = dashboard_service._build_weighted_wallet_plan(100.0, [])
        assert plan == []

    def test_raises_when_budget_too_small_for_tickers(self):
        recs = [{"ticker": "A", "score": 1.0}, {"ticker": "B", "score": 1.0}]
        with pytest.raises(ValueError, match="too small"):
            dashboard_service._build_weighted_wallet_plan(0.01, recs)

    def test_single_ticker_gets_full_budget(self):
        recs = [{"ticker": "AAPL", "score": 5.0}]
        plan = dashboard_service._build_weighted_wallet_plan(42.0, recs)
        assert len(plan) == 1
        ticker, amount = plan[0]
        assert ticker == "AAPL"
        assert float(amount) == pytest.approx(42.0, abs=0.01)

    def test_plan_assigns_ranks_to_recommendations(self):
        recs = [{"ticker": "A", "score": 1.0}, {"ticker": "B", "score": 1.0}]
        dashboard_service._build_weighted_wallet_plan(10.0, recs)
        # _build_weighted_wallet_plan mutates the recommendation dicts with rank/suggested_amount
        assert recs[0]["rank"] == 1
        assert recs[1]["rank"] == 2


# ---------------------------------------------------------------------------
# _place_wallet_orders  (new direct brokerage_service path)
# ---------------------------------------------------------------------------

class TestPlaceWalletOrders:
    @pytest.mark.asyncio
    async def test_successful_orders_have_ok_status(self, monkeypatch):
        import src.services.dashboard_service as dm

        async def fake_place(ticker, amount, side, *a, **kw):
            return {"status": "success", "order_id": f"id-{ticker}"}

        monkeypatch.setattr(dm.brokerage_service, "place_value_order", AsyncMock(side_effect=fake_place))

        plan = [("AAPL", Decimal("10.00")), ("MSFT", Decimal("10.00"))]
        orders, failures, skipped = await dashboard_service._place_wallet_orders(plan, delay_seconds=0)

        assert failures == 0
        assert skipped == []
        assert all(o["status"] == "ok" for o in orders)
        assert [o["ticker"] for o in orders] == ["AAPL", "MSFT"]

    @pytest.mark.asyncio
    async def test_error_status_from_provider_increments_failures(self, monkeypatch):
        import src.services.dashboard_service as dm

        async def fake_place(ticker, amount, side, *a, **kw):
            return {"status": "error", "message": "insufficient funds"}

        monkeypatch.setattr(dm.brokerage_service, "place_value_order", AsyncMock(side_effect=fake_place))

        plan = [("AAPL", Decimal("10.00"))]
        orders, failures, skipped = await dashboard_service._place_wallet_orders(plan, delay_seconds=0)

        assert failures == 1
        assert orders[0]["status"] == "error"
        assert orders[0]["message"] == "insufficient funds"

    @pytest.mark.asyncio
    async def test_exception_from_provider_increments_failures(self, monkeypatch):
        import src.services.dashboard_service as dm

        async def exploding_place(ticker, amount, side, *a, **kw):
            raise RuntimeError("network error")

        monkeypatch.setattr(dm.brokerage_service, "place_value_order", AsyncMock(side_effect=exploding_place))

        plan = [("GOOG", Decimal("15.00"))]
        orders, failures, skipped = await dashboard_service._place_wallet_orders(plan, delay_seconds=0)

        assert failures == 1
        assert orders[0]["status"] == "error"
        assert "network error" in orders[0]["message"]

    @pytest.mark.asyncio
    async def test_order_id_extracted_from_result(self, monkeypatch):
        import src.services.dashboard_service as dm

        async def fake_place(ticker, amount, side, *a, **kw):
            return {"status": "success", "order_id": "abc-123"}

        monkeypatch.setattr(dm.brokerage_service, "place_value_order", AsyncMock(side_effect=fake_place))

        plan = [("KO", Decimal("5.00"))]
        orders, _, _ = await dashboard_service._place_wallet_orders(plan, delay_seconds=0)

        assert orders[0]["order_id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_partial_failure_mixed_statuses(self, monkeypatch):
        import src.services.dashboard_service as dm

        call_count = 0

        async def sometimes_fail(ticker, amount, side, *a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                return {"status": "error", "message": "rejected"}
            return {"status": "ok", "order_id": f"ok-{ticker}"}

        monkeypatch.setattr(dm.brokerage_service, "place_value_order", AsyncMock(side_effect=sometimes_fail))

        plan = [("A", Decimal("5.00")), ("B", Decimal("5.00")), ("C", Decimal("5.00"))]
        orders, failures, _ = await dashboard_service._place_wallet_orders(plan, delay_seconds=0)

        assert failures == 1
        assert len(orders) == 3


# ---------------------------------------------------------------------------
# sync_wallet_for_coint – error guard cases
# ---------------------------------------------------------------------------

class TestSyncWalletForCointGuards:
    @pytest.mark.asyncio
    async def test_raises_409_when_monitor_not_attached(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_monitor = dashboard_state.monitor
        original_name = dm.brokerage_service.provider_name
        dm.brokerage_service.provider_name = "T212"
        dashboard_state.monitor = None
        monkeypatch.setattr(dm.brokerage_service, "test_connection", lambda: True)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await dashboard_service.sync_wallet_for_coint(WalletSyncRequest(budget=10.0))
            assert exc_info.value.status_code == 409
        finally:
            dashboard_state.monitor = original_monitor
            dm.brokerage_service.provider_name = original_name

    @pytest.mark.asyncio
    async def test_raises_400_when_brokerage_not_connected(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_monitor = dashboard_state.monitor
        original_name = dm.brokerage_service.provider_name
        dm.brokerage_service.provider_name = "T212"
        dashboard_state.monitor = SimpleNamespace(active_pairs=[])
        monkeypatch.setattr(dm.brokerage_service, "test_connection", lambda: False)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await dashboard_service.sync_wallet_for_coint(WalletSyncRequest(budget=10.0))
            assert exc_info.value.status_code == 400
            assert "not configured or reachable" in exc_info.value.detail
        finally:
            dashboard_state.monitor = original_monitor
            dm.brokerage_service.provider_name = original_name

    @pytest.mark.asyncio
    async def test_raises_400_when_no_active_tickers(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_monitor = dashboard_state.monitor
        original_name = dm.brokerage_service.provider_name
        dm.brokerage_service.provider_name = "T212"
        # Only crypto pairs — no equity tickers for T212
        dashboard_state.monitor = SimpleNamespace(
            active_pairs=[
                {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "is_cointegrated": True}
            ]
        )
        monkeypatch.setattr(dm.brokerage_service, "test_connection", lambda: True)
        monkeypatch.setattr(dm.brokerage_service, "get_venue", lambda t: "WEB3")
        try:
            with pytest.raises(HTTPException) as exc_info:
                await dashboard_service.sync_wallet_for_coint(WalletSyncRequest(budget=10.0))
            assert exc_info.value.status_code == 400
            assert "No active equity tickers" in exc_info.value.detail
        finally:
            dashboard_state.monitor = original_monitor
            dm.brokerage_service.provider_name = original_name


# ---------------------------------------------------------------------------
# calculate_wallet_recommendations – error guard cases
# ---------------------------------------------------------------------------

class TestCalculateWalletRecommendationsGuards:
    @pytest.mark.asyncio
    async def test_raises_400_when_brokerage_not_connected(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_name = dm.brokerage_service.provider_name
        original_monitor = dashboard_state.monitor
        dm.brokerage_service.provider_name = "ALPACA"
        dashboard_state.monitor = SimpleNamespace(active_pairs=[])
        monkeypatch.setattr(dm.brokerage_service, "test_connection", lambda: False)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await dashboard_service.calculate_wallet_recommendations(
                    WalletRecommendationRequest(budget=100.0)
                )
            assert exc_info.value.status_code == 400
            assert "ALPACA" in exc_info.value.detail
        finally:
            dm.brokerage_service.provider_name = original_name
            dashboard_state.monitor = original_monitor


# ---------------------------------------------------------------------------
# buy_wallet_recommendations – truly unknown ticker raises 400
# ---------------------------------------------------------------------------

class TestBuyWalletRecommendationsTrulyUnknown:
    @pytest.mark.asyncio
    async def test_raises_400_for_ticker_not_in_any_active_pair(self, wallet_context, monkeypatch):
        wallet_context("T212")
        monkeypatch.setattr(
            dashboard_service,
            "_wallet_pair_z_scores",
            AsyncMock(return_value={"AAPL_MSFT": 2.4}),
        )

        with pytest.raises(HTTPException) as exc_info:
            await dashboard_service.buy_wallet_recommendations(
                WalletRecommendationBuyRequest(
                    budget=10.0,
                    tickers=["TOTALLY_UNKNOWN_XYZ"],
                    delay_seconds=0,
                )
            )

        assert exc_info.value.status_code == 400
        assert "TOTALLY_UNKNOWN_XYZ" in exc_info.value.detail


# ---------------------------------------------------------------------------
# mode field reflects active provider in responses
# ---------------------------------------------------------------------------

class TestModeFieldInResponses:
    @pytest.mark.asyncio
    async def test_sync_wallet_mode_is_provider_name(self, wallet_context):
        wallet_context("ALPACA")
        result = await dashboard_service.sync_wallet_for_coint(
            WalletSyncRequest(budget=20.0, delay_seconds=0)
        )
        assert result["mode"] == "ALPACA"

    @pytest.mark.asyncio
    async def test_recommendations_mode_is_provider_name(self, wallet_context, monkeypatch):
        wallet_context("ALPACA")
        monkeypatch.setattr(
            dashboard_service,
            "_wallet_pair_z_scores",
            AsyncMock(return_value={"AAPL_MSFT": 2.4}),
        )
        result = await dashboard_service.calculate_wallet_recommendations(
            WalletRecommendationRequest(budget=40.0)
        )
        assert result["mode"] == "ALPACA"

    @pytest.mark.asyncio
    async def test_buy_recommendations_mode_is_provider_name(self, wallet_context, monkeypatch):
        wallet_context("ALPACA")
        monkeypatch.setattr(
            dashboard_service,
            "_wallet_pair_z_scores",
            AsyncMock(return_value={"AAPL_MSFT": 2.4}),
        )
        result = await dashboard_service.buy_wallet_recommendations(
            WalletRecommendationBuyRequest(
                budget=20.0, tickers=["AAPL", "MSFT"], delay_seconds=0
            )
        )
        assert result["mode"] == "ALPACA"


# ---------------------------------------------------------------------------
# _get_active_tickers – crypto pairs excluded, coint count accurate
# ---------------------------------------------------------------------------

class TestGetActiveTickers:
    def _setup_monitor(self, pairs):
        dashboard_state.monitor = SimpleNamespace(active_pairs=pairs)

    def teardown_method(self):
        dashboard_state.monitor = None

    def test_crypto_pairs_excluded(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_name = dm.brokerage_service.provider_name
        dm.brokerage_service.provider_name = "T212"
        monkeypatch.setattr(
            dm.brokerage_service,
            "get_venue",
            lambda t: "WEB3" if "-USD" in t else "T212",
        )
        self._setup_monitor([
            {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "is_cointegrated": True},
            {"ticker_a": "AAPL", "ticker_b": "MSFT", "is_cointegrated": True},
        ])
        try:
            coint_pairs, tickers = dashboard_service._get_active_tickers()
        finally:
            dm.brokerage_service.provider_name = original_name

        assert "BTC-USD" not in tickers
        assert "ETH-USD" not in tickers
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert coint_pairs == 1

    def test_coint_count_only_counts_cointegrated_equity_pairs(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_name = dm.brokerage_service.provider_name
        dm.brokerage_service.provider_name = "T212"
        monkeypatch.setattr(dm.brokerage_service, "get_venue", lambda t: "T212")
        self._setup_monitor([
            {"ticker_a": "AAPL", "ticker_b": "MSFT", "is_cointegrated": True},
            {"ticker_a": "KO", "ticker_b": "PEP", "is_cointegrated": False},
            {"ticker_a": "GOOG", "ticker_b": "GOOGL", "is_cointegrated": True},
        ])
        try:
            coint_pairs, tickers = dashboard_service._get_active_tickers()
        finally:
            dm.brokerage_service.provider_name = original_name

        assert coint_pairs == 2
        assert set(tickers) == {"AAPL", "MSFT", "KO", "PEP", "GOOG", "GOOGL"}

    def test_raises_409_when_monitor_is_none(self, monkeypatch):
        import src.services.dashboard_service as dm

        original_monitor = dashboard_state.monitor
        original_name = dm.brokerage_service.provider_name
        dashboard_state.monitor = None
        dm.brokerage_service.provider_name = "T212"
        try:
            with pytest.raises(HTTPException) as exc_info:
                dashboard_service._get_active_tickers()
            assert exc_info.value.status_code == 409
        finally:
            dashboard_state.monitor = original_monitor
            dm.brokerage_service.provider_name = original_name
