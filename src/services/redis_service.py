import redis.asyncio as redis
import json
from typing import Optional, Any
from src.config import settings

# Canonical Redis key namespaces and their lifecycle expectations.
# Dashboard login sessions are JWT/in-process — they are NOT stored in Redis.
REDIS_KEY_NAMESPACES = {
    "price": {"pattern": "price:{ticker}", "ttl": "10s (set_price)"},
    "kalman": {"pattern": "kalman:{pair_id}", "ttl": "KALMAN_STATE_TTL_SECONDS sliding"},
    "sec:integrity": {"pattern": "sec:integrity:{ticker}", "ttl": "24h"},
    "ratelimit": {"pattern": "ratelimit:{api}:{window}", "ttl": "rate window"},
    "latency": {"pattern": "latency:metrics:raw", "ttl": "1h + LTRIM 1000"},
    "cache": {"pattern": "cache:{name}", "ttl": "caller-supplied (e.g. tnx 1h)"},
    "execution_attempt": {"pattern": "execution_attempt:{signal_id}", "ttl": "1h"},
    "execution_attempt_lock": {"pattern": "execution_attempt_lock:{signal_id}", "ttl": "60s"},
    "execution:inflight": {"pattern": "execution:inflight:{uuid}", "ttl": "1h (Java)"},
    "l2": {"pattern": "l2:snapshot:{ticker} / l2:{ticker}", "ttl": "writer-supplied"},
    "whale": {"pattern": "whale:*", "ttl": "WHALE_WATCHER_CACHE_TTL_SECONDS"},
    "entropy_baseline": {"pattern": "entropy_baseline:{ticker}", "ttl": "persistent (live gate)"},
}


class RedisService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisService, cls).__new__(cls)
            cls._instance.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True
            )
        return cls._instance

    async def set_price(self, ticker: str, price: float):
        """Sets the current price for a ticker in the shadow book.
        TTL of 10 s ensures the cache expires between scan cycles (every 15 s)
        so yfinance is called again and the Kalman filter receives fresh prices."""
        await self.client.set(f"price:{ticker}", price, ex=10)

    async def get_price(self, ticker: str) -> Optional[float]:
        """Gets the current price for a ticker from the shadow book."""
        price = await self.client.get(f"price:{ticker}")
        return float(price) if price else None

    async def set_json(self, key: str, value: Any, ex: Optional[int] = None):
        """Sets a JSON value in Redis."""
        await self.client.set(key, json.dumps(value), ex=ex)

    async def set_json_nx(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Sets a JSON value only when the key does not already exist."""
        result = await self.client.set(key, json.dumps(value), nx=True, ex=ex)
        return bool(result)

    async def get_json(self, key: str) -> Optional[Any]:
        """Gets a JSON value from Redis."""
        value = await self.client.get(key)
        return json.loads(value) if value else None

    async def delete(self, key: str) -> int:
        """Deletes a Redis key."""
        return await self.client.delete(key)

    async def publish(self, channel: str, message: Any):
        """Publishes a message to a Redis channel."""
        await self.client.publish(channel, json.dumps(message))

    async def save_kalman_state(
        self,
        ticker_pair: str,
        x: list,
        P: list,
        z_score: float,
        innovation_variance: float = 0.0,
        state_fingerprint: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ):
        """
        Saves the current Kalman filter state (vector x and matrix P) to a Redis Hash.
        Also stores the z_score and innovation_variance for monitoring and warm-start restoration.

        Applies a sliding TTL so pairs that leave the universe (or stay quarantined)
        do not accumulate unbounded orphan hashes after Redis AUTH / long uptime.
        """
        key = f"kalman:{ticker_pair}"
        state = {
            "x": json.dumps(x),
            "P": json.dumps(P),
            "z_score": str(z_score),
            "innovation_variance": str(innovation_variance)
        }
        if state_fingerprint:
            state["state_fingerprint"] = state_fingerprint
        await self.client.hset(key, mapping=state)
        ttl = settings.KALMAN_STATE_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
        if ttl > 0:
            await self.client.expire(key, ttl)

    async def get_kalman_state(self, ticker_pair: str) -> Optional[dict]:
        """Retrieves the Kalman filter state from Redis."""
        key = f"kalman:{ticker_pair}"
        state = await self.client.hgetall(key)
        if not state:
            return None

        return {
            "x": json.loads(state["x"]),
            "P": json.loads(state["P"]),
            "z_score": float(state["z_score"]),
            "innovation_variance": float(state.get("innovation_variance", 0.0)),
            "state_fingerprint": state.get("state_fingerprint")
        }

    async def delete_kalman_state(self, ticker_pair: str) -> int:
        """Deletes a Kalman hash (quarantine / universe removal)."""
        return await self.client.delete(f"kalman:{ticker_pair}")

    async def check_rate_limit(self, api_name: str, limit: int, window: int = 3600) -> bool:
        """
        Atomic rate limiting using Redis INCR and EXPIRE.
        Returns True if the limit has not been exceeded.
        """
        # Current window based on timestamp (simplistic windowing)
        import time
        window_start = int(time.time() / window)
        key = f"ratelimit:{api_name}:{window_start}"
        
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, window)
            
        return count <= limit

    async def get_fundamental_score(self, ticker: str) -> Optional[dict]:
        """Gets the cached fundamental score for a ticker."""
        return await self.get_json(f"sec:integrity:{ticker}")

    async def set_fundamental_score(self, ticker: str, score_data: dict):
        """Sets the fundamental score for a ticker with a 24h TTL."""
        await self.set_json(f"sec:integrity:{ticker}", score_data, ex=86400)

    async def set_nx(self, key: str, value: Any, expire: int = 60) -> bool:
        """Atomic SET NX EX."""
        result = await self.client.set(key, value, nx=True, ex=expire)
        return bool(result)

    async def push_latency_metrics(self, metrics: dict):
        """Pushes a latency metric to a Redis list with a 1h TTL (via expiration on key)."""
        key = "latency:metrics:raw"
        await self.client.lpush(key, json.dumps(metrics))
        await self.client.ltrim(key, 0, 999) # Keep only last 1000 samples
        await self.client.expire(key, 3600) # Expire after 1 hour of inactivity

    async def get_recent_latency(self, count: int = 100) -> list:
        """Retrieves the most recent latency metrics from Redis."""
        key = "latency:metrics:raw"
        samples = await self.client.lrange(key, 0, count - 1)
        return [json.loads(s) for s in samples]

class _LazyRedisService:
    def __init__(self):
        self._instance: Optional[RedisService] = None

    def _get_instance(self) -> RedisService:
        if self._instance is None:
            self._instance = RedisService()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    @property
    def client(self):
        return self._get_instance().client

    @client.setter
    def client(self, value):
        self._get_instance().client = value

    async def set_price(self, ticker: str, price: float):
        return await self._get_instance().set_price(ticker, price)

    async def get_price(self, ticker: str) -> Optional[float]:
        return await self._get_instance().get_price(ticker)

    async def set_json(self, key: str, value: Any, ex: Optional[int] = None):
        return await self._get_instance().set_json(key, value, ex=ex)

    async def set_json_nx(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        return await self._get_instance().set_json_nx(key, value, ex=ex)

    async def get_json(self, key: str) -> Optional[Any]:
        return await self._get_instance().get_json(key)

    async def delete(self, key: str) -> int:
        return await self._get_instance().delete(key)

    async def publish(self, channel: str, message: Any):
        return await self._get_instance().publish(channel, message)

    async def save_kalman_state(
        self,
        ticker_pair: str,
        x: list,
        P: list,
        z_score: float,
        innovation_variance: float = 0.0,
        state_fingerprint: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ):
        return await self._get_instance().save_kalman_state(
            ticker_pair,
            x,
            P,
            z_score,
            innovation_variance=innovation_variance,
            state_fingerprint=state_fingerprint,
            ttl_seconds=ttl_seconds,
        )

    async def get_kalman_state(self, ticker_pair: str) -> Optional[dict]:
        return await self._get_instance().get_kalman_state(ticker_pair)

    async def delete_kalman_state(self, ticker_pair: str) -> int:
        return await self._get_instance().delete_kalman_state(ticker_pair)

    async def check_rate_limit(self, api_name: str, limit: int, window: int = 3600) -> bool:
        return await self._get_instance().check_rate_limit(api_name, limit, window=window)

    async def get_fundamental_score(self, ticker: str) -> Optional[dict]:
        return await self._get_instance().get_fundamental_score(ticker)

    async def set_fundamental_score(self, ticker: str, score_data: dict):
        return await self._get_instance().set_fundamental_score(ticker, score_data)

    async def set_nx(self, key: str, value: Any, expire: int = 60) -> bool:
        return await self._get_instance().set_nx(key, value, expire=expire)

    async def push_latency_metrics(self, metrics: dict):
        return await self._get_instance().push_latency_metrics(metrics)

    async def get_recent_latency(self, count: int = 100) -> list:
        return await self._get_instance().get_recent_latency(count=count)


redis_service = _LazyRedisService()
