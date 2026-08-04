import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Thin local venvs may lack edgartools / google generativeai; stub before SEC imports.
sys.modules.setdefault("edgar", SimpleNamespace(set_identity=lambda *_a, **_k: None, Company=object))
sys.modules.setdefault("google.generativeai", MagicMock())

from src.config import settings
from src.daemons.sec_fundamental_worker import (
    SECFundamentalWorker,
    _is_crypto_ticker,
    _score_is_fresh,
)
from src.models.arbitrage_models import FundamentalSignal
from src.services.sec_service import SECUnreachableException


def test_is_crypto_ticker_filters_usd_pairs():
    assert _is_crypto_ticker("BTC-USD") is True
    assert _is_crypto_ticker("AAPL") is False


def test_score_is_fresh_requires_wall_clock_edgar_score():
    assert _score_is_fresh(None, max_age_seconds=3600) is False
    assert _score_is_fresh({"score": 80, "last_updated": 12.0}, max_age_seconds=3600) is False
    assert _score_is_fresh(
        {"score": 80, "source": "fallback", "last_updated": time.time()},
        max_age_seconds=3600,
    ) is False
    assert _score_is_fresh(
        {"score": 80, "source": "edgar", "available": True, "last_updated": time.time()},
        max_age_seconds=3600,
    ) is True


@pytest.mark.asyncio
async def test_process_ticker_skips_fresh_cache(monkeypatch):
    monkeypatch.setattr(settings, "SEC_WORKER_REFRESH_SECONDS", 43200)
    worker = SECFundamentalWorker()
    worker.analyst = MagicMock()
    cached = {
        "score": 77,
        "source": "edgar",
        "available": True,
        "last_updated": time.time(),
    }

    with patch(
        "src.daemons.sec_fundamental_worker.redis_service.get_fundamental_score",
        new_callable=AsyncMock,
        return_value=cached,
    ), patch.object(
        worker,
        "_analyze_and_cache",
        new_callable=AsyncMock,
    ) as analyze:
        await worker.process_ticker("AAPL")

    analyze.assert_not_awaited()
    assert worker._consecutive_unreachable == 0


@pytest.mark.asyncio
async def test_process_ticker_does_not_cache_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "SEC_WORKER_UNREACHABLE_THRESHOLD", 3)
    worker = SECFundamentalWorker()

    with patch(
        "src.daemons.sec_fundamental_worker.redis_service.get_fundamental_score",
        new_callable=AsyncMock,
        return_value=None,
    ), patch.object(
        worker,
        "_analyze_and_cache",
        new_callable=AsyncMock,
        side_effect=SECUnreachableException("timeout"),
    ), patch(
        "src.daemons.sec_fundamental_worker.redis_service.set_fundamental_score",
        new_callable=AsyncMock,
    ) as set_score:
        await worker.process_ticker("MSFT")

    set_score.assert_not_awaited()
    assert worker._consecutive_unreachable == 1


@pytest.mark.asyncio
async def test_analyze_and_cache_skips_fallback_signal():
    worker = SECFundamentalWorker()
    worker.analyst = MagicMock()
    worker.analyst.analyze_ticker = AsyncMock(
        return_value=FundamentalSignal(
            signal_id="bg",
            ticker="ZZZ",
            structural_integrity_score=50,
            prosecutor_argument="N/A - No SEC filings found.",
            defender_argument="N/A - No SEC filings found.",
            final_reasoning="Fallback to default (50) due to missing SEC data.",
        )
    )

    with patch(
        "src.daemons.sec_fundamental_worker.redis_service.set_fundamental_score",
        new_callable=AsyncMock,
    ) as set_score:
        # Bypass tenacity retry wrapper by calling the underlying function once.
        await worker._analyze_and_cache.__wrapped__(worker, "ZZZ")

    set_score.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyze_and_cache_writes_edgar_metadata():
    worker = SECFundamentalWorker()
    worker.analyst = MagicMock()
    worker.analyst.analyze_ticker = AsyncMock(
        return_value=FundamentalSignal(
            signal_id="bg",
            ticker="AAPL",
            structural_integrity_score=82,
            prosecutor_argument="risk",
            defender_argument="ok",
            final_reasoning="Solid structure.",
        )
    )

    with patch(
        "src.daemons.sec_fundamental_worker.redis_service.set_fundamental_score",
        new_callable=AsyncMock,
    ) as set_score:
        await worker._analyze_and_cache.__wrapped__(worker, "AAPL")

    set_score.assert_awaited_once()
    ticker, payload = set_score.await_args.args
    assert ticker == "AAPL"
    assert payload["score"] == 82
    assert payload["source"] == "edgar"
    assert payload["available"] is True
    assert payload["last_updated"] > 1_000_000_000
