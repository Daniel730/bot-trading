"""Shadow vs broker-paper execution lane: mutual exclusion, signal_id, close routing."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings
from src.services.execution_lane import (
    LANE_BROKER_PAPER,
    LANE_LIVE,
    LANE_SHADOW,
    close_uses_broker,
    resolve_execution_lane,
    signal_is_shadow,
    stamp_trade_metadata,
)
from src.services.persistence_service import ExitReason, OrderStatus


def test_resolve_execution_lane_mutual_exclusion():
    assert resolve_execution_lane(paper_trading=True, broker_paper_trading=False) == LANE_SHADOW
    # PAPER_TRADING wins even if broker_paper flag were somehow true
    assert resolve_execution_lane(paper_trading=True, broker_paper_trading=True) == LANE_SHADOW
    assert resolve_execution_lane(paper_trading=False, broker_paper_trading=True) == LANE_BROKER_PAPER
    assert resolve_execution_lane(paper_trading=False, broker_paper_trading=False) == LANE_LIVE


def test_settings_execution_lane_shadow_vs_broker_paper(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    assert settings.execution_lane == LANE_SHADOW
    assert settings.is_broker_paper_trading is False

    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    assert settings.execution_lane == LANE_BROKER_PAPER
    assert settings.is_broker_paper_trading is True


def test_stamp_trade_metadata_never_dual_tags_shadow_and_broker():
    shadow = stamp_trade_metadata(
        {"is_shadow": True, "direction": "Long-Short"},
        execution_lane=LANE_BROKER_PAPER,
        broker_paper_trading=True,
    )
    assert shadow["is_shadow"] is True
    assert shadow["execution_lane"] == LANE_SHADOW
    assert shadow["broker_paper_trading"] is False

    broker = stamp_trade_metadata(
        {"broker_order_id": "x"},
        execution_lane=LANE_BROKER_PAPER,
        broker_paper_trading=True,
    )
    assert broker["is_shadow"] is False
    assert broker["execution_lane"] == LANE_BROKER_PAPER
    assert broker["broker_paper_trading"] is True


def test_close_uses_broker_follows_open_lane_not_only_env():
    shadow_signal = {
        "signal_id": "s1",
        "legs": [
            {
                "ticker": "AAPL",
                "side": "BUY",
                "quantity": 1,
                "price": 100,
                "metadata": {"is_shadow": True, "execution_lane": LANE_SHADOW},
            }
        ],
    }
    # Even if PAPER_TRADING flipped off, do not hit the broker for shadow opens.
    assert close_uses_broker(shadow_signal, paper_trading=False) is False
    assert signal_is_shadow(shadow_signal) is True

    broker_signal = {
        "signal_id": "s2",
        "is_shadow": False,
        "execution_lane": LANE_BROKER_PAPER,
        "legs": [
            {
                "ticker": "AAPL",
                "side": "BUY",
                "quantity": 1,
                "price": 100,
                "metadata": {"is_shadow": False, "execution_lane": LANE_BROKER_PAPER},
            }
        ],
    }
    # Even if PAPER_TRADING flipped on, still close via broker for tagged broker opens.
    assert close_uses_broker(broker_signal, paper_trading=True) is True
    assert signal_is_shadow(broker_signal) is False

    # Untagged legacy: fall back to current PAPER_TRADING.
    legacy = {"signal_id": "s3", "legs": [{"ticker": "AAPL", "side": "BUY", "quantity": 1, "price": 1}]}
    assert close_uses_broker(legacy, paper_trading=True) is False
    assert close_uses_broker(legacy, paper_trading=False) is True


@pytest.mark.asyncio
async def test_execute_trade_shadow_never_calls_broker(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.monitor.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_journal, \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "STABLE", "confidence": 0.9, "features": {}}
        monitor.brokerage.place_value_order = AsyncMock()

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

    assert result == {"executed": True, "reason": "paper_shadow_executed"}
    mock_shadow.assert_awaited_once()
    assert mock_shadow.await_args.kwargs.get("signal_id") == signal_id
    monitor.brokerage.place_value_order.assert_not_awaited()
    journal = mock_journal.await_args.args[0]
    assert journal["signal_id"] == uuid.UUID(signal_id)
    assert journal["metrics_at_entry"]["execution_lane"] == LANE_SHADOW
    assert journal["metrics_at_entry"]["paper_trade"] is True


@pytest.mark.asyncio
async def test_execute_trade_broker_paper_never_calls_shadow(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.monitor.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_journal, \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False), \
         patch.object(settings, "LIVE_CAPITAL_DANGER", True), \
         patch.object(settings, "BROKERAGE_PROVIDER", "ALPACA"), \
         patch.object(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "STABLE", "confidence": 0.9, "features": {}}
        mock_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 300.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])
        monitor.brokerage.get_account_cash = MagicMock(return_value=10_000.0)
        monitor.brokerage.get_account_equity = MagicMock(return_value=10_000.0)
        monitor.brokerage.get_account_buying_power = MagicMock(return_value=10_000.0)
        monitor.brokerage.get_pending_orders_value = MagicMock(return_value=0.0)

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert result["executed"] is True
        mock_shadow.assert_not_awaited()
        assert monitor.brokerage.place_value_order.await_count == 2
        assert settings.execution_lane == LANE_BROKER_PAPER
        journal = mock_journal.await_args.args[0]
        assert journal["signal_id"] == uuid.UUID(signal_id)
        assert journal["metrics_at_entry"]["execution_lane"] == LANE_BROKER_PAPER
        assert journal["metrics_at_entry"]["paper_trade"] is False
        assert journal["metrics_at_entry"]["broker_paper_trading"] is True


@pytest.mark.asyncio
async def test_execute_trade_blocks_shadow_when_broker_signal_open(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    open_broker = {
        "signal_id": str(uuid.uuid4()),
        "is_shadow": False,
        "execution_lane": LANE_BROKER_PAPER,
        "legs": [
            {"ticker": "KO", "side": "BUY", "quantity": 1, "price": 50, "is_shadow": False,
             "metadata": {"is_shadow": False, "execution_lane": LANE_BROKER_PAPER}},
            {"ticker": "PEP", "side": "SELL", "quantity": 1, "price": 50, "is_shadow": False,
             "metadata": {"is_shadow": False, "execution_lane": LANE_BROKER_PAPER}},
        ],
    }

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.monitor.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=[open_broker]), \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "STABLE", "confidence": 0.9, "features": {}}

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, str(uuid.uuid4()))

    assert result == {"executed": False, "reason": "mixed_execution_lane_blocked"}
    mock_shadow.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_shadow_skips_broker_even_if_paper_trading_false(monitor):
    signal = {
        "signal_id": str(uuid.uuid4()),
        "is_shadow": True,
        "execution_lane": LANE_SHADOW,
        "legs": [
            {
                "ticker": "AAPL",
                "quantity": 10,
                "side": "BUY",
                "price": 150.0,
                "is_shadow": True,
                "metadata": {"is_shadow": True, "execution_lane": LANE_SHADOW},
            },
            {
                "ticker": "MSFT",
                "quantity": 5,
                "side": "SELL",
                "price": 300.0,
                "is_shadow": True,
                "metadata": {"is_shadow": True, "execution_lane": LANE_SHADOW},
            },
        ],
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch("src.services.shadow_service.shadow_service.close_simulated_trade", new_callable=AsyncMock) as mock_shadow_close, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False):
        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock()

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        monitor.brokerage.place_value_order.assert_not_awaited()
        mock_shadow_close.assert_awaited_once()
        mock_persistence.close_trade.assert_awaited_once()
        # Single ledger write — close_simulated_trade must not also persist.
        assert mock_persistence.close_trade.await_count == 1


@pytest.mark.asyncio
async def test_close_broker_paper_uses_broker_even_if_paper_trading_true(monitor):
    signal = {
        "signal_id": str(uuid.uuid4()),
        "is_shadow": False,
        "execution_lane": LANE_BROKER_PAPER,
        "legs": [
            {
                "ticker": "AAPL",
                "quantity": 10,
                "side": "BUY",
                "price": 150.0,
                "is_shadow": False,
                "metadata": {"is_shadow": False, "execution_lane": LANE_BROKER_PAPER},
            },
            {
                "ticker": "MSFT",
                "quantity": 5,
                "side": "SELL",
                "price": 300.0,
                "is_shadow": False,
                "metadata": {"is_shadow": False, "execution_lane": LANE_BROKER_PAPER},
            },
        ],
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch("src.services.shadow_service.shadow_service.close_simulated_trade", new_callable=AsyncMock) as mock_shadow_close, \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch.object(monitor, "_preflight_live_sell_inventory", new_callable=AsyncMock, return_value=True), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "DEV_MODE", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", True):
        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "close-a"},
            {"status": "success", "order_id": "close-b"},
        ])
        monitor.brokerage.get_available_quantity = MagicMock(side_effect=[0.0, 0.0])
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 10.0, "filled_avg_price": 160.0},
            {"status": "filled", "filled_qty": 5.0, "filled_avg_price": 290.0},
        ]

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        assert monitor.brokerage.place_value_order.await_count == 2
        mock_shadow_close.assert_not_awaited()
        mock_persistence.close_trade.assert_awaited_once()
