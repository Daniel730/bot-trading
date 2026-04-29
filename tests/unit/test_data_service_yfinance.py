from unittest.mock import patch

import pandas as pd

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
