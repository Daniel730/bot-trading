import numpy as np
import pandas as pd
import pytest

from src.services.arbitrage_service import ArbitrageService


@pytest.mark.asyncio
async def test_kalman_state_invalidates_on_corporate_action(monkeypatch):
    service = ArbitrageService()
    pair_id = "AAA_BBB"
    stale_state = [99.0, 9.0]
    saved_payload = {}

    current_adjusted_history = pd.DataFrame(
        {
            "AAA": [100.0, 101.0, 102.0, 103.0],
            "BBB": [50.0, 50.5, 51.0, 51.5],
        },
        index=pd.date_range("2026-01-01", periods=4, freq="h"),
    )

    async def get_kalman_state(ticker_pair):
        assert ticker_pair == pair_id
        return {
            "x": stale_state,
            "P": [[1.0, 0.0], [0.0, 1.0]],
            "z_score": 0.0,
            "innovation_variance": 1.0,
            "state_fingerprint": "old-adjusted-history",
        }

    async def save_kalman_state(**kwargs):
        saved_payload.update(kwargs)

    monkeypatch.setattr(
        "src.services.arbitrage_service.redis_service.get_kalman_state",
        get_kalman_state,
    )
    monkeypatch.setattr(
        "src.services.arbitrage_service.redis_service.save_kalman_state",
        save_kalman_state,
    )

    kf = await service.get_or_create_filter(pair_id, prewarm_data=current_adjusted_history)

    assert not np.allclose(kf.state, stale_state)

    await service.save_filter_state(pair_id, kf, z_score=0.0)

    assert saved_payload["state_fingerprint"]
    assert saved_payload["state_fingerprint"].startswith("history-v2:")
    assert saved_payload["state_fingerprint"] != "old-adjusted-history"


def test_series_has_corporate_action_jump_detects_single_bar_spike():
    quiet = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    spiked = pd.Series([50.0, 50.5, 51.0, 80.0, 80.5])  # ~57% jump
    assert ArbitrageService.series_has_corporate_action_jump(
        quiet, spiked, threshold=0.15
    )
    assert not ArbitrageService.series_has_corporate_action_jump(
        quiet, quiet, threshold=0.15
    )


@pytest.mark.asyncio
async def test_invalidate_pair_state_clears_filter_and_redis(monkeypatch):
    service = ArbitrageService()
    service.filters["AAA_BBB"] = object()
    service.filter_fingerprints["AAA_BBB"] = "fp"
    deleted = []

    async def delete_kalman_state(pair_id):
        deleted.append(pair_id)

    monkeypatch.setattr(
        "src.services.arbitrage_service.redis_service.delete_kalman_state",
        delete_kalman_state,
    )
    await service.invalidate_pair_state("AAA_BBB", reason="corporate_action_jump")
    assert "AAA_BBB" not in service.filters
    assert "AAA_BBB" not in service.filter_fingerprints
    assert deleted == ["AAA_BBB"]


def test_build_state_fingerprint_is_stable_and_sensitive_to_rescales():
    """Streaming fingerprint must stay stable for identical history and change on rescale."""
    base = pd.DataFrame(
        {
            "AAA": [100.0, 101.0, 102.0, 103.0],
            "BBB": [50.0, 50.5, 51.0, 51.5],
        },
        index=pd.date_range("2026-01-01", periods=4, freq="h"),
    )
    fp1 = ArbitrageService.build_state_fingerprint("AAA_BBB", base)
    fp2 = ArbitrageService.build_state_fingerprint("AAA_BBB", base.copy())
    assert fp1 == fp2
    assert fp1.startswith("history-v2:")

    rescaled = base.copy()
    rescaled["AAA"] = rescaled["AAA"] * 0.5  # corporate-action style adjust
    fp3 = ArbitrageService.build_state_fingerprint("AAA_BBB", rescaled)
    assert fp3 != fp1
    assert fp3.startswith("history-v2:")
