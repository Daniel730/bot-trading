"""Spec 037: tests for the adaptive-Q session boundary handling.

These tests verify the new ``inflate_q`` API, which is the safer replacement
for the legacy one-shot ``bump_uncertainty(P)`` at session open.
"""
import numpy as np

from src.services.kalman_service import KalmanFilter


def test_inflate_q_sets_countdown_and_factor():
    """Calling inflate_q stages the inflation but leaves Q untouched until update()."""
    kf = KalmanFilter(delta=1e-5, r=1e-3)
    base = kf.Q_base.copy()
    kf.inflate_q(factor=5.0, n_bars=10)
    # Until update() runs, Q should still be the base.
    assert np.allclose(kf.Q, base)
    assert kf._q_inflation_remaining == 10
    assert kf._q_inflation_factor == 5.0


def test_inflate_q_decays_linearly_to_base():
    """Across n_bars updates, Q should decay smoothly back to Q_base."""
    kf = KalmanFilter(delta=1e-5, r=1e-3)
    base = kf.Q_base.copy()
    n_bars = 5
    factor = 5.0
    kf.inflate_q(factor=factor, n_bars=n_bars)

    seen_scales = []
    for _ in range(n_bars):
        kf.update(100.0, 100.0)
        # Q after update reflects the value used in that step.
        scale = kf.Q[0, 0] / base[0, 0]
        seen_scales.append(scale)

    # First scale must be the full factor; last must be 1.0 (base restored).
    assert seen_scales[0] == factor
    assert abs(seen_scales[-1] - 1.0) < 1e-9
    # Monotonic decay.
    for a, b in zip(seen_scales, seen_scales[1:]):
        assert a >= b - 1e-9


def test_inflate_q_reverts_after_countdown():
    """One extra update past the countdown should put Q back at Q_base."""
    kf = KalmanFilter(delta=1e-5, r=1e-3)
    base = kf.Q_base.copy()
    kf.inflate_q(factor=10.0, n_bars=3)
    for _ in range(3):
        kf.update(100.0, 100.0)
    kf.update(100.0, 100.0)
    assert np.allclose(kf.Q, base)
    assert kf._q_inflation_remaining == 0


def test_inflate_q_preserves_state_vector():
    """Unlike bump_uncertainty, inflate_q must NOT touch the learned state."""
    kf = KalmanFilter(delta=1e-5, r=1e-3)
    # Run enough updates to give the filter a real state.
    np.random.seed(0)
    for _ in range(100):
        kf.update(150.0, 100.0)
    state_before = kf.state.copy()
    p_before = kf.P.copy()
    kf.inflate_q(factor=5.0, n_bars=10)
    # State and P unchanged immediately after staging.
    assert np.allclose(kf.state, state_before)
    assert np.allclose(kf.P, p_before)


def test_inflate_q_speeds_convergence_through_a_gap():
    """A filter with Q-inflation should track a beta jump faster than baseline."""
    np.random.seed(7)
    # Pre-converge two filters identically on beta=1.0.
    kf_base = KalmanFilter(delta=1e-5, r=1e-3)
    kf_inflated = KalmanFilter(delta=1e-5, r=1e-3)
    for _ in range(200):
        x = 100.0 + np.random.randn() * 0.05
        kf_base.update(x, x)
        kf_inflated.update(x, x)

    # Stage Q inflation only on one filter.
    kf_inflated.inflate_q(factor=20.0, n_bars=8)

    # Now hit both with a clean beta=2.0 regime.
    n_post = 8
    distances_base = []
    distances_inflated = []
    for _ in range(n_post):
        pb = 100.0 + np.random.randn() * 0.05
        pa = 2.0 * pb + np.random.randn() * 0.05
        kf_base.update(pa, pb)
        kf_inflated.update(pa, pb)
        distances_base.append(abs(kf_base.state[1] - 2.0))
        distances_inflated.append(abs(kf_inflated.state[1] - 2.0))

    # The inflated filter must be closer to the true beta at the end.
    assert distances_inflated[-1] < distances_base[-1]


def test_inflate_q_idempotent_call_resets_countdown():
    """Calling inflate_q again before the previous run finishes restarts the run."""
    kf = KalmanFilter(delta=1e-5, r=1e-3)
    kf.inflate_q(factor=2.0, n_bars=10)
    kf.update(100.0, 100.0)
    kf.update(100.0, 100.0)
    # Two bars consumed.
    assert kf._q_inflation_remaining == 8
    # Re-stage with new params.
    kf.inflate_q(factor=5.0, n_bars=4)
    assert kf._q_inflation_remaining == 4
    assert kf._q_inflation_factor == 5.0


def test_inflate_q_ignores_bad_args():
    """factor < 1 or n_bars < 1 must be no-ops."""
    kf = KalmanFilter(delta=1e-5, r=1e-3)
    base = kf.Q_base.copy()
    kf.inflate_q(factor=0.5, n_bars=5)
    kf.inflate_q(factor=5.0, n_bars=0)
    assert kf._q_inflation_remaining == 0
    assert np.allclose(kf.Q, base)


def test_get_state_dict_persists_q_base_not_inflated():
    """Serialised Q must be Q_base — otherwise inflation persists across restarts."""
    kf = KalmanFilter(delta=1e-5, r=1e-3)
    base = np.array(kf.Q_base.tolist())
    kf.inflate_q(factor=10.0, n_bars=5)
    kf.update(100.0, 100.0)  # Q is now 10x base.
    snap = kf.get_state_dict()
    assert np.allclose(np.array(snap["q_matrix"]), base)
