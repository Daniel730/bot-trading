from datetime import datetime as real_datetime

from src.config import settings
from src.monitor import ArbitrageMonitor


class _NewYearsDayDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 1, 1, 10, 0)
        if tz is None:
            return current
        return tz.localize(current)


def test_holiday_blocks_equity_scan_even_inside_suffix_window(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr("src.monitor.datetime", _NewYearsDayDateTime)

    monitor = object.__new__(ArbitrageMonitor)

    assert monitor.is_market_open("AAPL") is False
