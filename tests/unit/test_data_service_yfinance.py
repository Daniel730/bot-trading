from unittest.mock import AsyncMock, patch
import importlib
import threading
import time

import pandas as pd
import pytest

from src.services.data_service import DataService


def test_module_import_does_not_initialize_external_market_clients():
    import src.services.data_service as module

    with patch(
        "polygon.RESTClient",
        side_effect=AssertionError("import must not initialize Polygon client"),
    ) as polygon_client, patch(
        "alpaca_trade_api.REST",
        side_effect=AssertionError("import must not initialize Alpaca client"),
    ) as alpaca_client:
        reloaded = importlib.reload(module)

    importlib.reload(reloaded)
    polygon_client.assert_not_called()
    alpaca_client.assert_not_called()


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
async def test_get_latest_price_async_serializes_crypto_chunks():
    service = DataService()
    tickers = ["BTC-USD", "ETH-USD", "LTC-USD", "BCH-USD"]
    active_calls = 0
    max_active_calls = 0
    guard = threading.Lock()

    def fake_batch(chunk):
        nonlocal active_calls, max_active_calls
        with guard:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        time.sleep(0.05)
        with guard:
            active_calls -= 1
        return {ticker: float(idx + 1) for idx, ticker in enumerate(chunk)}

    with patch("src.services.data_service.settings.MARKET_DATA_BATCH_SIZE", 2), \
         patch("src.services.data_service.settings.MARKET_DATA_BATCH_CONCURRENCY", 2), \
         patch.object(service, "get_latest_price", side_effect=fake_batch), \
         patch("src.services.data_service.redis_service.get_price", new_callable=AsyncMock) as get_price, \
         patch("src.services.data_service.redis_service.set_price", new_callable=AsyncMock):
        get_price.return_value = None
        prices = await service.get_latest_price_async(tickers, timeout=1.0)

    assert set(prices) == set(tickers)
    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_get_latest_price_async_cached_prices_clear_stale_alpaca_metadata():
    service = DataService()
    tickers = ["BTC-USD", "ETH-USD", "LTC-USD", "BCH-USD", "SOL-USD", "AVAX-USD"]
    cached_prices = {
        "BTC-USD": 90_000.0,
        "ETH-USD": 3_000.0,
        "LTC-USD": 85.0,
        "BCH-USD": 420.0,
        "SOL-USD": 160.0,
        "AVAX-USD": 25.0,
    }
    service.last_price_sources.update(
        {ticker: "alpaca_crypto_quote_mid" for ticker in tickers}
    )
    service.last_price_timestamps.update(
        {ticker: "2026-05-20T12:01:00+00:00" for ticker in tickers}
    )

    async def fake_cached_price(ticker):
        return cached_prices[ticker]

    with patch(
        "src.services.data_service.redis_service.get_price",
        new_callable=AsyncMock,
        side_effect=fake_cached_price,
    ), patch.object(
        service,
        "get_latest_price",
        side_effect=AssertionError("fresh fetch should not run for cached prices"),
    ):
        prices = await service.get_latest_price_async(tickers, timeout=1.0)

    assert prices == cached_prices
    for ticker in tickers:
        assert service.last_price_sources[ticker] == "redis"
        assert ticker not in service.last_price_timestamps


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


@pytest.mark.asyncio
async def test_get_bid_ask_uses_alpaca_crypto_snapshot_when_yfinance_quote_is_zero():
    service = DataService()

    class FakeTicker:
        info = {
            "bid": 0.0,
            "ask": 0.0,
        }

    class FakeQuote:
        bp = 90000.0
        ap = 90010.0

    class FakeSnapshot:
        latest_quote = FakeQuote()

    with patch("src.services.data_service.yf.Ticker", return_value=FakeTicker()), \
         patch.object(
             service.alpaca_client,
             "get_crypto_snapshots",
             return_value={"BTC/USD": FakeSnapshot()},
         ):
        bid, ask = await service.get_bid_ask("BTC-USD")

    assert (bid, ask) == (90000.0, 90010.0)


def test_get_latest_price_crypto_snapshot_does_not_require_exchange_kwarg():
    service = DataService()

    class FakeTrade:
        p = 90000.0

    class FakeSnapshot:
        latest_trade = FakeTrade()

    def fake_get_crypto_snapshots(symbols, **kwargs):
        if kwargs:
            raise TypeError("REST.get_crypto_snapshots() got an unexpected keyword argument 'exchange'")
        return {"BTC/USD": FakeSnapshot()}

    with patch("src.services.data_service.redis_service.get_price", return_value=None), \
         patch.object(service, "_update_redis_cache"), \
         patch.object(
             service.alpaca_client,
             "get_crypto_snapshots",
             side_effect=fake_get_crypto_snapshots,
         ), \
         patch.object(service, "_get_latest_price_polygon", return_value={}), \
         patch.object(
             service,
             "_get_latest_price_yfinance_with_retry",
             return_value={"BTC-USD": 1.0},
         ) as yfinance_fallback:
        prices = service.get_latest_price(["BTC-USD"])

    assert prices == {"BTC-USD": 90000.0}
    yfinance_fallback.assert_not_called()


def test_get_latest_price_uses_newer_crypto_quote_mid_when_trade_is_stale():
    service = DataService()

    class FakeTrade:
        p = 90000.0
        t = pd.Timestamp("2026-05-20T12:00:00Z")

    class FakeQuote:
        bp = 90100.0
        ap = 90110.0
        t = pd.Timestamp("2026-05-20T12:01:00Z")

    class FakeSnapshot:
        latest_trade = FakeTrade()
        latest_quote = FakeQuote()

    with patch("src.services.data_service.redis_service.get_price", return_value=None), \
         patch.object(service, "_update_redis_cache"), \
         patch.object(
             service.alpaca_client,
             "get_crypto_snapshots",
             return_value={"BTC/USD": FakeSnapshot()},
         ), \
         patch.object(service, "_get_latest_price_polygon", return_value={}), \
         patch.object(
             service,
             "_get_latest_price_yfinance_with_retry",
             return_value={"BTC-USD": 1.0},
         ) as yfinance_fallback:
        prices = service.get_latest_price(["BTC-USD"])

    assert prices == {"BTC-USD": 90105.0}
    assert service.last_price_sources["BTC-USD"] == "alpaca_crypto_quote_mid"
    assert service.last_price_timestamps["BTC-USD"] == "2026-05-20T12:01:00+00:00"
    yfinance_fallback.assert_not_called()


@pytest.mark.asyncio
async def test_get_bid_ask_crypto_snapshot_does_not_require_exchange_kwarg():
    service = DataService()

    class FakeTicker:
        info = {
            "bid": 0.0,
            "ask": 0.0,
        }

    class FakeQuote:
        bp = 90000.0
        ap = 90010.0

    class FakeSnapshot:
        latest_quote = FakeQuote()

    def fake_get_crypto_snapshots(symbols, **kwargs):
        if kwargs:
            raise TypeError("REST.get_crypto_snapshots() got an unexpected keyword argument 'exchange'")
        return {"BTC/USD": FakeSnapshot()}

    with patch("src.services.data_service.yf.Ticker", return_value=FakeTicker()), \
         patch.object(
             service.alpaca_client,
             "get_crypto_snapshots",
             side_effect=fake_get_crypto_snapshots,
         ):
        bid, ask = await service.get_bid_ask("BTC-USD")

    assert (bid, ask) == (90000.0, 90010.0)
