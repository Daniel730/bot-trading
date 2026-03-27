import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Trading 212 API
    t212_api_key: str = "your_api_key"
    t212_api_secret: str = "your_api_secret"
    t212_demo: bool = True

    # Market Data
    polygon_api_key: str = "your_polygon_key"

    # Telegram Notification
    telegram_bot_token: str = "your_bot_token"
    telegram_chat_id: str = "your_chat_id"

    # Risk Management
    max_allocation_percentage: float = 10.0

    # Operational
    operating_timezone: str = "WET"
    log_level: str = "INFO"

    # Database
    db_path: str = "trading_bot.sqlite"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Top-level access for backward compatibility with existing tasks
DB_PATH = settings.db_path
T212_API_KEY = settings.t212_api_key
T212_API_SECRET = settings.t212_api_secret
POLYGON_API_KEY = settings.polygon_api_key
TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
TELEGRAM_CHAT_ID = settings.telegram_chat_id
