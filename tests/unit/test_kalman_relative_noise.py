"""Tests for price-relative Kalman measurement noise (z-score scale invariance).

The Kalman filter runs on raw price levels. With a fixed absolute measurement
variance R, the innovation variance collapses for high-priced assets (e.g. BTC
~ $60k), so a normal fractional price move is reported as a huge z-score and the
pair is permanently quarantined. Scaling the measurement variance by
(r_relative * price_a)^2 keeps z-scores dimensionless across price scales.
"""
import numpy as np

from src.services.kalman_service import KalmanFilter


def _synthetic_pair(scale: float, n: int = 800, seed: int = 7):
    """Cointegrated pair whose spread noise is a fixed *fraction* of price.

    Returns (price_a, price_b) with true beta = 2.0. ``scale`` multiplies the
    absolute price level (e.g. scale=600 -> BTC-like magnitudes) without changing
    the relative dynamics, so a correct z-score should be scale-invariant.
    """
    rng = np.random.default_rng(seed)
    base = 100.0 * scale
    steps = rng.normal(0, 0.005, n)  # 0.5% relative random-walk increments
    price_b = base * np.exp(np.cumsum(steps))
    true_beta = 2.0
    rel_noise = rng.normal(0, 0.01, n)  # 1% relative measurement noise
    price_a = true_beta * price_b * (1.0 + rel_noise)
    return price_a, price_b


def _run(price_a, price_b, r_relative):
    kf = KalmanFilter(delta=1e-5, r=1e-3, r_relative=r_relative)
    zs = []
    for a, b in zip(price_a, price_b):
        _, _, z, _ = kf.update(float(a), float(b))
        zs.append(z)
    return kf, np.array(zs[100:])  # drop warmup


def test_effective_r_scales_with_price():
    kf = KalmanFilter(r=1e-3, r_relative=0.02)
    # R + (0.02 * price)^2
    assert abs(kf._effective_r(0.0) - 1e-3) < 1e-12
    assert abs(kf._effective_r(100.0) - (1e-3 + (0.02 * 100.0) ** 2)) < 1e-9
    assert abs(kf._effective_r(60000.0) - (1e-3 + (0.02 * 60000.0) ** 2)) < 1e-3


def test_relative_noise_defaults_to_legacy_behavior():
    """The default (r_relative=0) must be byte-for-byte identical to the legacy filter."""
    default_kf = KalmanFilter(delta=1e-5, r=1e-3)
    explicit_kf = KalmanFilter(delta=1e-5, r=1e-3, r_relative=0.0)

    assert default_kf.r_relative == 0.0
    assert default_kf._effective_r(123.45) == default_kf.R

    prices = [(150.0, 100.0), (151.0, 100.5), (149.0, 99.0), (152.5, 101.0)]
    for pa, pb in prices:
        _, iv_d, z_d, s_d = default_kf.update(pa, pb)
        _, iv_e, z_e, s_e = explicit_kf.update(pa, pb)
        assert iv_d == iv_e
        assert z_d == z_e
        assert s_d == s_e


def test_zscore_is_scale_invariant_with_relative_noise():
    """With relative noise, z-score distribution is comparable across price scales."""
    lo_a, lo_b = _synthetic_pair(scale=1.0)      # ~$100-200
    hi_a, hi_b = _synthetic_pair(scale=600.0)    # ~$60k-120k (BTC-like)

    _, z_lo = _run(lo_a, lo_b, r_relative=0.02)
    kf_hi, z_hi = _run(hi_a, hi_b, r_relative=0.02)

    # Both should be well-calibrated (std of order 1, never near the |z|>100 guard).
    assert z_lo.std() < 5.0
    assert z_hi.std() < 5.0
    assert np.abs(z_hi).max() < 50.0
    # Scale invariance: the two z-score spreads are within a small factor.
    assert 0.25 < (z_hi.std() / z_lo.std()) < 4.0
    # Beta still recovers the true hedge ratio (~2.0) regardless of scale.
    assert abs(kf_hi.state[1] - 2.0) < 0.5


def test_relative_noise_prevents_innovation_variance_collapse():
    """After the filter's covariance converges (P shrinks), absolute-only R lets
    the innovation variance collapse for high-priced assets, so tiny fractional
    residuals become huge z-scores. Relative noise keeps a price-proportional
    floor on the innovation std, bounding the z-score.
    """
    hi_a, hi_b = _synthetic_pair(scale=600.0)  # BTC-like magnitudes

    kf_abs, _ = _run(hi_a, hi_b, r_relative=0.0)
    kf_rel, _ = _run(hi_a, hi_b, r_relative=0.02)

    price_a = float(hi_a[-1])
    # Relative mode keeps the innovation std at a sane fraction of price...
    rel_std = np.sqrt(kf_rel.innovation_variance)
    assert rel_std >= 0.01 * price_a
    # ...whereas the absolute-only innovation std is a negligible fraction of price,
    # which is exactly what inflates z-scores for expensive assets.
    abs_std = np.sqrt(kf_abs.innovation_variance)
    assert abs_std < rel_std
