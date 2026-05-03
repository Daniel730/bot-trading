import logging
import yfinance as yf
import pandas as pd
import requests
from polygon import RESTClient
from typing import Callable, List, Optional, TypeVar
from src.config import settings
import asyncio
import inspect
from datetime import datetime, timedelta, timezone
import alpaca_trade_api as tradeapi
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
        self.alpaca_client = tradeapi.REST(
            key_id=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_API_SECRET,
            base_url=settings.ALPACA_BASE_URL
        )
        self._ws_client: Optional[WebSocketClient] = None

    def _download_yfinance(self, *args, **kwargs) -> pd.DataFrame:
        """
        Download market data via yfinance with a default timeout and normalized empty-result handling.
        
        Attempts to download data by forwarding all arguments to yf.download, inserting a default "timeout" from settings.MARKET_DATA_TIMEOUT_SECONDS when not provided. If yf.download returns None or an empty DataFrame, a warning is logged and an empty DataFrame is returned. If a TypeError arises mentioning "timeout", the call is retried once after removing the "timeout" kwarg. Any other exception raised by yf.download is propagated.
        
        Parameters:
            *args: Positional arguments passed through to yf.download (typically tickers and/or download options).
            **kwargs: Keyword arguments passed through to yf.download. A default "timeout" is applied when absent.
        
        Returns:
            pd.DataFrame: The DataFrame returned by yfinance, or an empty DataFrame if no data was obtained.
        
        Raises:
            Exception: Re-raises exceptions raised by yf.download except for a TypeError caused by a "timeout" argument, which is handled by retrying without "timeout".
        """
        kwargs.setdefault("timeout", settings.MARKET_DATA_TIMEOUT_SECONDS)
        try:
            df = yf.download(*args, **kwargs)
            if df is None or df.empty:
                # yfinance often prints 'Possible delisted' to stdout. 
                # We catch the empty result here to log it clearly.
                logger.warning(f"DataService: yfinance download returned empty for {args[0] if args else 'unknown'}")
                return pd.DataFrame()
            return df
        except TypeError as exc:
            if "timeout" not in str(exc):
                raise
            kwargs.pop("timeout", None)
            return yf.download(*args, **kwargs)
        except Exception as exc:
            logger.error(f"DataService: yfinance download failed: {exc}")
            raise

    @staticmethod
    def _dedupe_tickers(tickers: List[str]) -> List[str]:
        """
        Remove falsy entries and duplicate tickers while preserving first-seen order.
        
        Parameters:
            tickers (List[str]): Sequence of ticker strings that may contain falsy values or duplicates.
        
        Returns:
            List[str]: Tickers in their original order with falsy values omitted and only the first occurrence of each ticker retained.
        """
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

    def _update_redis_cache(self, ticker: str, price: float):
        """Helper to fire-and-forget Redis price updates safely from sync context."""
        try:
            coro = redis_service.set_price(ticker, price)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(coro, loop)
                else:
                    # Close it to avoid warning if we can't run it
                    if inspect.isawaitable(coro): coro.close()
            except Exception:
                if inspect.isawaitable(coro): coro.close()
        except Exception:
            pass

    async def _run_sync_backend(
        self,
        func: Callable[..., T],
        *args,
        timeout: Optional[float] = None,
        label: str = "backend request",
        fallback: Optional[T] = None,
        raise_on_timeout: bool = False,
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
            if raise_on_timeout:
                raise
            return fallback

    @agent_trace("DataService.get_historical_data_async")
    async def get_historical_data_async(
        self,
        tickers: List[str],
        period: str = "30d",
        interval: str = "1h",
        timeout: Optional[float] = None,
    ) -> pd.DataFrame:
        # Increase deadline for historical data to allow for yf delays + retries
        deadline = timeout if timeout is not None else settings.MARKET_DATA_TIMEOUT_SECONDS * 3
        return await self._run_sync_backend(
            self.get_historical_data,
            tickers,
            period,
            interval,
            timeout=deadline,
            label=f"historical data for {tickers}",
            fallback=pd.DataFrame(),
            raise_on_timeout=True
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
            # Check if we can find any valid column by fuzzy match (e.g. MSFT instead of MSFT_Close)
            fuzzy_cols = [c for c in close_data.columns if ticker in c]
            if fuzzy_cols:
                series = close_data[fuzzy_cols[0]].dropna()
                if not series.empty:
                    return float(series.iloc[-1])
            return None
        return float(series.iloc[-1])

    @agent_trace("DataService.get_historical_data")
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    def get_historical_data(self, tickers: List[str], period: str = "30d", interval: str = "1h") -> pd.DataFrame:
        """
        Fetches historical data using Alpaca, falling back to yfinance and Polygon.
        """
        tickers = self._dedupe_tickers(tickers)
        
        # 1. Try Alpaca first (Fastest and most reliable for our Alpaca-only setup)
        try:
            # Map tickers for Alpaca
            # Note: For crypto tickers (e.g. BTC-USD), we fallback to yf/Polygon 
            # because Alpaca historical crypto bars often require a separate 'crypto' subscription
            # and can throw 'invalid symbol' on basic stock plans.
            alpaca_tickers = [t for t in tickers if not t.endswith("-USD")]
            
            if not alpaca_tickers:
                raise ValueError("No stock tickers in batch for Alpaca")
            
            # Map period to days
            days = 30
            if "d" in period: days = int(period.replace("d", ""))
            elif "mo" in period: days = int(period.replace("mo", "")) * 30
            elif "y" in period: days = int(period.replace("y", "")) * 365
            
            # Map interval to Alpaca timeframe
            timeframe = "1Hour" if interval == "1h" else "1Min"
            
            # Use Alpaca bar fetching (RFC3339 UTC format)
            # Free Tier constraint: historical data (SIP) must be at least 15-20 minutes old.
            # Using 21 minutes to be safe.
            end_dt = datetime.now(timezone.utc) - timedelta(minutes=21)
            start_dt = end_dt - timedelta(days=days)
            
            # Format as RFC3339 string without microseconds
            start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Fetch bars
            bars = self.alpaca_client.get_bars(
                alpaca_tickers,
                timeframe,
                start=start_str,
                end=end_str,
                adjustment="raw" # Use 'raw' for broader compatibility with free tier
            ).df
            
            if not bars.empty:
                # Alpaca returns a multi-index (symbol, timestamp) or just timestamp
                if "symbol" in bars.index.names:
                    # Pivoting to get tickers as columns
                    df = bars.reset_index().pivot(index="timestamp", columns="symbol", values="close")
                    # Map back tickers
                    df.columns = [c.replace("/", "-") for c in df.columns]
                    return df
                else:
                    return bars["close"]
        except Exception as e:
            logger.warning(f"DataService: Alpaca historical data failed: {e}")

        # 2. Try yfinance fallback
        try:
            # Bug 1.2: Enforce auto_adjust=True to handle splits and dividends correctly
            df = self._download_yfinance(tickers, period=period, interval=interval, progress=False, auto_adjust=True)
            if not df.empty:
                # When auto_adjust=True, 'Adj Close' is usually not present, 'Close' IS the adjusted close
                if 'Close' in df.columns:
                    return df['Close']
                else:
                    # In some cases yf returns a flat DF
                    cols = [c for c in df.columns if 'Close' in c]
                    if cols:
                        return df[cols]
                    logger.warning(f"Adjusted 'Close' not found in yfinance columns: {df.columns}")
        except Exception as e:
            logger.warning(f"DataService: yfinance historical data error for {tickers}: {e}")

        # 2. Fallback to Polygon if API key exists and it's a small batch
        if settings.POLYGON_API_KEY and len(tickers) <= 5:
            try:
                logger.info(f"DataService: Falling back to Polygon for {tickers} historical data...")
                # Polygon is per-ticker, so we fetch one by one and merge
                
                # Approximate 30d -> dates
                # interval 1h -> 1, "hour"
                poly_data = {}
                end_dt = datetime.now()
                # Simplified period mapping
                days = 30
                if "d" in period: days = int(period.replace("d", ""))
                elif "mo" in period: days = int(period.replace("mo", "")) * 30
                elif "y" in period: days = int(period.replace("y", "")) * 365
                
                start_dt = end_dt - timedelta(days=days)
                
                for ticker in tickers:
                    # Map yfinance crypto to Polygon if needed
                    poly_ticker = ticker
                    if ticker.endswith("-USD"):
                        poly_ticker = f"X:{ticker.replace('-USD', 'USD')}"
                    
                    aggs = self.polygon_client.list_aggs(
                        poly_ticker,
                        1,
                        "hour" if interval == "1h" else "minute",
                        start_dt.strftime("%Y-%m-%d"),
                        end_dt.strftime("%Y-%m-%d"),
                        limit=5000
                    )
                    
                    ticker_aggs = []
                    for agg in aggs:
                        ticker_aggs.append({
                            "timestamp": pd.to_datetime(agg.timestamp, unit="ms"),
                            "Close": agg.close
                        })
                    
                    if ticker_aggs:
                        tdf = pd.DataFrame(ticker_aggs).set_index("timestamp")
                        poly_data[ticker] = tdf["Close"]
                
                if poly_data:
                    final_df = pd.DataFrame(poly_data).sort_index()
                    if not final_df.empty:
                        return final_df
            except Exception as pe:
                logger.error(f"DataService: Polygon fallback failed for {tickers}: {pe}")

        raise ValueError(f"No data returned for {tickers} after yfinance and Polygon attempts.")

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

        # 2. Try Alpaca Snapshot (Batch) for Stocks and Crypto
        if remaining_tickers:
            try:
                # Alpaca Snapshots are very fast and return multiple tickers in one call
                # Note: For crypto tickers like BTC-USD, we might need to map them to Alpaca format
                alpaca_tickers = []
                for t in remaining_tickers:
                    if t.endswith("-USD"):
                        # Alpaca crypto format is often BTC/USD or just BTCUSD depending on the endpoint
                        # Snapshots endpoint usually expects BTC/USD or BTC/USDT
                        alpaca_tickers.append(t.replace("-", "/"))
                    else:
                        alpaca_tickers.append(t)
                
                snapshots = self.alpaca_client.get_snapshots(alpaca_tickers)
                for ticker_key, snapshot in snapshots.items():
                    # Map back to our ticker format
                    internal_ticker = ticker_key.replace("/", "-")
                    if internal_ticker in remaining_tickers:
                        price = float(snapshot.latest_trade.p)
                        if price > 0:
                            latest[internal_ticker] = price
                            self._update_redis_cache(internal_ticker, price)
                
                remaining_tickers = [t for t in remaining_tickers if t not in latest]
            except Exception as e:
                logger.warning(f"DataService: Alpaca snapshot failed: {e}")

        if not remaining_tickers:
            return latest

        # 3. Try Polygon for remaining
        if settings.POLYGON_API_KEY and remaining_tickers:
            poly_prices = self._get_latest_price_polygon(remaining_tickers)
            for ticker, price in poly_prices.items():
                latest[ticker] = price
                try:
                    self._update_redis_cache(ticker, price)
                except Exception:
                    pass
                remaining_tickers = [t for t in remaining_tickers if t not in latest]

        if not remaining_tickers:
            return AwaitableDict(latest)

        # 3. Fallback to yfinance for remaining with retry logic
        try:
            yfinance_prices = self._get_latest_price_yfinance_with_retry(remaining_tickers)
            for ticker, price in yfinance_prices.items():
                try:
                    self._update_redis_cache(ticker, price)
                except Exception:
                    pass
                latest.update(yfinance_prices)
        except Exception as e:
            logger.error(f"DataService: yfinance retry failed for {remaining_tickers}: {e}")
            
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
                    self.get_latest_price,
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

    def _get_latest_price_polygon(self, tickers: List[str]) -> dict:
        """
        Fetch latest prices from Polygon for crypto tickers.
        Uses snapshots for immediate price lookup without historical aggregation.
        """
        if not settings.POLYGON_API_KEY:
            return {}
        
        results = {}
        # Only attempt Polygon for crypto tickers (-USD) or if explicitly prefixed
        crypto_candidates = [t for t in tickers if "-" in t or ":" in t]
        
        for ticker in crypto_candidates:
            try:
                # Map yfinance BTC-USD to Polygon X:BTCUSD
                poly_symbol = ticker
                if ticker.endswith("-USD"):
                    poly_symbol = f"X:{ticker.replace('-USD', 'USD')}"
                
                # get_snapshot_ticker is usually faster and more direct than list_aggs for 'latest'
                snapshot = self.polygon_client.get_snapshot_ticker("crypto", poly_symbol)
                
                # Check for trade price first, then fallback to last minute close
                price = None
                if hasattr(snapshot, 'last_trade') and snapshot.last_trade and snapshot.last_trade.price:
                    price = float(snapshot.last_trade.price)
                elif hasattr(snapshot, 'min') and snapshot.min and snapshot.min.c:
                    price = float(snapshot.min.c)
                elif hasattr(snapshot, 'prev_day') and snapshot.prev_day and snapshot.prev_day.c:
                    price = float(snapshot.prev_day.c)
                
                if price:
                    results[ticker] = self._maybe_randomize_price(price)
            except Exception:
                # Silently fail for individual tickers to allow yfinance fallback
                continue
        return results

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
        """
        Fetch latest intraday close prices for the given tickers from yfinance, using a retried batch request and limited per-ticker fallbacks.
        
        The function deduplicates the input tickers, performs a batch fetch which is retried with exponential backoff, and then fills any partially-missing tickers by performing sequential single-ticker requests when 1–10 tickers are missing (with a short delay between attempts). If more than 10 tickers are missing the per-ticker fallback is skipped to avoid long timeouts. If no valid prices are obtained, an empty dict is returned and an error is logged.
        
        Returns:
            dict: Mapping from ticker string to latest price (float) for tickers successfully fetched.
        """
        tickers = self._dedupe_tickers(tickers)
        # Let batch exceptions propagate to tenacity so retries with backoff actually happen.
        results = self._get_latest_price_yfinance_batch(tickers)

        # US-035 fallback: per-ticker fetch for tickers missing from a partial batch response.
        import time
        missing = [t for t in tickers if t not in results]
        
        # T014: Cap sequential fallback to avoid 120s timeouts on large partial failures.
        # If > 10 tickers are missing, we likely hit a rate limit or massive batch failure;
        # doing 10+ sequential requests with 0.5s sleeps is too slow.
        if 0 < len(missing) <= 10:
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
        elif len(missing) > 10:
            logger.warning(
                "DataService: %d tickers missing from batch, skipping individual fallback to avoid timeout. Missing: %s",
                len(missing),
                self._summarize_tickers(missing)
            )

        if not results:
            logger.error(f"DataService: Critical - No valid prices found for {tickers}. This may indicate a network issue or mass delisting.")
            # Return an empty dict instead of raising if we want to avoid crashing the caller
            return results

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
