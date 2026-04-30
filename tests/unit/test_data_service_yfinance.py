from unittest.mock import patch
import time

import pandas as pd
import pytest

from src.services.data_service import DataService


def test_extract_latest_close_handles_flat_yfinance_columns():
    df = pd.DataFrame(
        {"Close": [150.0, 151.25]},
        index=pd.date_range("2026-04-29 13:00", periods=2, freq="min"),
    )

    assert DataService._extract_latest_close(df, "MSFT") == 151.25


def test_extract_latest_close_handles_multiindex_yfinance_columns():
    df = pd.DataFrame(
        [[150.0, 149.0], [151.25, 149.75]],
        index=pd.date_range("2026-04-29 13:00", periods=2, freq="min"),
        columns=pd.MultiIndex.from_product([["Close"], ["MSFT", "AAPL"]]),
    )

    assert DataService._extract_latest_close(df, "MSFT") == 151.25


def test_get_latest_price_yfinance_retry_does_not_check_series_truthiness():
    service = DataService()
    df = pd.DataFrame(
        [[150.0], [151.25]],
        index=pd.date_range("2026-04-29 13:00", periods=2, freq="min"),
        columns=pd.MultiIndex.from_product([["Close"], ["MSFT"]]),
    )

    with patch("src.services.data_service.yf.download", return_value=df):
        with patch("time.sleep"):
            with patch("src.services.data_service.settings.DEV_MODE", False):
                assert service._get_latest_price_yfinance_with_retry(["MSFT"]) == {
                    "MSFT": 151.25
                }


@pytest.mark.asyncio
async def test_get_latest_price_async_times_out_without_blocking_loop():
    service = DataService()

    def slow_price_fetch(_tickers):
        time.sleep(0.2)
        return {"MSFT": 151.25}

    with patch.object(service, "get_latest_price", side_effect=slow_price_fetch):
        start = time.perf_counter()
        prices = await service.get_latest_price_async(["MSFT"], timeout=0.01)

    assert prices == {}
    assert time.perf_counter() - start < 0.15
