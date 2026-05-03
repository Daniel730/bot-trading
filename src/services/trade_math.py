from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN
from math import isfinite, sqrt


@dataclass(frozen=True)
class PairLegPlan:
    direction: str
    side_a: str
    side_b: str
    quantity_a: float
    quantity_b: float
    notional_a: float
    notional_b: float
    gross_notional: float
    hedge_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PairProfitPreview:
    gross_profit: float
    friction_usd: float
    net_profit: float
    profit_margin_pct: float
    expected_loss: float
    loss_margin_pct: float
    spread_capture: float
    stop_spread_move: float

    def to_dict(self) -> dict:
        return asdict(self)


def _floor(value: float, precision: int) -> float:
    quant = Decimal("1").scaleb(-precision)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_DOWN))


def _positive(value: float, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if isfinite(parsed) and parsed > 0 else fallback


def cap_pair_notional(
    desired_notional: float,
    available_cash: float,
    *,
    min_trade_value: float,
) -> float:
    capped = min(_positive(desired_notional), _positive(available_cash))
    return capped if capped >= min_trade_value else 0.0


def build_pair_legs(
    *,
    price_a: float,
    price_b: float,
    hedge_ratio: float,
    gross_notional: float,
    direction: str,
    quantity_precision: int = 6,
) -> PairLegPlan:
    price_a = _positive(price_a)
    price_b = _positive(price_b)
    hedge_ratio = _positive(hedge_ratio, 1.0)
    gross_notional = _positive(gross_notional)
    if price_a <= 0 or price_b <= 0 or hedge_ratio <= 0 or gross_notional <= 0:
        raise ValueError("price_a, price_b, hedge_ratio, and gross_notional must be positive")

    denom = price_a + (hedge_ratio * price_b)
    quantity_a = _floor(gross_notional / denom, quantity_precision)
    quantity_b = _floor(quantity_a * hedge_ratio, quantity_precision)
    notional_a = _floor(quantity_a * price_a, 2)
    notional_b = _floor(quantity_b * price_b, 2)

    side_a = "SELL" if direction == "Short-Long" else "BUY"
    side_b = "BUY" if direction == "Short-Long" else "SELL"
    return PairLegPlan(
        direction=direction,
        side_a=side_a,
        side_b=side_b,
        quantity_a=quantity_a,
        quantity_b=quantity_b,
        notional_a=notional_a,
        notional_b=notional_b,
        gross_notional=_floor(notional_a + notional_b, 2),
        hedge_ratio=hedge_ratio,
    )


def estimate_pair_profit(
    *,
    quantity_a: float,
    gross_notional: float,
    spread: float,
    z_score: float,
    innovation_variance: float,
    friction_pct: float,
    take_profit_zscore: float,
    stop_loss_zscore: float,
) -> PairProfitPreview:
    quantity_a = _positive(quantity_a)
    gross_notional = _positive(gross_notional)
    if quantity_a <= 0 or gross_notional <= 0:
        return PairProfitPreview(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    std = sqrt(_positive(innovation_variance))
    current_deviation = abs(float(spread or 0.0))
    if current_deviation <= 0 and std > 0:
        current_deviation = abs(float(z_score or 0.0)) * std

    exit_deviation = max(0.0, _positive(take_profit_zscore) * std)
    spread_capture = max(0.0, current_deviation - exit_deviation)
    gross_profit = quantity_a * spread_capture

    friction_pct = max(0.0, float(friction_pct or 0.0))
    friction_usd = gross_notional * friction_pct
    net_profit = gross_profit - friction_usd
    profit_margin_pct = (net_profit / gross_notional) * 100.0 if gross_notional > 0 else 0.0

    stop_distance_z = max(0.0, _positive(stop_loss_zscore) - abs(float(z_score or 0.0)))
    stop_spread_move = stop_distance_z * std
    expected_loss = quantity_a * stop_spread_move
    loss_margin_pct = (expected_loss / gross_notional) * 100.0 if gross_notional > 0 else 0.0

    return PairProfitPreview(
        gross_profit=_floor(gross_profit, 6),
        friction_usd=_floor(friction_usd, 6),
        net_profit=_floor(net_profit, 6),
        profit_margin_pct=profit_margin_pct,
        expected_loss=_floor(expected_loss, 6),
        loss_margin_pct=loss_margin_pct,
        spread_capture=spread_capture,
        stop_spread_move=stop_spread_move,
    )
