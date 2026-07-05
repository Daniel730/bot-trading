from unittest.mock import AsyncMock

import pandas as pd
import pytest

from src.services.market_regime_service import MarketRegimeService
from src.services.persistence_service import MarketRegime


@pytest.mark.asyncio
async def test_market_regime_reuses_recent_classification(monkeypatch):
    prices = pd.DataFrame(
        {"SPY": [100.0] * 60},
        index=pd.date_range("2026-01-01", periods=60),
    )

    class FakeDataService:
        def __init__(self):
            self.calls = 0

        def get_historical_data(self, *_args, **_kwargs):
            self.calls += 1
            return prices

    fake_data_service = FakeDataService()
    entropy = AsyncMock(return_value=0.1)
    log_market_regime = AsyncMock()

    monkeypatch.setattr(
        "src.services.market_regime_service.data_service",
        fake_data_service,
    )
    monkeypatch.setattr(
        "src.services.market_regime_service.volatility_service.get_l2_entropy",
        entropy,
    )
    monkeypatch.setattr(
        "src.services.market_regime_service.persistence_service.log_market_regime",
        log_market_regime,
    )

    service = MarketRegimeService()

    first = await service.classify_current_regime("SPY")
    second = await service.classify_current_regime("SPY")

    assert first == second
    assert first["regime"] == MarketRegime.SIDEWAYS
    assert fake_data_service.calls == 1
    entropy.assert_awaited_once_with("SPY")
    log_market_regime.assert_awaited_once()
