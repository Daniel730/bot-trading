"""Corporate-action jump detection for Kalman invalidation / benching."""

import pandas as pd

from src.services.arbitrage_service import ArbitrageService


def test_series_has_corporate_action_jump_detects_split_sized_move():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    series_a = pd.Series([100.0, 101.0, 50.0, 50.5, 51.0], index=idx)  # ~50% drop
    series_b = pd.Series([200.0, 201.0, 202.0, 203.0, 204.0], index=idx)

    assert ArbitrageService.series_has_corporate_action_jump(
        series_a, series_b, threshold=0.15
    ) is True


def test_series_has_corporate_action_jump_quiet_series():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    series_a = pd.Series([100.0, 101.0, 100.5, 102.0, 101.5], index=idx)
    series_b = pd.Series([50.0, 50.5, 50.2, 50.8, 51.0], index=idx)

    assert ArbitrageService.series_has_corporate_action_jump(
        series_a, series_b, threshold=0.15
    ) is False
