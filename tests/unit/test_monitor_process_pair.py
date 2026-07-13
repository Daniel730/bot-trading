import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings


@pytest.mark.asyncio
async def test_process_pair_blocks_clipped_kalman_state_before_orchestrator(monitor, caplog):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock), \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 0.001], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "kalman_state_invalid"
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()
    assert "KALMAN GUARD [BTC-USD/ETH-USD]" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_quarantines_invalid_kalman_state_until_rebuild(monitor):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 0.001], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}

        first = await monitor.process_pair(pair, latest_prices)
        second = await monitor.process_pair(pair, latest_prices)

    assert first["reason"] == "kalman_state_invalid"
    assert second["reason"] == "kalman_state_quarantined"
    assert mock_kf_get.await_count == 1
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()


@pytest.mark.asyncio
async def test_quarantined_kalman_state_requests_post_scan_rebuild(monitor):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "LTC-USD", "id": "BTC-USD_LTC-USD"}
    latest_prices = {"BTC-USD": 76800.0, "LTC-USD": 85.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 0.001], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["reason"] == "kalman_state_invalid"
    assert monitor._kalman_quarantine_reload_requested is True
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()

    monitor.reload_pairs = AsyncMock()

    rebuilt = await monitor._reload_quarantined_pairs_if_requested()

    assert rebuilt is True
    monitor.reload_pairs.assert_awaited_once()
    assert monitor._kalman_quarantine_reload_requested is False


@pytest.mark.asyncio
async def test_quarantine_does_not_reload_repeatedly_after_rebuild(monitor):
    """A structurally-invalid pair must trigger the historical rebuild only ONCE.

    Regression: an extreme price-ratio pair (beta pinned at the clip) was
    re-quarantined every scan, and each quarantine re-requested a full pair
    reload — which reset the dashboard stage to 'pre_warming' forever and
    re-fetched 30d history on a loop.
    """
    pair = {"ticker_a": "BTC-USD", "ticker_b": "LTC-USD", "id": "BTC-USD_LTC-USD"}
    latest_prices = {"BTC-USD": 76800.0, "LTC-USD": 85.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock), \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock):

        mock_kf = MagicMock()
        # beta pinned at the clip minimum -> invalid_kalman_state every call.
        mock_kf.update.return_value = ([0.0, 0.001], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf

        first = await monitor.process_pair(pair, latest_prices)
        assert first["reason"] == "kalman_state_invalid"
        assert monitor._kalman_quarantine_reload_requested is True
        assert pair["id"] in monitor._kalman_rebuild_attempted

        # Simulate the post-scan rebuild running: it clears the quarantine set and
        # resets the reload flag, but the pair remains invalid on the next scan.
        monitor._kalman_quarantine_reload_requested = False
        monitor.kalman_quarantined_pairs.discard(pair["id"])

        second = await monitor.process_pair(pair, latest_prices)

    assert second["reason"] == "kalman_state_invalid"
    # The key assertion: no second reload is requested, so the stage/warm loop stops.
    assert monitor._kalman_quarantine_reload_requested is False


@pytest.mark.asyncio
async def test_orchestrator_veto(monitor):
    """
    S-07: Test orchestrator veto path in process_pair.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock) as mock_audit, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf

        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
            "fee_status": {"total_friction_percent": 0.0},
        }
        mock_estimate_profit.return_value = MagicMock(
            net_profit=10.0,
            profit_margin_pct=0.03,
            gross_profit=12.0,
            expected_loss=8.0,
            loss_margin_pct=0.02,
            friction_usd=2.0,
        )

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.3
        mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_process_pair_low_confidence_veto_precedes_profit_guard(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True), \
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.3
        mock_validate_trade.assert_not_called()
        mock_estimate_profit.assert_not_called()
        assert monitor.active_signals[-1]["status"] == "VETOED"
        assert monitor.active_signals[-1]["confidence"] == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_process_pair_orchestrator_veto_text_precedes_profit_guard(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True), \
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {
            "final_confidence": 0.8,
            "final_verdict": "VETO: conflicting macro regime",
        }

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.8
        assert diagnostic["reason"] == "orchestrator_veto"
        mock_validate_trade.assert_not_called()
        mock_estimate_profit.assert_not_called()
        assert monitor.active_signals[-1]["status"] == "VETOED"
        assert monitor.active_signals[-1]["confidence"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_process_pair_unprofitable_veto_preserves_confidence(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True), \
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.8, "final_verdict": "APPROVE"}
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
            "fee_status": {"total_friction_percent": 0.002},
        }
        mock_estimate_profit.return_value = MagicMock(
            net_profit=-0.25,
            profit_margin_pct=-0.01,
            gross_profit=0.25,
            expected_loss=8.0,
            loss_margin_pct=0.02,
            friction_usd=0.5,
            spread_capture=0.75,
            stop_spread_move=12.0,
        )

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.8
        assert diagnostic["profit_guard_net_profit"] == -0.25
        assert diagnostic["profit_guard_gross_profit"] == 0.25
        assert diagnostic["profit_guard_friction_usd"] == 0.5
        assert diagnostic["profit_guard_friction_pct"] == 0.002
        assert diagnostic["profit_guard_gross_notional"] == pytest.approx(299.98)
        assert diagnostic["profit_guard_quantity_a"] == pytest.approx(0.666666)
        assert diagnostic["profit_guard_quantity_b"] == pytest.approx(0.666666)
        assert diagnostic["profit_guard_z_score"] == 3.0
        assert monitor.active_signals[-1]["status"] == "VETOED_UNPROFITABLE"
        assert monitor.active_signals[-1]["confidence"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_process_pair_does_not_mark_failed_execution_as_executed(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.notification_service.notification_service.request_approval", new_callable=AsyncMock, return_value=True), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "execute_trade", new_callable=AsyncMock) as mock_execute_trade, \
         patch.object(monitor, "is_market_open", return_value=True), \
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.8, "final_verdict": "APPROVE"}
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
            "fee_status": {"total_friction_percent": 0.0},
        }
        mock_estimate_profit.return_value = MagicMock(
            net_profit=10.0,
            profit_margin_pct=0.03,
            gross_profit=12.0,
            expected_loss=8.0,
            loss_margin_pct=0.02,
            friction_usd=2.0,
        )
        mock_execute_trade.return_value = {
            "executed": False,
            "reason": "duplicate_active_pair",
        }

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "EXECUTION_BLOCKED"
        assert monitor.active_signals[-1]["status"] == "EXECUTION_BLOCKED"
        assert mock_execute_trade.await_count == 1
