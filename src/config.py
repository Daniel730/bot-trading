import json
import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

load_dotenv()

# Path to user-editable pairs override file (created/edited by the dashboard).
PAIRS_OVERRIDE_PATH = Path(__file__).resolve().parent.parent / "data" / "pairs.json"


def _load_pairs_override():
    """Load runtime-editable pair overrides from data/pairs.json if present."""
    try:
        if not PAIRS_OVERRIDE_PATH.exists():
            return None
        with PAIRS_OVERRIDE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def save_pairs_override(arbitrage_pairs: list, crypto_test_pairs=None) -> None:
    """Persist a new pair universe to data/pairs.json. Creates dir if needed."""
    PAIRS_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ARBITRAGE_PAIRS": arbitrage_pairs}
    if crypto_test_pairs is not None:
        payload["CRYPTO_TEST_PAIRS"] = crypto_test_pairs
    with PAIRS_OVERRIDE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        env_prefix=''
    )

    POLYGON_API_KEY: str = Field(default="", validation_alias="POLYGON_API_KEY")
    GEMINI_API_KEY: str = Field(default="", validation_alias="GEMINI_API_KEY")
    TELEGRAM_BOT_TOKEN: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")

    T212_API_KEY: str = Field(default="", validation_alias="T212_API_KEY")
    T212_API_SECRET: str = Field(default="", validation_alias="T212_API_SECRET")
    TRADING_212_API_KEY: str = Field(default="", validation_alias="TRADING_212_API_KEY")

    REDIS_HOST: str = Field(default="localhost", validation_alias="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, validation_alias="REDIS_PORT")
    REDIS_DB: int = Field(default=0, validation_alias="REDIS_DB")
    REDIS_PASSWORD: str = Field(default="", validation_alias="REDIS_PASSWORD")
    REDIS_APPENDONLY: bool = Field(default=True, validation_alias="REDIS_APPENDONLY")

    POSTGRES_HOST: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    POSTGRES_USER: str = Field(default="bot_admin", validation_alias="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(validation_alias="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(default="trading_bot", validation_alias="POSTGRES_DB")

    DASHBOARD_TOKEN: str = Field(validation_alias="DASHBOARD_TOKEN")
    REGION: Literal["US", "EU"] = Field(default="US", validation_alias="REGION")

    DB_PATH: str = Field(default="data/trading_bot.db", validation_alias="DB_PATH")

    TRADING_212_MODE: str = "demo"
    DEV_MODE: bool = False
    PAPER_TRADING: bool = True
    MAX_ALLOCATION_PERCENTAGE: float = 10.0
    SGOV_SWEEP_TICKER: str = "SGOV"
    MIN_SWEEP_THRESHOLD: float = 10.0
    LIVE_CAPITAL_DANGER: bool = Field(default=False, validation_alias="LIVE_CAPITAL_DANGER")
    SEC_USER_AGENT: str = Field(default="ArbitrageBot/1.0 (admin@example.com)", validation_alias="SEC_USER_AGENT")

    START_HOUR: int = 9
    START_MINUTE: int = 30
    END_HOUR: int = 16
    END_MINUTE: int = 0
    MARKET_TIMEZONE: str = "America/New_York"

    KELLY_FRACTION: float = 0.25
    MAX_RISK_PER_TRADE: float = 0.02
    MAX_DRAWDOWN: float = 0.10
    APPROVAL_THRESHOLD: float = 100.0

    MAX_FRICTION_PCT: float = 0.015
    MIN_TRADE_VALUE: float = 1.00

    EXECUTION_ENGINE_HOST: str = Field(default="localhost", validation_alias="EXECUTION_ENGINE_HOST")
    EXECUTION_ENGINE_PORT: int = Field(default=50051, validation_alias="EXECUTION_ENGINE_PORT")
    LATENCY_ALARM_THRESHOLD_MS: float = Field(default=10.0, validation_alias="LATENCY_ALARM_THRESHOLD_MS")

    KALMAN_DELTA: float = 1e-5
    KALMAN_R: float = 0.001

    MAX_SECTOR_EXPOSURE: float = 0.30
    PAIR_SECTORS: dict = {
        'KO_PEP': 'Consumer Staples', 'MA_V': 'Financials', 'XOM_CVX': 'Energy',
        'JPM_BAC': 'Financials', 'WMT_TGT': 'Consumer Staples', 'GOOGL_GOOG': 'Technology',
        'MSFT_AAPL': 'Technology', 'DAL_UAL': 'Industrials', 'UPS_FDX': 'Industrials',
        'HD_LOW': 'Consumer Discretionary', 'GM_F': 'Consumer Discretionary',
        'INTC_AMD': 'Technology', 'PYPL_AFRM': 'Financials',
        'NKE_ADDYY': 'Consumer Discretionary', 'PG_CL': 'Consumer Staples',
        'BA_AIR.PA': 'Industrials', 'T_VZ': 'Telecommunications',
        'VLO_MPC': 'Energy', 'COF_SYF': 'Financials', 'GS_MS': 'Financials',
        'BTCE.DE_ZETH.DE': 'Crypto ETNs'
    }

    EU_HEDGE_MAPPINGS: dict = {
        "SPY": "XSPS.L", "QQQ": "SQQQ.L", "IWM": "R2SC.L", "DIA": "DOG"
    }

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
        {'ticker_a': 'GS', 'ticker_b': 'MS'},
        {'ticker_a': 'BTCE.DE', 'ticker_b': 'ZETH.DE'}
    ]

    CRYPTO_TEST_PAIRS: list = [
        {'ticker_a': 'BTC-USD', 'ticker_b': 'ETH-USD'},
        {'ticker_a': 'BNB-USD', 'ticker_b': 'SOL-USD'}
    ]

    DEV_EXECUTION_TICKERS: dict = {
        'BTC-USD': 'MSFT', 'ETH-USD': 'AAPL', 'BNB-USD': 'GOOGL', 'SOL-USD': 'TSLA'
    }

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

# Apply runtime overrides for the trading-pair universe (dashboard-editable).
_override = _load_pairs_override()
if _override:
    if isinstance(_override.get("ARBITRAGE_PAIRS"), list):
        settings.ARBITRAGE_PAIRS = _override["ARBITRAGE_PAIRS"]
    if isinstance(_override.get("CRYPTO_TEST_PAIRS"), list):
        settings.CRYPTO_TEST_PAIRS = _override["CRYPTO_TEST_PAIRS"]
