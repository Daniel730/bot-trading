"""#150: capital-halt HWM uses managed equity under IGNORE_UNMANAGED."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings
from src.services.capital_halt_service import evaluate_capital_halt
from src.services.unmanaged_positions_service import unmanaged_market_value


def test_unmanaged_market_value_excludes_ledger_legs():
    positions = [
        {"ticker": "NVDA", "quantity": 10.0, "marketValue": 40_000.0},
        {"ticker": "AAPL", "quantity": 5.0, "marketValue": 1_000.0},
    ]
    open_signals = [{"legs": [{"ticker": "AAPL"}, {"ticker": "MSFT"}]}]
    assert unmanaged_market_value(positions, open_signals) == pytest.approx(40_000.0)


@pytest.mark.asyncio
async def test_hwm_tracks_managed_equity_not_full_broker(monkeypatch):
    """Unmanaged MV must not inflate equity_high_water_mark under IGNORE_UNMANAGED."""
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "IGNORE_UNMANAGED_POSITIONS", True)
    monkeypatch.setattr(settings, "MAX_DRAWDOWN", 0.50)

    persistence = SimpleNamespace(
        get_system_state=AsyncMock(side_effect=lambda key, default=None: {
            "operational_status": "NORMAL",
            "equity_high_water_mark": "0",
        }.get(key, default)),
        get_daily_pnl_for_date=AsyncMock(return_value=0.0),
        set_system_state=AsyncMock(),
        get_open_signals=AsyncMock(return_value=[]),
    )

    class FakeBroker:
        async def get_account_equity(self):
            return 50_000.0

        async def get_positions(self):
            return [
                {
                    "ticker": "NVDA",
                    "quantity": 10.0,
                    "quantityAvailableForTrading": 10.0,
                    "marketValue": 40_000.0,
                }
            ]

    with patch("src.services.brokerage_service.BrokerageService", return_value=FakeBroker()):
        result = await evaluate_capital_halt(persistence_service=persistence)

    assert result["halt"] is False
    assert result["details"]["equity_base"] == "managed"
    assert result["details"]["broker_equity"] == pytest.approx(50_000.0)
    assert result["details"]["unmanaged_mv"] == pytest.approx(40_000.0)
    assert result["details"]["current_equity"] == pytest.approx(10_000.0)
    persistence.set_system_state.assert_any_await("equity_high_water_mark", "10000.0")


@pytest.mark.asyncio
async def test_managed_drawdown_not_masked_by_unmanaged_mv(monkeypatch):
    """Managed-book DD must halt even when full broker equity looks flat."""
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "IGNORE_UNMANAGED_POSITIONS", True)
    monkeypatch.setattr(settings, "MAX_DRAWDOWN", 0.10)

    # Managed HWM was 10k; broker equity still ~48.5k with 40k unmanaged → managed 8.5k (15% DD).
    persistence = SimpleNamespace(
        get_system_state=AsyncMock(side_effect=lambda key, default=None: {
            "operational_status": "NORMAL",
            "equity_high_water_mark": "10000",
        }.get(key, default)),
        get_daily_pnl_for_date=AsyncMock(return_value=0.0),
        set_system_state=AsyncMock(),
        get_open_signals=AsyncMock(return_value=[]),
    )

    class FakeBroker:
        async def get_account_equity(self):
            return 48_500.0

        async def get_positions(self):
            return [
                {
                    "ticker": "NVDA",
                    "quantity": 10.0,
                    "quantityAvailableForTrading": 10.0,
                    "marketValue": 40_000.0,
                }
            ]

    with patch("src.services.brokerage_service.BrokerageService", return_value=FakeBroker()):
        result = await evaluate_capital_halt(persistence_service=persistence)

    assert result["halt"] is True
    assert result["reason"] == "equity_drawdown_exceeds_max_drawdown"
    assert result["details"]["equity_base"] == "managed"
    assert result["details"]["current_equity"] == pytest.approx(8_500.0)
    assert result["details"]["equity_drawdown_fraction"] == pytest.approx(0.15)
    # Must not ratchet HWM up to full broker equity
    for call in persistence.set_system_state.await_args_list:
        assert call.args[0] != "equity_high_water_mark" or float(call.args[1]) <= 10_000.0


@pytest.mark.asyncio
async def test_full_broker_equity_hwm_when_ignore_unmanaged_off(monkeypatch):
    """With IGNORE_UNMANAGED off, HWM still uses full broker equity (R-303 baseline)."""
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "IGNORE_UNMANAGED_POSITIONS", False)
    monkeypatch.setattr(settings, "MAX_DRAWDOWN", 0.10)

    persistence = SimpleNamespace(
        get_system_state=AsyncMock(side_effect=lambda key, default=None: {
            "operational_status": "NORMAL",
            "equity_high_water_mark": "100000",
        }.get(key, default)),
        get_daily_pnl_for_date=AsyncMock(return_value=0.0),
        set_system_state=AsyncMock(),
        get_open_signals=AsyncMock(return_value=[]),
    )

    class FakeBroker:
        async def get_account_equity(self):
            return 85_000.0

        async def get_positions(self):
            raise AssertionError("positions must not be probed when ignore-unmanaged is off")

    with patch("src.services.brokerage_service.BrokerageService", return_value=FakeBroker()):
        result = await evaluate_capital_halt(persistence_service=persistence)

    assert result["halt"] is True
    assert result["reason"] == "equity_drawdown_exceeds_max_drawdown"
    assert result["details"]["equity_base"] == "broker"
    assert result["details"]["current_equity"] == pytest.approx(85_000.0)
