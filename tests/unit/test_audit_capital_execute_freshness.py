"""Part B failure-oriented regressions: managed sizing + execute freshness."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid

import pytest

from src.config import settings


@pytest.mark.asyncio
async def test_unmanaged_mv_excluded_from_sizing_base(monitor, monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "IGNORE_UNMANAGED_POSITIONS", True)
    monitor.brokerage.get_account_equity.return_value = 50_000.0
    monitor.brokerage.get_positions = AsyncMock(
        return_value=[
            {
                "ticker": "NVDA",
                "symbol": "NVDA",
                "quantity": 10.0,
                "quantityAvailableForTrading": 10.0,
                "marketValue": 40_000.0,
            }
        ]
    )

    base = await monitor._get_sizing_base()
    assert base == pytest.approx(10_000.0)


@pytest.mark.asyncio
async def test_execute_trade_sizing_base_subtracts_unmanaged_mv(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=10_000.0), \
         patch(
             "src.services.budget_service.budget_service.get_venue_budget_info",
             return_value={"total": 10_000.0, "used": 0.0, "remaining": 10_000.0},
         ), \
         patch(
             "src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors",
             new_callable=AsyncMock,
             return_value=[],
         ), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", True):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": False,
            "rejection_reason": "forced",
            "final_amount": 0.0,
            "kelly_fraction": 0.0,
            "max_allowed_fiat": 0.0,
        }
        monitor.brokerage.get_account_cash.return_value = 10_000.0
        monitor.brokerage.get_account_equity.return_value = 50_000.0
        monitor.brokerage.get_account_buying_power.return_value = 10_000.0
        monitor.brokerage.get_positions = AsyncMock(
            return_value=[
                {
                    "ticker": "NVDA",
                    "symbol": "NVDA",
                    "quantity": 10.0,
                    "quantityAvailableForTrading": 10.0,
                    "marketValue": 40_000.0,
                }
            ]
        )
        monitor.brokerage.place_value_order = AsyncMock()

        result = await monitor.execute_trade(pair, "Short-Long", 999.0, 999.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "risk_rejected"
        assert mock_validate_trade.call_args.kwargs["total_portfolio_cash"] == pytest.approx(
            10_000.0
        )
        monitor.brokerage.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_sizes_from_bid_ask_mid_not_stale_scan_prices(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())
    captured = {}

    def _validate_trade(**kwargs):
        return {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }

    def _fake_build_pair_legs(**kwargs):
        captured["price_a"] = kwargs["price_a"]
        captured["price_b"] = kwargs["price_b"]
        raise AssertionError("stop_after_legs")

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.risk_service.risk_service.validate_trade", side_effect=_validate_trade), \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch(
             "src.services.budget_service.budget_service.get_venue_budget_info",
             return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0},
         ), \
         patch(
             "src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors",
             new_callable=AsyncMock,
             return_value=[],
         ), \
         patch(
             "src.services.market_regime_service.market_regime_service.classify_current_regime",
             new_callable=AsyncMock,
             return_value={"regime": "Normal", "confidence": 0.9, "features": {}},
         ), \
         patch("src.monitor.build_pair_legs", side_effect=_fake_build_pair_legs), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", False):

        async def bid_ask_for(ticker, *args, **kwargs):
            # Tight spreads so spread_guard passes; mids differ from stale 1.0/2.0.
            if ticker == "AAPL":
                return (100.0, 100.1)  # mid 100.05
            return (200.0, 200.2)  # mid 200.1

        mock_bid_ask.side_effect = bid_ask_for
        monitor.brokerage.get_positions = AsyncMock(return_value=[])
        monitor.brokerage.place_value_order = AsyncMock()

        with pytest.raises(AssertionError, match="stop_after_legs"):
            await monitor.execute_trade(pair, "Short-Long", 1.0, 2.0, signal_id)

        assert captured["price_a"] == pytest.approx(100.05)
        assert captured["price_b"] == pytest.approx(200.1)
        monitor.brokerage.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_crypto_rejects_stale_execute_price(monitor):
    pair = {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD", "id": "ETH-USD_BTC-USD"}
    signal_id = str(uuid.uuid4())
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    async def _refresh(symbols, *args, **kwargs):
        from src.services.data_service import data_service

        data_service.last_price_sources = {
            "ETH-USD": "alpaca_crypto_snapshot",
            "BTC-USD": "alpaca_crypto_snapshot",
        }
        data_service.last_price_timestamps = {
            "ETH-USD": stale_ts,
            "BTC-USD": stale_ts,
        }
        return {"ETH-USD": 2000.0, "BTC-USD": 50000.0}

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch(
             "src.monitor.data_service.get_latest_price_async",
             new_callable=AsyncMock,
             side_effect=_refresh,
         ), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "SCAN_INTERVAL_SECONDS", 30):

        mock_bid_ask.return_value = (100.0, 100.05)
        monitor.brokerage.place_value_order = AsyncMock()

        result = await monitor.execute_trade(pair, "Short-Long", 2000.0, 50000.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "stale_execute_price"
        monitor.brokerage.place_value_order.assert_not_awaited()
