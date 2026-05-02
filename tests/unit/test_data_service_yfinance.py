from unittest.mock import AsyncMock, patch
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


def test_extract_latest_close_returns_none_for_missing_batch_ticker():
    df = pd.DataFrame(
        [[150.0, 149.0], [151.25, 149.75]],
        index=pd.date_range("2026-04-29 13:00", periods=2, freq="min"),
        columns=pd.MultiIndex.from_product([["Close"], ["MSFT", "AAPL"]]),
    )

    assert (
        DataService._extract_latest_close(
            df,
            "DUK",
            allow_single_column_fallback=False,
        )
        is None
    )


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


@pytest.mark.asyncio
async def test_get_latest_price_async_chunks_large_universe():
    service = DataService()
    tickers = ["AAPL", "MSFT", "DUK", "SO", "XOM"]
    calls = []

    def fake_batch(chunk):
        calls.append(tuple(chunk))
        return {ticker: float(idx + 1) for idx, ticker in enumerate(chunk)}

    with patch("src.services.data_service.settings.MARKET_DATA_BATCH_SIZE", 2), \
         patch("src.services.data_service.settings.MARKET_DATA_BATCH_CONCURRENCY", 2), \
         patch.object(service, "_get_latest_price_yfinance_batch", side_effect=fake_batch), \
         patch("src.services.data_service.redis_service.get_price", new_callable=AsyncMock) as get_price, \
         patch("src.services.data_service.redis_service.set_price", new_callable=AsyncMock):
        get_price.return_value = None
        prices = await service.get_latest_price_async(tickers, timeout=1.0)

    assert prices == {
        "AAPL": 1.0,
        "MSFT": 2.0,
        "DUK": 1.0,
        "SO": 2.0,
        "XOM": 1.0,
    }
    assert set(calls) == {("AAPL", "MSFT"), ("DUK", "SO"), ("XOM",)}


# ---------------------------------------------------------------------------
# _download_yfinance – simplified behaviour (PR change: no empty-result
# logging; TypeError with "timeout" is retried without the kwarg)
# ---------------------------------------------------------------------------

class TestDownloadYfinance:
    def test_returns_yf_download_result_directly(self):
        """PR simplified _download_yfinance to return yf.download result directly."""
        service = DataService()
        df = pd.DataFrame({"Close": [100.0]})
        with patch("src.services.data_service.yf.download", return_value=df) as mock_dl:
            result = service._download_yfinance("AAPL", period="1d")
        assert result is df
        mock_dl.assert_called_once()

    def test_default_timeout_is_applied(self):
        """_download_yfinance should inject the default timeout when not provided."""
        service = DataService()
        with patch("src.services.data_service.yf.download", return_value=pd.DataFrame()) as mock_dl, \
             patch("src.services.data_service.settings.MARKET_DATA_TIMEOUT_SECONDS", 7.5):
            service._download_yfinance("AAPL", period="1d")
        _, kwargs = mock_dl.call_args
        assert kwargs.get("timeout") == 7.5

    def test_explicit_timeout_is_not_overridden(self):
        """Caller-supplied timeout must not be replaced by the default."""
        service = DataService()
        with patch("src.services.data_service.yf.download", return_value=pd.DataFrame()) as mock_dl:
            service._download_yfinance("AAPL", timeout=99.0)
        _, kwargs = mock_dl.call_args
        assert kwargs["timeout"] == 99.0

    def test_type_error_with_timeout_in_message_retries_without_timeout(self):
        """If yf.download raises TypeError mentioning 'timeout', retry without it."""
        service = DataService()
        df_success = pd.DataFrame({"Close": [150.0]})
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if "timeout" in kwargs:
                raise TypeError("unexpected keyword argument 'timeout'")
            return df_success

        with patch("src.services.data_service.yf.download", side_effect=side_effect):
            result = service._download_yfinance("AAPL")

        assert call_count["n"] == 2
        assert result is df_success

    def test_type_error_without_timeout_in_message_propagates(self):
        """TypeError unrelated to 'timeout' should be re-raised."""
        service = DataService()
        with patch("src.services.data_service.yf.download", side_effect=TypeError("bad argument X")):
            with pytest.raises(TypeError, match="bad argument X"):
                service._download_yfinance("AAPL")

    def test_empty_dataframe_returned_without_error(self):
        """PR removed the empty-result warning log; empty DataFrame is returned as-is."""
        service = DataService()
        empty_df = pd.DataFrame()
        with patch("src.services.data_service.yf.download", return_value=empty_df):
            result = service._download_yfinance("DELISTED")
        assert result.empty


# ---------------------------------------------------------------------------
# _dedupe_tickers – static method (PR removed docstring but logic unchanged)
# ---------------------------------------------------------------------------

class TestDedupeTickers:
    def test_removes_duplicates_preserving_order(self):
        result = DataService._dedupe_tickers(["AAPL", "MSFT", "AAPL", "DUK"])
        assert result == ["AAPL", "MSFT", "DUK"]

    def test_removes_empty_string_falsy_values(self):
        result = DataService._dedupe_tickers(["AAPL", "", "MSFT", None])
        assert result == ["AAPL", "MSFT"]

    def test_empty_list_returns_empty(self):
        assert DataService._dedupe_tickers([]) == []

    def test_single_element_returns_single(self):
        assert DataService._dedupe_tickers(["AAPL"]) == ["AAPL"]

    def test_all_duplicates_returns_one(self):
        assert DataService._dedupe_tickers(["X", "X", "X"]) == ["X"]

    def test_preserves_first_occurrence_order(self):
        result = DataService._dedupe_tickers(["C", "A", "B", "A", "C"])
        assert result == ["C", "A", "B"]


# ---------------------------------------------------------------------------
# _get_latest_price_yfinance_with_retry – raises ValueError when no prices
# (PR changed: previously returned empty dict, now raises ValueError)
# ---------------------------------------------------------------------------

def test_get_latest_price_yfinance_retry_raises_value_error_on_empty_response():
    """
    PR changed: when _get_latest_price_yfinance_with_retry finds no valid prices
    it now raises ValueError instead of returning an empty dict.
    """
    service = DataService()
    # Return a completely empty DataFrame so no prices can be extracted.
    empty_df = pd.DataFrame()

    with patch("src.services.data_service.yf.download", return_value=empty_df), \
         patch("time.sleep"):
        with pytest.raises(ValueError, match="No valid prices found"):
            service._get_latest_price_yfinance_with_retry(["UNKNOWN_TICKER"])
