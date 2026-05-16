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


class _DayAfterThanksgivingDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 11, 27, 14, 0)
        if tz is None:
            return current
        return tz.localize(current)


class _HongKongChristmasEveMorningDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 12, 24, 11, 0)
        if tz is None:
            return current
        return tz.localize(current)


class _HongKongChristmasEveAfternoonDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 12, 24, 13, 0)
        if tz is None:
            return current
        return tz.localize(current)


class _LondonChristmasEveMorningDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 12, 24, 11, 0)
        if tz is None:
            return current
        return tz.localize(current)


class _LondonChristmasEveAfternoonDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 12, 24, 13, 0)
        if tz is None:
            return current
        return tz.localize(current)


class _XetraChristmasEveDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 12, 24, 10, 0)
        if tz is None:
            return current
        return tz.localize(current)


class _AmsterdamChristmasEveMorningDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 12, 24, 11, 0)
        if tz is None:
            return current
        return tz.localize(current)


class _AmsterdamChristmasEveAfternoonDateTime:
    @classmethod
    def now(cls, tz=None):
        current = real_datetime(2026, 12, 24, 15, 0)
        if tz is None:
            return current
        return tz.localize(current)


def test_holiday_blocks_equity_scan_even_inside_suffix_window(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr("src.monitor.datetime", _NewYearsDayDateTime)

    monitor = object.__new__(ArbitrageMonitor)

    assert monitor.is_market_open("AAPL") is False


def test_nyse_half_day_blocks_equity_scan_after_early_close(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr("src.monitor.datetime", _DayAfterThanksgivingDateTime)

    monitor = object.__new__(ArbitrageMonitor)

    assert monitor.is_market_open("AAPL") is False


def test_hk_half_day_uses_local_session_and_blocks_afternoon(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monitor = object.__new__(ArbitrageMonitor)

    monkeypatch.setattr("src.monitor.datetime", _HongKongChristmasEveMorningDateTime)
    assert monitor.is_market_open("0700.HK") is True

    monkeypatch.setattr("src.monitor.datetime", _HongKongChristmasEveAfternoonDateTime)
    assert monitor.is_market_open("0700.HK") is False


def test_lse_half_day_blocks_equity_scan_after_early_close(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monitor = object.__new__(ArbitrageMonitor)

    monkeypatch.setattr("src.monitor.datetime", _LondonChristmasEveMorningDateTime)
    assert monitor.is_market_open("SHEL.L") is True

    monkeypatch.setattr("src.monitor.datetime", _LondonChristmasEveAfternoonDateTime)
    assert monitor.is_market_open("SHEL.L") is False


def test_xetra_exchange_closure_blocks_equity_scan(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr("src.monitor.datetime", _XetraChristmasEveDateTime)

    monitor = object.__new__(ArbitrageMonitor)

    assert monitor.is_market_open("SAP.DE") is False


def test_euronext_half_day_blocks_scan_after_early_close(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monitor = object.__new__(ArbitrageMonitor)

    monkeypatch.setattr("src.monitor.datetime", _AmsterdamChristmasEveMorningDateTime)
    assert monitor.is_market_open("ASML.AS") is True
    assert monitor.is_market_open("AIR.PA") is True

    monkeypatch.setattr("src.monitor.datetime", _AmsterdamChristmasEveAfternoonDateTime)
    assert monitor.is_market_open("ASML.AS") is False
    assert monitor.is_market_open("AIR.PA") is False
