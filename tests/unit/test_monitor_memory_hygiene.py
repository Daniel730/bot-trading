"""Unit coverage for monitor runtime cache pruning / memory pressure valve."""

from __future__ import annotations

from collections import deque
from unittest.mock import MagicMock

import pytest

from src.services.decision_trace_service import DecisionEvent, reset_decision_recorder_for_tests


@pytest.mark.asyncio
async def test_prune_runtime_caches_drops_stale_signals_and_markers(monitor, monkeypatch):
    monkeypatch.setattr("src.monitor.settings.MAX_ACTIVE_PAIRS", 2)
    monkeypatch.setattr("src.monitor.settings.MEMORY_ACTIVE_SIGNAL_MAX", 10)

    monitor.active_pairs = [
        {"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT"},
    ]
    monitor.active_signals = [
        {"ticker_a": "AAPL", "ticker_b": "MSFT", "status": "Analyzing"},
        {"ticker_a": "KO", "ticker_b": "PEP", "status": "VETOED"},
        {"ticker_a": "AAPL", "ticker_b": "MSFT", "status": "VETOED_SIZE"},
    ]
    monitor._crypto_snapshot_pair_prices = {
        "AAPL_MSFT": ((1.0, 2.0), 1),
        "KO_PEP": ((3.0, 4.0), 2),
    }

    soft = monitor._prune_runtime_caches(aggressive=False)
    assert soft["signals_after"] == 2  # both AAPL/MSFT rows kept when not aggressive
    assert "KO_PEP" not in monitor._crypto_snapshot_pair_prices
    assert "AAPL_MSFT" in monitor._crypto_snapshot_pair_prices

    hard = monitor._prune_runtime_caches(aggressive=True)
    assert hard["signals_after"] == 1
    assert monitor.active_signals[0]["status"] == "Analyzing"


def test_maybe_relieve_memory_pressure_aggressive_when_over_threshold(monitor, monkeypatch):
    recorder = reset_decision_recorder_for_tests(maxsize=20)
    recorder._events = deque(
        [
            DecisionEvent(
                ts="t0",
                level="compact",
                scan_id="s",
                pair_id="AAPL_MSFT",
                signal_id=None,
                stage="scan",
                outcome="skip",
                reason="below_entry_threshold",
            ),
            DecisionEvent(
                ts="t1",
                level="compact",
                scan_id="s",
                pair_id="AAPL_MSFT",
                signal_id="sig",
                stage="exec",
                outcome="execute",
                reason="filled",
                promoted=True,
            ),
        ],
        maxlen=20,
    )

    monitor.active_pairs = [{"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT"}]
    monitor.active_signals = [
        {"ticker_a": "AAPL", "ticker_b": "MSFT", "status": "VETOED"},
    ]
    monkeypatch.setattr(monitor, "_read_process_rss_mib", lambda: 950)
    monkeypatch.setattr("src.monitor.settings.MEMORY_PRESSURE_THRESHOLD_MIB", 900)
    monkeypatch.setattr("src.monitor.gc.collect", MagicMock(return_value=3))

    monitor._maybe_relieve_memory_pressure(reason="unit_test")

    assert monitor.active_signals == []
    outcomes = {event.outcome for event in recorder._events}
    assert "execute" in outcomes
    assert "skip" not in outcomes
