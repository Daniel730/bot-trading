"""Dashboard pair-discovery operator surface helpers."""
from __future__ import annotations

from src.services.dashboard_service import (
    _denylist_display,
    _pair_discovery_status,
    dashboard_state,
)


def test_denylist_display_dedupes_leg_order(monkeypatch):
    monkeypatch.setattr(
        "src.services.dashboard_service.settings.PAIR_DENYLIST",
        "BTC-USD_BCH-USD,BCH-USD_BTC-USD,KO_PEP",
    )
    assert _denylist_display() == ["BTC-USD_BCH-USD", "KO_PEP"]


def test_pair_discovery_status_includes_promote_meta(monkeypatch):
    monkeypatch.setattr(dashboard_state, "terminal_messages", [
        {
            "type": "SYSTEM",
            "text": "Pair discovery completed for dashboard. promoted=1 benched=1.",
            "timestamp": "2026-08-04T01:00:00+00:00",
            "metadata": {
                "type": "pair_discovery",
                "status": "completed",
                "promoted": ["KO_PEP"],
                "benched": ["BTC-USD_BCH-USD"],
            },
        }
    ])
    monkeypatch.setattr(
        "src.services.dashboard_service.settings.PAIR_DISCOVERY_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "src.services.dashboard_service.settings.PAIR_DISCOVERY_AUTO_PROMOTE",
        True,
    )

    status = _pair_discovery_status()
    assert status["last_status"] == "completed"
    assert status["promoted"] == ["KO_PEP"]
    assert status["benched"] == ["BTC-USD_BCH-USD"]
    assert status["auto_promote"] is True
    assert status["enabled"] is True
    assert "promoted=1" in (status["last_message"] or "")
