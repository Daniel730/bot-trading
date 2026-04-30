import logging
import yfinance as yf
import pandas as pd
import requests
from polygon import RESTClient
from typing import Callable, List, Optional, TypeVar
from src.config import settings
import asyncio
import inspect
from src.services.agent_log_service import agent_trace

logger = logging.getLogger(__name__)
T = TypeVar("T")

class AwaitableDict(dict):
    def __await__(self):
        async def _coro():
            return self
        return _coro().__await__()

from src.services.redis_service import redis_service
from polygon.websocket import WebSocketClient
from polygon.websocket.models import Market, Feed
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

class DataService:
    def __init__(self):
        self.polygon_client = RESTClient(api_key=settings.POLYGON_API_KEY)
        self._ws_client: Optional[WebSocketClient] = None

    def _download_yfinance(self, *args, **kwargs) -> pd.DataFrame:
        kwargs.setdefault("timeout", settings.MARKET_DATA_TIMEOUT_SECONDS)
        try:
            return yf.download(*args, **kwargs)
        except TypeError as exc:
            if "timeout" not in str(exc):
                raise
            kwargs.pop("timeout", None)
            return yf.download(*args, **kwargs)

    @staticmethod
    def _dedupe_tickers(tickers: List[str]) -> List[str]:
        seen = set()
        result = []
        for ticker in tickers:
            if ticker and ticker not in seen:
                seen.add(ticker)
                result.append(ticker)
        return result

    @staticmethod
    def _chunks(items: List[str], size: int):
        size = max(1, int(size or 1))
        for idx in range(0, len(items), size):
            yield items[idx: idx + size]

    @staticmethod
    def _summarize_tickers(tickers: List[str]) -> str:
        if len(tickers) <= 8:
            return str(tickers)
        head = ", ".join(tickers[:8])
        return f"[{head}, ...] ({len(tickers)} tickers)"

    @staticmethod
    def _maybe_randomize_price(value: float) -> float:
        if settings.DEV_MODE:
            import random
            return value * (1 + random.uniform(-0.015, 0.015))
        return value

    async def _run_sync_backend(
        self,
        func: Callable[..., T],
        *args,
        timeout: Optional[float] = None,
        label: str = "backend request",
        fallback: Optional[T] = None,
        **kwargs,
    ) -> T:
        deadline = timeout if timeout is not None else settings.MARKET_DATA_TIMEOUT_SECONDS

        async def runner():
            if inspect.iscoroutinefunction(func):
                result = func(*args, **kwargs)
            else:
                result = await asyncio.to_thread(func, *args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        try:
            return await asyncio.wait_for(runner(), timeout=deadline)
        except asyncio.TimeoutError:
            logger.warning("DataService: %s timed out after %.1fs", label, deadline)
            return fallback

    @agent_trace("DataService.get_historical_data_async")
    async def get_historical_data_async(
        self,
        tickers: List[str],
        period: str = "30d",
        interval: str = "1h",
        timeout: Optional[float] = None,
    ) -> pd.DataFrame:
        return await self._run_sync_backend(
            self.get_historical_data,
            tickers,
            period,
            interval,
            timeout=timeout,
            label=f"historical data for {tickers}",
            fallback=pd.DataFrame(),
        )

    @staticmethod
    def _extract_latest_close(
        df: pd.DataFrame,
        ticker: str,
        allow_single_column_fallback: bool = True,
    ) -> Optional[float]:
        """Return the newest non-null close price from flat or MultiIndex yfinance data."""
        if df.empty:
            return None

        close_data = None
        if isinstance(df.columns, pd.MultiIndex):
            if "Close" in df.columns.get_level_values(0):
                close_data = df["Close"]
            elif "Close" in df.columns.get_level_values(-1):
                close_data = df.xs("Close", axis=1, level=-1)
        elif "Close" in df.columns:
            close_data = df["Close"]

        if close_data is None:
            return None

        if isinstance(close_data, pd.DataFrame):
            if ticker in close_data.columns:
                series = close_data[ticker]
            elif allow_single_column_fallback and len(close_data.columns) == 1:
                series = close_data.iloc[:, 0]
            else:
                return None
        else:
            series = close_data

        series = series.dropna()
        if series.empty:
            return None
        return float(series.iloc[-1])

    @agent_trace("DataService.get_historical_data")
    def get_historical_data(self, tickers: List[str], period: str = "30d", interval: str = "1h") -> pd.DataFrame:
        """
        Fetches historical data using yfinance with auto_adjust=True.
        """
        try:
            # Bug 1.2: Enforce auto_adjust=True to handle splits and dividends correctly
            df = self._download_yfinance(tickers, period=period, interval=interval, progress=False, auto_adjust=True)
            if df.empty:
                raise ValueError(f"No data returned for {tickers}")
            
            # When auto_adjust=True, 'Adj Close' is usually not present, 'Close' IS the adjusted close
            if 'Close' in df.columns:
                return df['Close']
            else:
                # In some cases yf returns a flat DF
                cols = [c for c in df.columns if 'Close' in c]
                if cols:
                    return df[cols]
                raise KeyError(f"Adjusted 'Close' not found in columns: {df.columns}")
        except Exception as e:
            logger.error(f"DataService: yfinance error for {tickers}: {e}")
            raise

    @agent_trace("DataService.get_latest_price")
    def get_latest_price(self, tickers: List[str]) -> dict:
        """
        Fetches the latest prices for given tickers.
        Tries Redis shadow book first, falls back to yfinance with retries.
        Decision 1: Uses tenacity for 3-attempt exponential backoff.
        """
        tickers = self._dedupe_tickers(tickers)
        latest = {}
        remaining_tickers = []

        # 1. Try Redis Shadow Book
        for ticker in tickers:
            price = None
            try:
                candidate = redis_service.get_price(ticker)
                if not asyncio.iscoroutine(candidate):
                    price = candidate
                else:
                    candidate.close()
            except Exception:
                price = None
            if price:
                latest[ticker] = price
            else:
                remaining_tickers.append(ticker)

        if not remaining_tickers:
            return latest

        # 2. Fallback to yfinance for remaining with retry logic
        try:
            yfinance_prices = self._get_latest_price_yfinance_with_retry(remaining_tickers)
            for ticker, price in yfinance_prices.items():
                try:
                    stored = redis_service.set_price(ticker, price)
                    if asyncio.iscoroutine(stored):
                        stored.close()
                except Exception:
                    pass
            latest.update(yfinance_prices)
        except Exception as e:
            logger.error(f"DataService: retry failed after 3 attempts for {remaining_tickers}: {e}")
            
        return AwaitableDict(latest)

    @agent_trace("DataService.get_latest_price_async")
    async def get_latest_price_async(self, tickers: List[str], timeout: Optional[float] = None) -> dict:
        tickers = self._dedupe_tickers(tickers)
        if not tickers:
            return AwaitableDict({})

        batch_size = max(1, int(settings.MARKET_DATA_BATCH_SIZE))
        if len(tickers) <= batch_size:
            prices = await self._run_sync_backend(
                self.get_latest_price,
                tickers,
                timeout=timeout,
                label=f"latest prices for {self._summarize_tickers(tickers)}",
                fallback={},
            )
            return AwaitableDict(prices or {})

        latest = {}
        remaining_tickers = []

        async def read_cached_price(ticker: str):
            try:
                return ticker, await redis_service.get_price(ticker)
            except Exception:
                return ticker, None

        cached = await asyncio.gather(
            *(read_cached_price(ticker) for ticker in tickers),
            return_exceptions=True,
        )
        for item in cached:
            if isinstance(item, Exception):
                continue
            ticker, price = item
            if price:
                latest[ticker] = price
            else:
                remaining_tickers.append(ticker)

        if not remaining_tickers:
            return AwaitableDict(latest)

        per_batch_timeout = timeout if timeout is not None else settings.MARKET_DATA_TIMEOUT_SECONDS
        concurrency = max(1, int(settings.MARKET_DATA_BATCH_CONCURRENCY))
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_chunk(chunk: List[str]) -> dict:
            async with semaphore:
                return await self._run_sync_backend(
                    self._get_latest_price_yfinance_batch,
                    chunk,
                    timeout=per_batch_timeout,
                    label=f"latest price chunk {self._summarize_tickers(chunk)}",
                    fallback={},
                )

        chunk_results = await asyncio.gather(
            *(fetch_chunk(chunk) for chunk in self._chunks(remaining_tickers, batch_size)),
            return_exceptions=True,
        )

        cache_writes = []
        for result in chunk_results:
            if isinstance(result, Exception) or not result:
                continue
            latest.update(result)
            for ticker, price in result.items():
                cache_writes.append(redis_service.set_price(ticker, price))

        if cache_writes:
            await asyncio.gather(*cache_writes, return_exceptions=True)

        missing_count = len(tickers) - len(latest)
        if missing_count:
            logger.warning(
                "DataService: missing latest prices for %d/%d tickers after chunked fetch",
                missing_count,
                len(tickers),
            )

        return AwaitableDict(latest)

    def _get_latest_price_yfinance_batch(self, tickers: List[str]) -> dict:
        """Fetch latest prices for a chunk of tickers in one yfinance request."""
        tickers = self._dedupe_tickers(tickers)
        if not tickers:
            return {}

        download_arg = tickers[0] if len(tickers) == 1 else tickers
        df = self._download_yfinance(
            download_arg,
            period="1d",
            interval="1m",
            progress=False,
            auto_adjust=True,
            threads=True,
        )

        results = {}
        for ticker in tickers:
            val = self._extract_latest_close(
                df,
                ticker,
                allow_single_column_fallback=len(tickers) == 1,
            )
            if val is not None:
                results[ticker] = self._maybe_randomize_price(val)
        return results

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    def _get_latest_price_yfinance_with_retry(self, tickers: List[str]) -> dict:
        """Internal helper to fetch prices from yfinance with tenacity retries.

        Batch failures are allowed to propagate so tenacity can apply the
        exponential backoff between attempts (T013). The per-ticker fallback
        below only runs when the batch call *partially* succeeded — i.e. some
        tickers came back missing from an otherwise-successful response.
        """
        tickers = self._dedupe_tickers(tickers)
        # Let batch exceptions propagate to tenacity so retries with backoff actually happen.
        results = self._get_latest_price_yfinance_batch(tickers)

        # US-035 fallback: per-ticker fetch for tickers missing from a partial batch response.
        import time
        missing = [t for t in tickers if t not in results]
        for ticker in missing:
            try:
                df = self._download_yfinance(ticker, period="1d", interval="1m", progress=False, auto_adjust=True)
                val = self._extract_latest_close(df, ticker)
                if val is not None:
                    results[ticker] = self._maybe_randomize_price(val)
                # Small delay to prevent Yahoo from flagging the IP
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"DataService: Error fetching {ticker} specifically: {e}")
                continue

        if not results:
            raise ValueError(f"No valid prices found in yfinance response for {tickers}")

        return results

    @agent_trace("DataService.get_bid_ask")
    async def get_bid_ask(self, ticker: str) -> tuple[float, float]:
        """Fetches the actual real-time bid and ask for slippage calculation via yfinance."""
        try:
            def fetch():
                info = yf.Ticker(ticker).info
                bid = info.get('bid', 0.0)
                ask = info.get('ask', 0.0)
                # Fallback to currentPrice if bid/ask is missing (e.g. after hours)
                if bid == 0.0 or ask == 0.0:
                    current = info.get('currentPrice', info.get('previousClose', 1.0))
                    return current, current
                return bid, ask
            return await self._run_sync_backend(
                fetch,
                timeout=settings.MARKET_DATA_TIMEOUT_SECONDS,
                label=f"bid/ask for {ticker}",
                fallback=(0.0, 0.0),
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to fetch Bid/Ask for {ticker}: {e}")
            return 0.0, 0.0

    @agent_trace("DataService.stream_realtime_data")
    async def stream_realtime_data(self, tickers: List[str]):
        """
        Connects to Polygon WebSocket to stream real-time prices into Redis.
        """
        loop = asyncio.get_running_loop()
        def handle_msg(msgs):
            for m in msgs:
                # Trade event (T) or Quote event (Q)
                if hasattr(m, 'price'):
                    # Bug M-04: Ensure async Redis write is scheduled
                    asyncio.run_coroutine_threadsafe(redis_service.set_price(m.symbol, m.price), loop)
                elif hasattr(m, 'bid_price'):
                    # Mid-price approximation
                    mid = (m.bid_price + m.ask_price) / 2
                    asyncio.run_coroutine_threadsafe(redis_service.set_price(m.symbol, mid), loop)

        # Polygon WebSocket implementation
        self._ws_client = WebSocketClient(
            api_key=settings.POLYGON_API_KEY,
            feed=Feed.Delayed, # Use Delayed for free tier, RealTime for paid
            market=Market.Stocks,
            subscriptions=[f"T.{t}" for t in tickers] + [f"Q.{t}" for t in tickers]
        )
        
        # Start processing in background or current loop
        # Note: This is a simplified version; real usage might need a separate thread/task
        await self._ws_client.run(handle_msg)

data_service = DataService()
