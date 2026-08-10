import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings
from src.services.data_service import data_service


@pytest.fixture(autouse=True)
def _fresh_alpaca_crypto_price_metadata(monkeypatch):
    """Crypto process_pair tests assume Alpaca freshness metadata is present.

    Production scan path always stamps sources/timestamps via data_service;
    unit tests that call process_pair directly must do the same or the
    fail-closed freshness gate (price_freshness_unknown) correctly blocks.
    """
    fresh_ts = (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat()
    tickers = (
        "BTC-USD",
        "ETH-USD",
        "LTC-USD",
        "BCH-USD",
        "SOL-USD",
        "AVAX-USD",
        "DOT-USD",
    )
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {t: "alpaca_crypto_snapshot" for t in tickers},
        raising=False,
    )
    monkeypatch.setattr(
        data_service,
        "last_price_timestamps",
        {t: fresh_ts for t in tickers},
        raising=False,
    )


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
async def test_process_pair_skips_when_kalman_beta_exceeds_admission_cap(monitor):
    """Equity live Kalman beta must honor PAIR_DISCOVERY_MAX_ABS_HEDGE."""
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT", "is_cointegrated": True}
    latest_prices = {"AAPL": 190.0, "MSFT": 420.0}
    max_abs = float(settings.PAIR_DISCOVERY_MAX_ABS_HEDGE)

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True):

        mock_kf = MagicMock()
        # Valid innovation/z, but beta past equity admission hedge cap.
        mock_kf.update.return_value = ([0.0, max_abs + 9.0], 0.1, 0.2, 0.5)
        mock_kf_get.return_value = mock_kf

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "extreme_kalman_beta"
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_pair_allows_crypto_beta_within_crypto_hedge_cap(monitor):
    """Intentional crypto pairs use PAIR_DISCOVERY_MAX_ABS_HEDGE_CRYPTO (not equity 25)."""
    pair = {
        "ticker_a": "BTC-USD",
        "ticker_b": "ETH-USD",
        "id": "BTC-USD_ETH-USD",
        "is_cointegrated": True,
    }
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    equity_cap = float(settings.PAIR_DISCOVERY_MAX_ABS_HEDGE)
    crypto_cap = float(settings.PAIR_DISCOVERY_MAX_ABS_HEDGE_CRYPTO)
    assert crypto_cap > equity_cap
    # Observed stuck beta (~34) exceeds equity cap but is fine for crypto.
    crypto_beta = equity_cap + 9.0
    assert crypto_beta < crypto_cap

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.redis_service.redis_service.get_fundamental_score", new_callable=AsyncMock, return_value=None):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, crypto_beta], 0.1, 0.2, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.1, "final_verdict": "VETO"}

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["reason"] != "extreme_kalman_beta"
    mock_save_state.assert_awaited()


@pytest.mark.asyncio
async def test_process_pair_skips_crypto_when_beta_exceeds_crypto_hedge_cap(monitor, monkeypatch):
    pair = {
        "ticker_a": "BTC-USD",
        "ticker_b": "ETH-USD",
        "id": "BTC-USD_ETH-USD",
        "is_cointegrated": True,
    }
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    # Keep below KALMAN_BETA_CLIP_MAX so the abs-hedge gate (not clip invalid) fires.
    monkeypatch.setattr(settings, "PAIR_DISCOVERY_MAX_ABS_HEDGE_CRYPTO", 100.0)

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 150.0], 0.1, 0.2, 0.5)
        mock_kf_get.return_value = mock_kf

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "extreme_kalman_beta"
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()


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
    monitor.active_pairs = [pair]

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
    monitor._rebuild_quarantined_kalman_pair = AsyncMock(return_value=True)

    rebuilt = await monitor._reload_quarantined_pairs_if_requested()

    assert rebuilt is True
    monitor._rebuild_quarantined_kalman_pair.assert_awaited_once_with(pair)
    monitor.reload_pairs.assert_not_awaited()
    assert monitor._kalman_quarantine_reload_requested is False


@pytest.mark.asyncio
async def test_quarantine_does_not_reload_repeatedly_after_rebuild(monitor):
    """A structurally-invalid pair must trigger the historical rebuild only ONCE.

    Regression: an extreme price-ratio pair (beta pinned at the clip) was
    re-quarantined every scan, and each quarantine re-requested a full pair
    reload — which reset the dashboard stage to 'pre_warming' forever and
    re-fetched 30d history on a loop.
    """
    pair = {
        "ticker_a": "BTC-USD",
        "ticker_b": "LTC-USD",
        "id": "BTC-USD_LTC-USD",
        "hedge_ratio": 900.0,
    }
    latest_prices = {"BTC-USD": 76800.0, "LTC-USD": 85.0}
    monitor.active_pairs = [pair]

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock), \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock), \
         patch("src.monitor.persistence_service.save_trading_pairs", new_callable=AsyncMock) as mock_save_pairs:

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

    assert second["reason"] == "kalman_quarantine_benched"
    # No second reload; Active slot is freed so discovery=false servers stop burning it.
    assert monitor._kalman_quarantine_reload_requested is False
    assert pair["id"] not in {p["id"] for p in monitor.active_pairs}
    mock_save_pairs.assert_awaited()
    benched = mock_save_pairs.await_args.args[0][0]
    assert benched["id"] == pair["id"]
    assert benched["status"] == "Benched"


@pytest.mark.asyncio
async def test_stuck_quarantine_benches_after_rebuild_exhausted(monitor):
    """Pairs left in kalman_state_quarantined after a failed rebuild must retire."""
    pair = {
        "ticker_a": "BTC-USD",
        "ticker_b": "LTC-USD",
        "id": "BTC-USD_LTC-USD",
        "hedge_ratio": 1446.0,
    }
    monitor.active_pairs = [pair]
    monitor.kalman_quarantined_pairs.add(pair["id"])
    monitor._kalman_rebuild_attempted.add(pair["id"])
    monitor._kalman_quarantine_reload_requested = False

    with patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock), \
         patch("src.monitor.persistence_service.save_trading_pairs", new_callable=AsyncMock) as mock_save_pairs, \
         patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get:

        diagnostic = await monitor.process_pair(pair, {"BTC-USD": 76800.0, "LTC-USD": 85.0})

    assert diagnostic["reason"] == "kalman_quarantine_benched"
    assert pair["id"] not in {p["id"] for p in monitor.active_pairs}
    assert pair["id"] not in monitor.kalman_quarantined_pairs
    mock_kf_get.assert_not_awaited()
    mock_save_pairs.assert_awaited()


@pytest.mark.asyncio
async def test_beyond_stop_zscore_skips_without_ai(monitor):
    """A signal already past the stop-loss z-score must be skipped before the
    (expensive) AI orchestration, since the profit guard would always veto it."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "BCH-USD", "id": "BTC-USD_BCH-USD"}
    latest_prices = {"BTC-USD": 62000.0, "BCH-USD": 234.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True):

        mock_kf = MagicMock()
        # Valid Kalman state (beta ok, innovation > 0) but z = 4.5 > STOP_LOSS_ZSCORE (3.5).
        mock_kf.update.return_value = ([0.0, 1.0], 0.1, 4.5, 0.5)
        mock_kf_get.return_value = mock_kf

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["reason"] == "beyond_stop_threshold"
    mock_orchestrator.assert_not_awaited()


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
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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


@pytest.mark.asyncio
async def test_process_pair_skips_approval_when_pair_already_open(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.notification_service.notification_service.request_approval", new_callable=AsyncMock) as mock_request_approval, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "_has_active_pair_or_pending_order", new_callable=AsyncMock, return_value=True) as mock_dup_gate, \
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

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "SKIPPED"
        assert diagnostic["reason"] == "already_open_or_pending"
        assert monitor.active_signals[-1]["status"] == "ALREADY_OPEN"
        mock_dup_gate.assert_awaited()
        assert mock_dup_gate.await_args.kwargs.get("notify") is False
        mock_request_approval.assert_not_awaited()
        mock_execute_trade.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_pair_marks_rejected_when_approval_denied(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.notification_service.notification_service.request_approval", new_callable=AsyncMock, return_value=False) as mock_request_approval, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "_has_active_pair_or_pending_order", new_callable=AsyncMock, return_value=False), \
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

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "REJECTED"
        assert diagnostic["reason"] == "approval_denied"
        assert monitor.active_signals[-1]["status"] == "REJECTED"
        mock_request_approval.assert_awaited_once()
        mock_execute_trade.assert_not_awaited()
