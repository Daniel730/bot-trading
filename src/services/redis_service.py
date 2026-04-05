import redis.asyncio as redis
import json
from typing import Optional, Any
from src.config import settings

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
        """Sets the current price for a ticker in the shadow book."""
        await self.client.set(f"price:{ticker}", price)

    async def get_price(self, ticker: str) -> Optional[float]:
        """Gets the current price for a ticker from the shadow book."""
        price = await self.client.get(f"price:{ticker}")
        return float(price) if price else None

    async def set_json(self, key: str, value: Any, ex: Optional[int] = None):
        """Sets a JSON value in Redis."""
        await self.client.set(key, json.dumps(value), ex=ex)

    async def get_json(self, key: str) -> Optional[Any]:
        """Gets a JSON value from Redis."""
        value = await self.client.get(key)
        return json.loads(value) if value else None

    async def publish(self, channel: str, message: Any):
        """Publishes a message to a Redis channel."""
        await self.client.publish(channel, json.dumps(message))

    async def save_kalman_state(self, ticker_pair: str, x: list, P: list, z_score: float):
        """
        Saves the current Kalman filter state (vector x and matrix P) to a Redis Hash.
        Also stores the z_score for monitoring.
        """
        key = f"kalman:{ticker_pair}"
        state = {
            "x": json.dumps(x),
            "P": json.dumps(P),
            "z_score": str(z_score)
        }
        await self.client.hset(key, mapping=state)

    async def get_kalman_state(self, ticker_pair: str) -> Optional[dict]:
        """Retrieves the Kalman filter state from Redis."""
        key = f"kalman:{ticker_pair}"
        state = await self.client.hgetall(key)
        if not state:
            return None
        
        return {
            "x": json.loads(state["x"]),
            "P": json.loads(state["P"]),
            "z_score": float(state["z_score"])
        }

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

redis_service = RedisService()
