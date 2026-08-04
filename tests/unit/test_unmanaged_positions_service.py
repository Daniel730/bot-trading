"""Tests for unmanaged broker position acknowledgement (no OPEN ledger import)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.services.unmanaged_positions_service import (
    acknowledge_symbols,
    classify_broker_positions,
    filter_unacked_symbols,
    load_acknowledgements,
    parse_acknowledgements,
)


def test_classify_splits_managed_unmanaged_and_acknowledged():
    broker = [
        {"ticker": "BTC-USD", "quantity": 0.1, "marketValue": 11000},
        {"ticker": "AAPL", "quantity": 5, "marketValue": 1000},
        {"ticker": "ETH-USD", "quantity": 1.0, "marketValue": 3000},
    ]
    open_signals = [
        {
            "signal_id": "sig-1",
            "legs": [
                {"ticker": "AAPL", "quantity": 5, "side": "BUY"},
                {"ticker": "MSFT", "quantity": 2, "side": "SELL"},
            ],
        }
    ]
    acks = {
        "symbols": {
            "ETH-USD": {"symbol": "ETH-USD", "note": "reviewed"},
        }
    }
    result = classify_broker_positions(broker, open_signals, acks)
    assert [r["symbol"] for r in result["managed"]] == ["AAPL"]
    assert result["unmanaged_symbols"] == ["BTC-USD"]
    assert result["acknowledged_symbols"] == ["ETH-USD"]


def test_filter_unacked_symbols_drops_acknowledged():
    remaining = filter_unacked_symbols(
        ["BTC-USD", "ETH-USD", "SOL-USD"],
        {"symbols": {"ETH-USD": {}, "SOL-USD": {}}},
    )
    assert remaining == ["BTC-USD"]


def test_filter_unacked_symbols_matches_btc_usd_vs_btcusd_aliases():
    """Alpaca may surface BTC-USD while ack store / ledger use BTCUSD (or vice versa)."""
    assert filter_unacked_symbols(
        ["BTC-USD", "ETH-USD"],
        {"symbols": {"BTCUSD": {"note": "acked"}}},
    ) == ["ETH-USD"]
    assert filter_unacked_symbols(
        ["BTCUSD", "AAPL"],
        {"symbols": {"BTC-USD": {"note": "acked"}}},
    ) == ["AAPL"]


def test_parse_acknowledgements_rekeys_hyphenated_aliases():
    raw = json.dumps(
        {
            "symbols": {
                "BTC-USD": {"symbol": "BTC-USD", "note": "legacy"},
                "ETHUSD": {"symbol": "ETH-USD", "note": "already_canonical"},
            },
            "updated_at": "2026-08-04T18:58:16+00:00",
        }
    )
    parsed = parse_acknowledgements(raw)
    assert set(parsed["symbols"]) == {"BTCUSD", "ETHUSD"}
    assert parsed["symbols"]["BTCUSD"]["note"] == "legacy"


def test_classify_acknowledges_when_ack_key_is_stripped_form():
    broker = [{"ticker": "BTC-USD", "quantity": 0.1, "marketValue": 11000}]
    acks = {"symbols": {"BTCUSD": {"symbol": "BTC-USD", "note": "reviewed"}}}
    result = classify_broker_positions(broker, [], acks)
    assert result["unmanaged_symbols"] == []
    assert result["acknowledged_symbols"] == ["BTC-USD"]


@pytest.mark.asyncio
async def test_acknowledge_symbols_persists_provenance_without_open_signals():
    stored = {}

    async def _get(key, default=None):
        return stored.get(key, default)

    async def _set(key, value):
        stored[key] = value

    with patch(
        "src.services.unmanaged_positions_service.persistence_service.get_system_state",
        new=AsyncMock(side_effect=_get),
    ), patch(
        "src.services.unmanaged_positions_service.persistence_service.set_system_state",
        new=AsyncMock(side_effect=_set),
    ):
        payload = await acknowledge_symbols(
            symbols=["BTC-USD"],
            positions=[{"ticker": "BTC-USD", "quantity": 0.12, "marketValue": 11000}],
            actor="test",
            note="paper_ack",
        )
        loaded = await load_acknowledgements()

    assert "BTCUSD" in payload["symbols"]
    assert payload["symbols"]["BTCUSD"]["provenance"] == "broker_foreign_holding"
    assert loaded["symbols"]["BTCUSD"]["actor"] == "test"
    assert json.loads(stored["unmanaged_positions_acknowledged"])["symbols"]["BTCUSD"]["note"] == "paper_ack"
    alert = json.loads(stored["unmanaged_broker_positions"])
    assert alert["acknowledged_only"] is True
    assert alert["symbols"] == ["BTCUSD"]


@pytest.mark.asyncio
async def test_acknowledge_does_not_truncate_large_payload():
    stored = {}

    async def _get(key, default=None):
        return stored.get(key, default)

    async def _set(key, value):
        stored[key] = value

    symbols = [f"SYM{i}-USD" for i in range(80)]
    positions = [{"ticker": s, "quantity": 1.0, "marketValue": 100.0} for s in symbols]

    with patch(
        "src.services.unmanaged_positions_service.persistence_service.get_system_state",
        new=AsyncMock(side_effect=_get),
    ), patch(
        "src.services.unmanaged_positions_service.persistence_service.set_system_state",
        new=AsyncMock(side_effect=_set),
    ):
        payload = await acknowledge_symbols(symbols=symbols, positions=positions, actor="test")

    raw = stored["unmanaged_positions_acknowledged"]
    assert len(raw) > 8000
    roundtrip = json.loads(raw)
    assert len(roundtrip["symbols"]) == 80
