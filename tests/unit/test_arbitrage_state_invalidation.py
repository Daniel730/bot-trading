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
    assert saved_payload["state_fingerprint"] != "old-adjusted-history"
