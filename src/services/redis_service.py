import redis
import json
import os
from typing import Optional, Any
from pydantic_settings import BaseSettings

class RedisSettings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        extra = "ignore"

class RedisService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisService, cls).__new__(cls)
            settings = RedisSettings()
            cls._instance.client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return cls._instance

    def set_price(self, ticker: str, price: float):
        """Sets the current price for a ticker in the shadow book."""
        self.client.set(f"price:{ticker}", price)

    def get_price(self, ticker: str) -> Optional[float]:
        """Gets the current price for a ticker from the shadow book."""
        price = self.client.get(f"price:{ticker}")
        return float(price) if price else None

    def set_json(self, key: str, value: Any, ex: Optional[int] = None):
        """Sets a JSON value in Redis."""
        self.client.set(key, json.dumps(value), ex=ex)

    def get_json(self, key: str) -> Optional[Any]:
        """Gets a JSON value from Redis."""
        value = self.client.get(key)
        return json.loads(value) if value else None

    def publish(self, channel: str, message: Any):
        """Publishes a message to a Redis channel."""
        self.client.publish(channel, json.dumps(message))

redis_service = RedisService()
