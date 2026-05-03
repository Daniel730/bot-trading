import pytest

from src.services.trade_math import build_pair_legs


def test_fractional_pair_quantities_keep_six_decimal_precision():
    legs = build_pair_legs(
        price_a=173.50,
        price_b=95.25,
        hedge_ratio=1.35,
        gross_notional=1000.0,
        direction="Long-Short",
    )

    assert legs.side_a == "BUY"
    assert legs.side_b == "SELL"
    assert legs.quantity_a == pytest.approx(3.311765)
    assert legs.quantity_b == pytest.approx(4.470382)
    assert legs.gross_notional <= 1000.0


def test_pair_leg_sizing_rejects_zero_budget():
    with pytest.raises(ValueError):
        build_pair_legs(
            price_a=100.0,
            price_b=100.0,
            hedge_ratio=1.0,
            gross_notional=0.0,
            direction="Long-Short",
        )
