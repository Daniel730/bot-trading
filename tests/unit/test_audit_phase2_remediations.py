"""Phase-2 audit remediations (F-014, F-002 gate, F-004, F-018, F-019, F-021)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings, _atomic_json_write, _guard_kalman_delta, settings
from src.services.brokerage_service import BrokerageService
from src.services.capital_halt_service import evaluate_capital_halt


def test_f021_kalman_delta_rejects_unity_and_above():
    with pytest.raises(ValueError, match=r"\(0, 1\)"):
        _guard_kalman_delta(1.0)
    with pytest.raises(ValueError, match=r"\(0, 1\)"):
        _guard_kalman_delta(0.0)
    assert _guard_kalman_delta(1e-5) == pytest.approx(1e-5)


def test_f019_atomic_json_write(tmp_path: Path):
    target = tmp_path / "bot_settings.json"
    _atomic_json_write(target, {"A": 1})
    assert json.loads(target.read_text()) == {"A": 1}
    _atomic_json_write(target, {"A": 2, "B": True})
    assert json.loads(target.read_text()) == {"A": 2, "B": True}
    assert not list(tmp_path.glob(".bot_settings.json.*.tmp"))


@pytest.mark.asyncio
async def test_f002_broker_gate_blocks_open_when_halted(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "DEV_MODE", False)

    svc = BrokerageService.__new__(BrokerageService)
    svc.provider_name = "ALPACA"
    svc.provider = SimpleNamespace(
        place_value_order=AsyncMock(return_value={"status": "success", "order_id": "x"})
    )

    with patch(
        "src.services.capital_halt_service.enforce_capital_halt_or_raise_state",
        new=AsyncMock(
            return_value={
                "halt": True,
                "reason": "daily_loss_exceeds_max_drawdown",
                "details": {},
            }
        ),
    ):
        result = await svc.place_value_order("AAPL", 10.0, "BUY", intent="open")

    assert result["status"] == "error"
    assert "capital_halt" in result["message"]
    svc.provider.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_f002_broker_gate_allows_close_when_halted(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)

    svc = BrokerageService.__new__(BrokerageService)
    svc.provider_name = "ALPACA"
    svc.provider = SimpleNamespace(
        place_value_order=AsyncMock(return_value={"status": "success", "order_id": "close-1"})
    )
    result = await svc.place_value_order(
        "AAPL", 10.0, "SELL", client_order_id="c1", intent="close"
    )
    assert result["status"] == "success"
    svc.provider.place_value_order.assert_awaited_once()


@pytest.mark.asyncio
async def test_f004_broker_gate_blocks_without_live_capital_danger(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", False)

    svc = BrokerageService.__new__(BrokerageService)
    svc.provider_name = "ALPACA"
    svc.provider = SimpleNamespace(place_value_order=AsyncMock())
    result = await svc.place_value_order("AAPL", 10.0, "BUY", intent="open")
    assert result["status"] == "error"
    assert "LIVE_CAPITAL_DANGER" in result["message"]
    svc.provider.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_f002_daily_pnl_unavailable_fail_closed_on_broker(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "MAX_DRAWDOWN", 0.1)
    monkeypatch.setattr(settings, "ALPACA_BUDGET_USD", 10_000.0)

    persistence = SimpleNamespace(
        get_system_state=AsyncMock(return_value="NORMAL"),
        get_daily_pnl_for_date=AsyncMock(side_effect=RuntimeError("db down")),
    )
    result = await evaluate_capital_halt(persistence_service=persistence)
    assert result["halt"] is True
    assert result["reason"] == "daily_pnl_unavailable"


def test_f005_still_exact_hostname():
    good = Settings.model_construct(ALPACA_BASE_URL="https://paper-api.alpaca.markets")
    bad = Settings.model_construct(
        ALPACA_BASE_URL="https://evil.example/paper-api.alpaca.markets"
    )
    assert good.is_alpaca_paper_endpoint is True
    assert bad.is_alpaca_paper_endpoint is False
