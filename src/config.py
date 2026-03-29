import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', 
        env_file_encoding='utf-8', 
        extra='ignore',
        env_prefix='' # No prefix required
    )

    # Use Field with validation to ensure they are picked up
    POLYGON_API_KEY: str = Field(default="", validation_alias="POLYGON_API_KEY")
    GEMINI_API_KEY: str = Field(default="", validation_alias="GEMINI_API_KEY")
    TELEGRAM_BOT_TOKEN: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")
    
    # Support both T212_API_KEY and TRADING_212_API_KEY
    T212_API_KEY: str = Field(default="", validation_alias="T212_API_KEY")
    TRADING_212_API_KEY: str = Field(default="", validation_alias="TRADING_212_API_KEY")
    
    TRADING_212_MODE: str = "demo"
    DB_PATH: str = "trading_bot.db"
    DEV_MODE: bool = False
    
    # Operation Hours (WET)
    START_HOUR: int = 14
    START_MINUTE: int = 30
    END_HOUR: int = 21
    END_MINUTE: int = 0
    
    # Risk Parameters
    KELLY_FRACTION: float = 0.25
    MAX_RISK_PER_TRADE: float = 0.02
    MAX_DRAWDOWN: float = 0.10
    APPROVAL_THRESHOLD: float = 100.0
    
    # Arbitrage Pairs
    ARBITRAGE_PAIRS: list = [
        {'ticker_a': 'KO', 'ticker_b': 'PEP'},
        {'ticker_a': 'MA', 'ticker_b': 'V'},
        {'ticker_a': 'XOM', 'ticker_b': 'CVX'},
        {'ticker_a': 'JPM', 'ticker_b': 'BAC'},
        {'ticker_a': 'WMT', 'ticker_b': 'TGT'},
        {'ticker_a': 'GOOGL', 'ticker_b': 'GOOG'},
        {'ticker_a': 'MSFT', 'ticker_b': 'AAPL'},
        {'ticker_a': 'DAL', 'ticker_b': 'UAL'},
        {'ticker_a': 'UPS', 'ticker_b': 'FDX'},
        {'ticker_a': 'HD', 'ticker_b': 'LOW'},
        {'ticker_a': 'GM', 'ticker_b': 'F'},
        {'ticker_a': 'INTC', 'ticker_b': 'AMD'},
        {'ticker_a': 'PYPL', 'ticker_b': 'AFRM'},
        {'ticker_a': 'NKE', 'ticker_b': 'ADDYY'},
        {'ticker_a': 'PG', 'ticker_b': 'CL'},
        {'ticker_a': 'BA', 'ticker_b': 'AIR.PA'},
        {'ticker_a': 'T', 'ticker_b': 'VZ'},
        {'ticker_a': 'VLO', 'ticker_b': 'MPC'},
        {'ticker_a': 'COF', 'ticker_b': 'SYF'},
        {'ticker_a': 'GS', 'ticker_b': 'MS'}
    ]

    # 24/7 Test Pairs
    CRYPTO_TEST_PAIRS: list = [
        {'ticker_a': 'KO', 'ticker_b': 'PEP'},
        {'ticker_a': 'MA', 'ticker_b': 'V'}
    ]

    @property
    def effective_t212_key(self) -> str:
        return self.T212_API_KEY or self.TRADING_212_API_KEY

    @property
    def has_t212_key(self) -> bool:
        return len(self.effective_t212_key) > 5

    @property
    def is_t212_demo(self) -> bool:
        return self.TRADING_212_MODE.lower() == "demo"

settings = Settings()
