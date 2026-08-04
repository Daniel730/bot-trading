"""Unit tests for crypto vs equity abs-hedge ceilings."""

from src.services.pair_discovery_helpers import (
    is_hedge_ratio_sane,
    max_abs_hedge_limit,
    select_rotation_actions,
)
from src.config import settings


def test_max_abs_hedge_limit_keeps_equity_tight():
    assert max_abs_hedge_limit("AAPL", "MSFT") == float(settings.PAIR_DISCOVERY_MAX_ABS_HEDGE)
    assert max_abs_hedge_limit("AAPL", "MSFT") == 25.0


def test_max_abs_hedge_limit_raises_for_crypto_pairs():
    crypto_cap = max_abs_hedge_limit("BTC-USD", "ETH-USD")
    assert crypto_cap == float(settings.PAIR_DISCOVERY_MAX_ABS_HEDGE_CRYPTO)
    assert crypto_cap > float(settings.PAIR_DISCOVERY_MAX_ABS_HEDGE)
    # Observed BTC/ETH Kalman beta (~34) must be admitted for crypto.
    assert is_hedge_ratio_sane(34.0, max_abs_hedge=crypto_cap)
    assert not is_hedge_ratio_sane(34.0, max_abs_hedge=25.0)


def test_equity_hedge_still_rejects_extreme_ratios():
    assert not is_hedge_ratio_sane(
        34.0,
        max_abs_hedge=max_abs_hedge_limit("KO", "PEP"),
    )


def test_rotation_uses_crypto_cap_when_max_abs_hedge_is_none():
    actions = select_rotation_actions(
        active_pairs=[
            {
                "id": "BTC-USD_ETH-USD",
                "hedge_ratio": 34.0,
                "is_cointegrated": True,
            }
        ],
        candidates=[],
        max_active_pairs=4,
        max_abs_hedge=None,
        min_abs_hedge=0.05,
    )
    assert "BTC-USD_ETH-USD" not in actions["to_bench"]


def test_rotation_benches_equity_extreme_when_max_abs_hedge_is_none():
    actions = select_rotation_actions(
        active_pairs=[
            {
                "id": "AAPL_MSFT",
                "hedge_ratio": 34.0,
                "is_cointegrated": True,
            }
        ],
        candidates=[],
        max_active_pairs=4,
        max_abs_hedge=None,
        min_abs_hedge=0.05,
    )
    assert "AAPL_MSFT" in actions["to_bench"]
