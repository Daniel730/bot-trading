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


def test_alpaca_bars_to_close_frame_pivots_symbol_column():
    timestamps = pd.to_datetime(
        [
            "2026-05-13 13:00",
            "2026-05-13 13:00",
            "2026-05-13 14:00",
            "2026-05-13 14:00",
        ],
        utc=True,
    )
    bars = pd.DataFrame(
        {
            "close": [100.0, 50.0, 101.0, 51.0],
            "symbol": ["HD", "LOW", "HD", "LOW"],
        },
        index=timestamps,
    )
    bars.index.name = "timestamp"

    result = DataService._alpaca_bars_to_close_frame(bars, ["HD", "LOW"])

    assert list(result.columns) == ["HD", "LOW"]
    assert result.iloc[-1].to_dict() == {"HD": 101.0, "LOW": 51.0}


def test_alpaca_bars_to_close_frame_normalizes_crypto_symbol_index():
    timestamp = pd.Timestamp("2026-05-13 13:00", tz="UTC")
    index = pd.MultiIndex.from_tuples(
        [("BTC/USD", timestamp), ("LTC/USD", timestamp)],
        names=["symbol", "timestamp"],
    )
    bars = pd.DataFrame({"close": [80000.0, 55.0]}, index=index)

    result = DataService._alpaca_bars_to_close_frame(
        bars,
        ["BTC-USD", "LTC-USD"],
        normalize_symbol=lambda symbol: symbol.replace("/", "-"),
    )

    assert list(result.columns) == ["BTC-USD", "LTC-USD"]
    assert result.iloc[0].to_dict() == {"BTC-USD": 80000.0, "LTC-USD": 55.0}


def test_alpaca_bars_to_close_frame_does_not_mislabel_multi_ticker_without_symbol():
    bars = pd.DataFrame(
        {"close": [100.0, 101.0]},
        index=pd.date_range("2026-05-13 13:00", periods=2, freq="h", tz="UTC"),
    )

    result = DataService._alpaca_bars_to_close_frame(bars, ["HD", "LOW"])

    assert result.empty


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
         patch.object(service, "get_latest_price", side_effect=fake_batch), \
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


@pytest.mark.asyncio
async def test_get_latest_price_async_caps_large_configured_batch_size():
    service = DataService()
    tickers = [f"T{i}" for i in range(12)]
    calls = []

    def fake_batch(chunk):
        calls.append(tuple(chunk))
        return {ticker: float(idx + 1) for idx, ticker in enumerate(chunk)}

    with patch("src.services.data_service.settings.MARKET_DATA_BATCH_SIZE", 50), \
         patch("src.services.data_service.settings.MARKET_DATA_BATCH_CONCURRENCY", 3), \
         patch.object(service, "get_latest_price", side_effect=fake_batch), \
         patch("src.services.data_service.redis_service.get_price", new_callable=AsyncMock) as get_price, \
         patch("src.services.data_service.redis_service.set_price", new_callable=AsyncMock):
        get_price.return_value = None
        prices = await service.get_latest_price_async(tickers, timeout=1.0)

    assert set(prices) == set(tickers)
    assert len(calls) == 3
    assert all(len(call) <= service.LATEST_PRICE_BATCH_CAP for call in calls)


@pytest.mark.asyncio
async def test_get_bid_ask_missing_quote_does_not_fallback_to_zero_spread():
    service = DataService()

    class FakeTicker:
        info = {
            "bid": 0.0,
            "ask": 0.0,
            "currentPrice": 151.25,
            "previousClose": 150.0,
        }

    with patch("src.services.data_service.yf.Ticker", return_value=FakeTicker()):
        bid, ask = await service.get_bid_ask("MSFT")

    assert (bid, ask) == (0.0, 0.0)
