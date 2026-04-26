"""Spec 037: rolling-window cointegration stability tests.

Single-shot ADF can flatter a pair that was coíntegrated for half the period
and decoupled for the other half. The rolling check is what protects us.
"""
import numpy as np
import pandas as pd

from src.services.arbitrage_service import ArbitrageService


def _ar1_random_walk(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.standard_normal(n)) + 100.0


def test_stably_cointegrated_pair_passes():
    """Two series with a constant linear relationship and Gaussian noise."""
    np.random.seed(1)
    n = 400
    s2 = _ar1_random_walk(n, seed=1)
    s1 = 1.5 * s2 + 5.0 + np.random.randn(n) * 0.5
    res = ArbitrageService.check_rolling_cointegration(
        pd.Series(s1), pd.Series(s2), window=60, step=10, min_pass_rate=0.7
    )
    assert res["stable"] is True
    assert res["pass_rate"] >= 0.7
    assert res["windows_total"] > 0
    assert res["median_pvalue"] < 0.05


def test_random_walk_pair_fails():
    """Two independent random walks: the spread is non-stationary; rolling fails."""
    s1 = _ar1_random_walk(400, seed=11)
    s2 = _ar1_random_walk(400, seed=22)
    res = ArbitrageService.check_rolling_cointegration(
        pd.Series(s1), pd.Series(s2), window=60, step=10, min_pass_rate=0.7
    )
    assert res["stable"] is False
    assert res["pass_rate"] < 0.7


def test_regime_shifting_pair_fails():
    """Pair coíntegrated in the first half, decoupled in the second half.

    Static ADF on the full sample may still pass because half the data has a
    stationary spread. Rolling stability must catch this and reject.
    """
    np.random.seed(3)
    n_half = 200
    base = _ar1_random_walk(n_half, seed=3)
    s2_first = base
    s1_first = 1.5 * base + np.random.randn(n_half) * 0.5
    # Second half: s1 decouples and walks on its own.
    s2_second = _ar1_random_walk(n_half, seed=4)
    s1_second = _ar1_random_walk(n_half, seed=5)
    s1 = np.concatenate([s1_first, s1_second])
    s2 = np.concatenate([s2_first, s2_second])

    res = ArbitrageService.check_rolling_cointegration(
        pd.Series(s1), pd.Series(s2), window=60, step=10, min_pass_rate=0.7
    )
    # A regime-shifting pair must fail the stability test.
    assert res["stable"] is False


def test_too_short_series_returns_empty():
    """Short series should return the empty stability dict, not crash."""
    s1 = pd.Series([1.0, 2.0, 3.0, 4.0])
    s2 = pd.Series([1.0, 2.0, 3.0, 4.0])
    res = ArbitrageService.check_rolling_cointegration(s1, s2, window=60)
    assert res["stable"] is False
    assert res["windows_total"] == 0
    assert res["pass_rate"] == 0.0


def test_step_argument_changes_window_count():
    """Reducing step yields more rolling windows."""
    np.random.seed(2)
    n = 300
    s2 = _ar1_random_walk(n, seed=7)
    s1 = 2.0 * s2 + np.random.randn(n) * 0.5

    res_step10 = ArbitrageService.check_rolling_cointegration(
        pd.Series(s1), pd.Series(s2), window=60, step=10
    )
    res_step5 = ArbitrageService.check_rolling_cointegration(
        pd.Series(s1), pd.Series(s2), window=60, step=5
    )
    assert res_step5["windows_total"] >= res_step10["windows_total"]
