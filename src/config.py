import json
import os
from pathlib import Path
from typing import Any, Literal
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic import Field, model_validator

load_dotenv()

# Path to user-editable pairs override file (created/edited by the dashboard).
PAIRS_OVERRIDE_PATH = Path(__file__).resolve().parent.parent / "data" / "pairs.json"
BOT_SETTINGS_OVERRIDE_PATH = Path(__file__).resolve().parent.parent / "data" / "bot_settings.json"

def _load_settings_override():
    try:
        if not BOT_SETTINGS_OVERRIDE_PATH.exists():
            return None
        with BOT_SETTINGS_OVERRIDE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None

def save_settings_override(new_settings: dict) -> None:
    BOT_SETTINGS_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_settings_override() or {}
    existing.update(new_settings)
    with BOT_SETTINGS_OVERRIDE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1].strip()
    return stripped


class _DockerEnvSettingsSource(EnvSettingsSource):
    """Accept JSON values passed through Docker env_file with literal quotes."""

    def prepare_field_value(self, field_name: str, field, value: Any, value_is_complex: bool) -> Any:
        if isinstance(value, str) and field_name in {"CRYPTO_TOKEN_MAPPING"}:
            value = _strip_wrapping_quotes(value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)



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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _DockerEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    POLYGON_API_KEY: str = Field(default="", validation_alias="POLYGON_API_KEY")
    OPENAI_API_KEY: str = Field(default="", validation_alias="OPENAI_API_KEY")
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
    PAPER_TRADING_STARTING_CASH: float = Field(default=10000.0, validation_alias="PAPER_TRADING_STARTING_CASH")
    T212_BUDGET_USD: float = Field(default=0.0, validation_alias="T212_BUDGET_USD")
    WEB3_BUDGET_USD: float = Field(default=0.0, validation_alias="WEB3_BUDGET_USD")
    MAX_ALLOCATION_PERCENTAGE: float = 10.0
    SGOV_SWEEP_TICKER: str = "SGOV"
    MIN_SWEEP_THRESHOLD: float = 10.0
    LIVE_CAPITAL_DANGER: bool = Field(default=False, validation_alias="LIVE_CAPITAL_DANGER")
    ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM: bool = Field(
        default=False,
        validation_alias="ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM",
    )
    SEC_USER_AGENT: str = Field(default="ArbitrageBot/1.0 (admin@example.com)", validation_alias="SEC_USER_AGENT")
    DASHBOARD_ALLOWED_ORIGINS: str = Field(default="", validation_alias="DASHBOARD_ALLOWED_ORIGINS")
    DASHBOARD_ALLOWED_ORIGIN_REGEX: str = Field(default="", validation_alias="DASHBOARD_ALLOWED_ORIGIN_REGEX")

    START_HOUR: int = 9
    START_MINUTE: int = 30
    END_HOUR: int = 16
    END_MINUTE: int = 0
    MARKET_TIMEZONE: str = "America/New_York"

    KELLY_FRACTION: float = 0.25
    MAX_RISK_PER_TRADE: float = 0.02
    MAX_DRAWDOWN: float = 0.10
    APPROVAL_THRESHOLD: float = 100.0
    DEFAULT_WIN_PROBABILITY: float = 0.55
    DEFAULT_WIN_LOSS_RATIO: float = 1.0

    MAX_FRICTION_PCT: float = 0.015
    T212_FLAT_SPREAD_USD: float = Field(default=0.5, validation_alias="T212_FLAT_SPREAD_USD")
    MICRO_TRADE_THRESHOLD_USD: float = Field(default=5.0, validation_alias="MICRO_TRADE_THRESHOLD_USD")
    # WEB3 / DEX trades carry percentage-based gas + slippage instead of a
    # fixed equity spread, so they need a wider friction tolerance.
    # 3 % covers Uniswap pool fee (0.3%) + max configured slippage (1.5 %) +
    # gas headroom on testnet. Raise toward 0.05 for high-gas mainnet use.
    WEB3_MAX_FRICTION_PCT: float = Field(default=0.03, validation_alias="WEB3_MAX_FRICTION_PCT")
    MIN_TRADE_VALUE: float = 1.00
    FINANCIAL_KILL_SWITCH_PCT: float = Field(default=0.02, validation_alias="FINANCIAL_KILL_SWITCH_PCT")
    T212_LIMIT_SLIPPAGE_PCT: float = Field(default=0.01, validation_alias="T212_LIMIT_SLIPPAGE_PCT")

    EXECUTION_ENGINE_HOST: str = Field(default="localhost", validation_alias="EXECUTION_ENGINE_HOST")
    EXECUTION_ENGINE_PORT: int = Field(default=50051, validation_alias="EXECUTION_ENGINE_PORT")
    LATENCY_ALARM_THRESHOLD_MS: float = Field(default=10.0, validation_alias="LATENCY_ALARM_THRESHOLD_MS")

    WEB3_RPC_URL: str = Field(default="", validation_alias="WEB3_RPC_URL")
    WEB3_PRIVATE_KEY: str = Field(default="", validation_alias="WEB3_PRIVATE_KEY")
    WEB3_CHAIN_ID: int = Field(default=1, validation_alias="WEB3_CHAIN_ID")
    WEB3_ROUTER_ADDRESS: str = Field(default="", validation_alias="WEB3_ROUTER_ADDRESS")
    WEB3_WETH_ADDRESS: str = Field(default="", validation_alias="WEB3_WETH_ADDRESS")
    WEB3_BASE_TOKEN_SYMBOL: str = Field(default="USDC", validation_alias="WEB3_BASE_TOKEN_SYMBOL")
    WEB3_MAX_SLIPPAGE_BPS: int = Field(default=150, validation_alias="WEB3_MAX_SLIPPAGE_BPS")
    WEB3_MAX_GAS_GWEI: float = Field(default=150.0, validation_alias="WEB3_MAX_GAS_GWEI")
    WEB3_TX_TIMEOUT_SECONDS: int = Field(default=180, validation_alias="WEB3_TX_TIMEOUT_SECONDS")
    WEB3_TX_GAS_LIMIT: int = Field(default=30000, validation_alias="WEB3_TX_GAS_LIMIT")
    WEB3_SIGNAL_VALUE_WEI: int = Field(default=0, validation_alias="WEB3_SIGNAL_VALUE_WEI")
    # Optional: set to your MetaMask wallet address so trade signals are sent
    # TO your wallet (visible in MetaMask activity) instead of as self-transfers.
    WEB3_METAMASK_ADDRESS: str = Field(default="", validation_alias="WEB3_METAMASK_ADDRESS")
    CRYPTO_TOKEN_MAPPING: dict[str, Any] = Field(
        default_factory=lambda: {
            "USDC": {"address": "", "decimals": 6},
            "WETH": {"address": "", "decimals": 18},
            "ETH": {"address": "", "decimals": 18, "is_native": True},
            "BTC": {"address": "", "decimals": 8},
            "WBTC": {"address": "", "decimals": 8},
            "SOL": {"address": "", "decimals": 9},
            "AVAX": {"address": "", "decimals": 18},
            "BNB": {"address": "", "decimals": 18},
            "ADA": {"address": "", "decimals": 18},
            "DOT": {"address": "", "decimals": 10},
            "NEAR": {"address": "", "decimals": 24},
            "ATOM": {"address": "", "decimals": 6},
            "ALGO": {"address": "", "decimals": 6},
            "LTC": {"address": "", "decimals": 8},
            "BCH": {"address": "", "decimals": 8},
            "ETC": {"address": "", "decimals": 18},
            "XRP": {"address": "", "decimals": 6},
            "XLM": {"address": "", "decimals": 7},
            "HBAR": {"address": "", "decimals": 8},
            "TRX": {"address": "", "decimals": 6},
            "EOS": {"address": "", "decimals": 4},
            "LINK": {"address": "", "decimals": 18},
            "AAVE": {"address": "", "decimals": 18},
            "CRV": {"address": "", "decimals": 18},
            "INJ": {"address": "", "decimals": 18},
            "FIL": {"address": "", "decimals": 18},
            "TIA": {"address": "", "decimals": 6},
            "DOGE": {"address": "", "decimals": 8},
            "SHIB": {"address": "", "decimals": 18},
            "WIF": {"address": "", "decimals": 6},
            "BONK": {"address": "", "decimals": 5},
        },
        validation_alias="CRYPTO_TOKEN_MAPPING",
    )

    KALMAN_DELTA: float = 1e-5
    KALMAN_R: float = 0.001
    MONITOR_ENTRY_ZSCORE: float = Field(default=2.0, validation_alias="MONITOR_ENTRY_ZSCORE")
    MONITOR_MIN_AI_CONFIDENCE: float = Field(default=0.5, validation_alias="MONITOR_MIN_AI_CONFIDENCE")
    ORCHESTRATOR_TIMEOUT_SECONDS: float = Field(default=8.0, validation_alias="ORCHESTRATOR_TIMEOUT_SECONDS")
    MARKET_DATA_TIMEOUT_SECONDS: float = Field(default=8.0, validation_alias="MARKET_DATA_TIMEOUT_SECONDS")
    SPREAD_GUARD_MAX_PCT: float = Field(default=0.003, validation_alias="SPREAD_GUARD_MAX_PCT")
    TAKE_PROFIT_ZSCORE: float = Field(default=0.5, validation_alias="TAKE_PROFIT_ZSCORE")
    STOP_LOSS_ZSCORE: float = Field(default=3.5, validation_alias="STOP_LOSS_ZSCORE")
    SCAN_INTERVAL_SECONDS: int = Field(default=15, validation_alias="SCAN_INTERVAL_SECONDS")
    RISK_DRAWDOWN_ZERO_PCT: float = Field(default=0.15, validation_alias="RISK_DRAWDOWN_ZERO_PCT")
    RISK_SHARPE_FLOOR: float = Field(default=0.5, validation_alias="RISK_SHARPE_FLOOR")
    RISK_MULTIPLIER_CAP_LOW_SHARPE: float = Field(default=0.1, validation_alias="RISK_MULTIPLIER_CAP_LOW_SHARPE")
    RISK_SLIPPAGE_NORMAL: float = Field(default=0.001, validation_alias="RISK_SLIPPAGE_NORMAL")
    RISK_SLIPPAGE_HIGH_VOL: float = Field(default=0.0005, validation_alias="RISK_SLIPPAGE_HIGH_VOL")
    VOLATILITY_ENTROPY_THRESHOLD: float = Field(default=0.8, validation_alias="VOLATILITY_ENTROPY_THRESHOLD")
    VOLATILITY_FALLBACK_ENTROPY: float = Field(default=0.5, validation_alias="VOLATILITY_FALLBACK_ENTROPY")
    MARKET_REGIME_FALLBACK_CONFIDENCE: float = Field(default=0.5, validation_alias="MARKET_REGIME_FALLBACK_CONFIDENCE")
    MARKET_REGIME_BASE_CONFIDENCE: float = Field(default=0.7, validation_alias="MARKET_REGIME_BASE_CONFIDENCE")
    MARKET_REGIME_EMA_BULL_FACTOR: float = Field(default=1.01, validation_alias="MARKET_REGIME_EMA_BULL_FACTOR")
    MARKET_REGIME_EMA_BEAR_FACTOR: float = Field(default=0.99, validation_alias="MARKET_REGIME_EMA_BEAR_FACTOR")
    MARKET_REGIME_VOLATILITY_HIGH: float = Field(default=0.30, validation_alias="MARKET_REGIME_VOLATILITY_HIGH")
    MARKET_REGIME_VOLATILITY_LOW: float = Field(default=0.10, validation_alias="MARKET_REGIME_VOLATILITY_LOW")
    MARKET_REGIME_ENTROPY_SPIKE: float = Field(default=0.85, validation_alias="MARKET_REGIME_ENTROPY_SPIKE")
    ORCH_AGENT_CONFIDENCE_THRESHOLD: float = Field(default=0.5, validation_alias="ORCH_AGENT_CONFIDENCE_THRESHOLD")
    ORCH_FUNDAMENTAL_DEFAULT_SCORE: int = Field(default=50, validation_alias="ORCH_FUNDAMENTAL_DEFAULT_SCORE")
    ORCH_FUNDAMENTAL_VETO_SCORE: int = Field(default=40, validation_alias="ORCH_FUNDAMENTAL_VETO_SCORE")
    ORCH_ACCURACY_LOW_THRESHOLD: float = Field(default=0.4, validation_alias="ORCH_ACCURACY_LOW_THRESHOLD")
    ORCH_ACCURACY_HIGH_THRESHOLD: float = Field(default=0.7, validation_alias="ORCH_ACCURACY_HIGH_THRESHOLD")
    ORCH_ACCURACY_LOW_MULTIPLIER: float = Field(default=0.7, validation_alias="ORCH_ACCURACY_LOW_MULTIPLIER")
    ORCH_ACCURACY_HIGH_MULTIPLIER: float = Field(default=1.1, validation_alias="ORCH_ACCURACY_HIGH_MULTIPLIER")
    GLOBAL_STRATEGY_ACCURACY_DEFAULT: float = Field(default=0.5, validation_alias="GLOBAL_STRATEGY_ACCURACY_DEFAULT")

    WHALE_WATCHER_ENABLED: bool = Field(default=True, validation_alias="WHALE_WATCHER_ENABLED")
    WHALE_WATCHER_ROLLING_WINDOW_SECONDS: int = Field(default=1800, validation_alias="WHALE_WATCHER_ROLLING_WINDOW_SECONDS")
    WHALE_WATCHER_CACHE_TTL_SECONDS: int = Field(default=3600, validation_alias="WHALE_WATCHER_CACHE_TTL_SECONDS")
    WHALE_WATCHER_MAX_EVENTS_PER_SYMBOL: int = Field(default=250, validation_alias="WHALE_WATCHER_MAX_EVENTS_PER_SYMBOL")
    WHALE_WATCHER_MIN_VALUE_USD: float = Field(default=5_000_000.0, validation_alias="WHALE_WATCHER_MIN_VALUE_USD")
    WHALE_WATCHER_EXTREME_VALUE_USD: float = Field(default=50_000_000.0, validation_alias="WHALE_WATCHER_EXTREME_VALUE_USD")
    WHALE_WATCHER_VETO_SCORE: float = Field(default=0.85, validation_alias="WHALE_WATCHER_VETO_SCORE")
    WHALE_WATCHER_VETO_MIN_EVENTS: int = Field(default=2, validation_alias="WHALE_WATCHER_VETO_MIN_EVENTS")
    WHALE_WATCHER_RISK_MULTIPLIER: float = Field(default=0.85, validation_alias="WHALE_WATCHER_RISK_MULTIPLIER")
    WHALE_WATCHER_SUPPORT_MULTIPLIER: float = Field(default=1.05, validation_alias="WHALE_WATCHER_SUPPORT_MULTIPLIER")
    COINTEGRATION_MIN_OBSERVATIONS: int = Field(default=20, validation_alias="COINTEGRATION_MIN_OBSERVATIONS")
    COINTEGRATION_PVALUE_THRESHOLD: float = Field(default=0.05, validation_alias="COINTEGRATION_PVALUE_THRESHOLD")

    # Spec 037: Rolling cointegration stability check. A pair must pass the
    # ADF test in at least COINTEGRATION_ROLLING_PASS_RATE of the rolling
    # windows of size COINTEGRATION_ROLLING_WINDOW (with stride
    # COINTEGRATION_ROLLING_STEP) to be admitted to the live universe.
    # Defaults are calibrated for hourly bars over a ~30-day calibration period.
    COINTEGRATION_ROLLING_WINDOW: int = Field(default=60, validation_alias="COINTEGRATION_ROLLING_WINDOW")
    COINTEGRATION_ROLLING_STEP: int = Field(default=5, validation_alias="COINTEGRATION_ROLLING_STEP")
    COINTEGRATION_ROLLING_PASS_RATE: float = Field(default=0.7, validation_alias="COINTEGRATION_ROLLING_PASS_RATE")
    COINTEGRATION_ROLLING_ENABLED: bool = Field(default=True, validation_alias="COINTEGRATION_ROLLING_ENABLED")

    # Spec 037: Kalman session-boundary handling. We inflate Q (process noise)
    # by KALMAN_Q_SESSION_FACTOR for the first KALMAN_Q_SESSION_BARS bars of
    # each new trading session, then decay linearly back to base. This lets
    # the filter "breathe" through overnight gaps without throwing away the
    # state it has already learned (vs. the legacy P bump which is a one-shot
    # uncertainty boost).
    KALMAN_Q_SESSION_FACTOR: float = Field(default=5.0, validation_alias="KALMAN_Q_SESSION_FACTOR")
    KALMAN_Q_SESSION_BARS: int = Field(default=10, validation_alias="KALMAN_Q_SESSION_BARS")
    KALMAN_USE_Q_INFLATION: bool = Field(default=True, validation_alias="KALMAN_USE_Q_INFLATION")

    # Spec 037: Pair-eligibility gate. Cross-currency / cross-session pairs
    # rarely cointegrate in any economically useful sense; LSE pairs carry
    # 0.5 % stamp duty per buy leg which usually exceeds short-hold edge.
    ACCOUNT_CURRENCY: str = Field(default="EUR", validation_alias="ACCOUNT_CURRENCY")
    BLOCK_CROSS_CURRENCY_PAIRS: bool = Field(default=True, validation_alias="BLOCK_CROSS_CURRENCY_PAIRS")
    BLOCK_LSE_PAIRS_FOR_SHORT_HOLD: bool = Field(default=True, validation_alias="BLOCK_LSE_PAIRS_FOR_SHORT_HOLD")
    PAIR_MAX_ROUND_TRIP_COST_PCT: float = Field(default=0.0125, validation_alias="PAIR_MAX_ROUND_TRIP_COST_PCT")

    # Spec 038: when True, treat XETRA, EURONEXT, BORSA_ITALIANA and SIX as
    # the same session group ("EU continental"). Their wall-clock windows
    # overlap by ~7-8 hours so cross-venue pairs (ASML.AS / SAP.DE,
    # MC.PA / NESN.SW) can be admitted. Default False keeps the strict
    # market_id rule in place - opt in per deployment after verifying that
    # cointegration holds across the venue boundary for your hourly bar
    # frequency.
    ALLOW_EU_CONTINENTAL_OVERLAP: bool = Field(
        default=False, validation_alias="ALLOW_EU_CONTINENTAL_OVERLAP"
    )

    # Spec 038: cost-aware z-score gate. When enabled, the entry z-score
    # threshold for a pair is scaled up proportionally to its estimated
    # round-trip cost. Pairs with higher friction (HK, Swiss, cross-currency)
    # require more statistical edge before the bot fires a signal. The
    # baseline is the cost level at which no scaling is applied; pairs
    # cheaper than the baseline trade at the global threshold unchanged.
    MONITOR_ENTRY_ZSCORE_COST_SCALING_ENABLED: bool = Field(
        default=False, validation_alias="MONITOR_ENTRY_ZSCORE_COST_SCALING_ENABLED"
    )
    MONITOR_ENTRY_ZSCORE_COST_BASELINE: float = Field(
        default=0.0015, validation_alias="MONITOR_ENTRY_ZSCORE_COST_BASELINE"
    )
    MONITOR_ENTRY_ZSCORE_COST_SCALING_CAP: float = Field(
        default=3.0, validation_alias="MONITOR_ENTRY_ZSCORE_COST_SCALING_CAP"
    )

    PORTFOLIO_RISK_FREE_RATE: float = Field(default=0.02, validation_alias="PORTFOLIO_RISK_FREE_RATE")

    MAX_SECTOR_EXPOSURE: float = 0.30
    PAIR_SECTORS: dict = {
        # --- Original equity pairs ---
        'KO_PEP': 'Consumer Staples', 'MA_V': 'Financials', 'XOM_CVX': 'Energy',
        'JPM_BAC': 'Financials', 'WMT_TGT': 'Consumer Staples', 'GOOGL_GOOG': 'Technology',
        'MSFT_AAPL': 'Technology', 'DAL_UAL': 'Industrials', 'UPS_FDX': 'Industrials',
        'HD_LOW': 'Consumer Discretionary', 'GM_F': 'Consumer Discretionary',
        'INTC_AMD': 'Technology', 'PYPL_AFRM': 'Financials',
        'NKE_ADS.DE': 'Consumer Discretionary', 'PG_CL': 'Consumer Staples',
        'BA_AIR.PA': 'Industrials', 'T_VZ': 'Telecommunications',
        'VLO_MPC': 'Energy', 'COF_SYF': 'Financials', 'GS_MS': 'Financials',
        'BTCE.DE_ZETH.DE': 'Crypto ETNs',
        # --- New high-volatility equity pairs ---
        'NVDA_AMD': 'Technology',           # GPU/AI chip duopoly
        'TSLA_RIVN': 'Consumer Discretionary',  # EV pair
        'COIN_MSTR': 'Financials',          # Bitcoin-proxy stocks
        'META_SNAP': 'Technology',          # Social media
        'NFLX_DIS': 'Consumer Discretionary',   # Streaming wars
        'UBER_LYFT': 'Consumer Discretionary',  # Rideshare duopoly
        'MU_SMCI': 'Technology',            # Memory / AI servers
        'SBUX_MCD': 'Consumer Discretionary',   # QSR
        'SLB_HAL': 'Energy',               # Oilfield services
        'AMZN_SHOP': 'Consumer Discretionary',  # E-commerce
        'PLTR_BBAI': 'Technology',          # AI / defence analytics
        'BRK-B_JPM': 'Financials',          # Financial giants
        # --- Global Expansion Pairs ---
        'ASML.AS_SAP.DE': 'Technology',     # European tech giants
        'SHEL.L_BP.L': 'Energy',           # UK Energy pair
        'MC.PA_RMS.PA': 'Luxury',          # French luxury
        '9988.HK_0700.HK': 'Technology',    # HK Big Tech (Alibaba/Tencent)
        '3690.HK_9999.HK': 'Technology',    # HK Consumer Tech
        # --- Crypto: Layer 1 / Smart-contract platforms ---
        'ETH-USD_BTC-USD': 'Crypto L1',     'BTC-USD_ETH-USD': 'Crypto L1',
        'ETH-USD_SOL-USD': 'Crypto L1',     'SOL-USD_ETH-USD': 'Crypto L1',
        'SOL-USD_AVAX-USD': 'Crypto L1',    'AVAX-USD_SOL-USD': 'Crypto L1',
        'BNB-USD_ETH-USD': 'Crypto L1',     'ETH-USD_BNB-USD': 'Crypto L1',
        'ADA-USD_DOT-USD': 'Crypto L1',     'DOT-USD_ADA-USD': 'Crypto L1',
        'ADA-USD_SOL-USD': 'Crypto L1',     'SOL-USD_ADA-USD': 'Crypto L1',
        'AVAX-USD_DOT-USD': 'Crypto L1',    'DOT-USD_AVAX-USD': 'Crypto L1',
        'NEAR-USD_SOL-USD': 'Crypto L1',    'SOL-USD_NEAR-USD': 'Crypto L1',
        'ATOM-USD_DOT-USD': 'Crypto L1',    'DOT-USD_ATOM-USD': 'Crypto L1',
        'AVAX-USD_ATOM-USD': 'Crypto L1',   'ATOM-USD_AVAX-USD': 'Crypto L1',
        'ADA-USD_ALGO-USD': 'Crypto L1',    'ALGO-USD_ADA-USD': 'Crypto L1',
        'ETH-USD_ATOM-USD': 'Crypto L1',    'ATOM-USD_ETH-USD': 'Crypto L1',
        'ALGO-USD_NEAR-USD': 'Crypto L1',   'NEAR-USD_ALGO-USD': 'Crypto L1',
        # --- Crypto: Store of Value / Bitcoin forks ---
        'BTC-USD_LTC-USD': 'Crypto Store of Value',  'LTC-USD_BTC-USD': 'Crypto Store of Value',
        'BTC-USD_BCH-USD': 'Crypto Store of Value',  'BCH-USD_BTC-USD': 'Crypto Store of Value',
        'LTC-USD_BCH-USD': 'Crypto Store of Value',  'BCH-USD_LTC-USD': 'Crypto Store of Value',
        'ETC-USD_LTC-USD': 'Crypto Store of Value',  'LTC-USD_ETC-USD': 'Crypto Store of Value',
        # --- Crypto: Payments / Enterprise DLT ---
        'XRP-USD_XLM-USD': 'Crypto Payments',   'XLM-USD_XRP-USD': 'Crypto Payments',
        'XRP-USD_HBAR-USD': 'Crypto Payments',  'HBAR-USD_XRP-USD': 'Crypto Payments',
        'TRX-USD_EOS-USD': 'Crypto Payments',   'EOS-USD_TRX-USD': 'Crypto Payments',
        'HBAR-USD_ALGO-USD': 'Crypto Payments', 'ALGO-USD_HBAR-USD': 'Crypto Payments',
        # --- Crypto: DeFi ---
        'AAVE-USD_LINK-USD': 'Crypto DeFi',  'LINK-USD_AAVE-USD': 'Crypto DeFi',
        'AAVE-USD_CRV-USD': 'Crypto DeFi',   'CRV-USD_AAVE-USD': 'Crypto DeFi',
        'LINK-USD_DOT-USD': 'Crypto DeFi',   'DOT-USD_LINK-USD': 'Crypto DeFi',
        'INJ-USD_ATOM-USD': 'Crypto DeFi',   'ATOM-USD_INJ-USD': 'Crypto DeFi',
        # --- Crypto: Storage / Utility ---
        'FIL-USD_ATOM-USD': 'Crypto Utility', 'ATOM-USD_FIL-USD': 'Crypto Utility',
        'TIA-USD_ATOM-USD': 'Crypto Utility', 'ATOM-USD_TIA-USD': 'Crypto Utility',
        # --- Crypto: Memes ---
        'DOGE-USD_SHIB-USD': 'Crypto Memes', 'SHIB-USD_DOGE-USD': 'Crypto Memes',
        'WIF-USD_BONK-USD': 'Crypto Memes',  'BONK-USD_WIF-USD': 'Crypto Memes',
    }

    EU_HEDGE_MAPPINGS: dict = {
        "SPY": "XSPS.L", "QQQ": "SQQQ.L", "IWM": "R2SC.L", "DIA": "DOG"
    }

    ARBITRAGE_PAIRS: list = [
        # --- YOUR ORIGINAL CLASSIC PAIRS ---
        {'ticker_a': 'KO',      'ticker_b': 'PEP'},
        {'ticker_a': 'MA',      'ticker_b': 'V'},
        {'ticker_a': 'XOM',     'ticker_b': 'CVX'},
        {'ticker_a': 'JPM',     'ticker_b': 'BAC'},
        {'ticker_a': 'WMT',     'ticker_b': 'TGT'},
        {'ticker_a': 'GOOGL',   'ticker_b': 'GOOG'},
        {'ticker_a': 'MSFT',    'ticker_b': 'AAPL'},
        {'ticker_a': 'DAL',     'ticker_b': 'UAL'},
        {'ticker_a': 'UPS',     'ticker_b': 'FDX'},
        {'ticker_a': 'HD',      'ticker_b': 'LOW'},
        {'ticker_a': 'GM',      'ticker_b': 'F'},
        {'ticker_a': 'INTC',    'ticker_b': 'AMD'},
        {'ticker_a': 'PYPL',    'ticker_b': 'AFRM'},
        {'ticker_a': 'NKE',     'ticker_b': 'ADS.DE'},   # switched from ADDYY ADR → primary Xetra listing
        {'ticker_a': 'PG',      'ticker_b': 'CL'},
        {'ticker_a': 'BA',      'ticker_b': 'AIR.PA'},
        {'ticker_a': 'T',       'ticker_b': 'VZ'},
        {'ticker_a': 'VLO',     'ticker_b': 'MPC'},
        {'ticker_a': 'COF',     'ticker_b': 'SYF'},
        {'ticker_a': 'GS',      'ticker_b': 'MS'},
        {'ticker_a': 'BTCE.DE', 'ticker_b': 'ZETH.DE'},
        
        # --- YOUR ORIGINAL HIGH-VOL PAIRS ---
        {'ticker_a': 'NVDA',    'ticker_b': 'AMD'},
        {'ticker_a': 'TSLA',    'ticker_b': 'RIVN'},
        {'ticker_a': 'COIN',    'ticker_b': 'MSTR'},
        {'ticker_a': 'META',    'ticker_b': 'SNAP'},
        {'ticker_a': 'NFLX',    'ticker_b': 'DIS'},
        {'ticker_a': 'UBER',    'ticker_b': 'LYFT'},
        {'ticker_a': 'MU',      'ticker_b': 'SMCI'},
        {'ticker_a': 'SBUX',    'ticker_b': 'MCD'},
        {'ticker_a': 'SLB',     'ticker_b': 'HAL'},
        {'ticker_a': 'AMZN',    'ticker_b': 'SHOP'},
        {'ticker_a': 'PLTR',    'ticker_b': 'BBAI'},
        {'ticker_a': 'BRK-B',   'ticker_b': 'JPM'},

        # German Automotive (High Correlation)
        {"ticker_a": "BMW.DE", "ticker_b": "MBG.DE"},        # BMW vs Mercedes-Benz
        {"ticker_a": "VOW3.DE", "ticker_b": "PAH3.DE"},      # VW vs Porsche SE
        {"ticker_a": "CON.DE", "ticker_b": "PUM.DE"},        # Continental vs Puma (Consumer/Industrial)
        
        # European Banking (High Beta)
        {"ticker_a": "DBK.DE", "ticker_b": "CBK.DE"},        # Deutsche Bank vs Commerzbank
        {"ticker_a": "BNP.PA", "ticker_b": "GLE.PA"},        # BNP Paribas vs Societe Generale
        {"ticker_a": "ACA.PA", "ticker_b": "BNP.PA"},        # Credit Agricole vs BNP Paribas
        
        # French Luxury (The "Gold Standard" for Pairs)
        {"ticker_a": "MC.PA", "ticker_b": "RMS.PA"},         # LVMH vs Hermes
        {"ticker_a": "MC.PA", "ticker_b": "KER.PA"},         # LVMH vs Kering (Gucci)
        {"ticker_a": "OR.PA", "ticker_b": "EL.PA"},          # L'Oreal vs EssilorLuxottica
        
        # Energy & Utilities
        {"ticker_a": "RWE.DE", "ticker_b": "EOAN.DE"},       # RWE vs E.ON
        {"ticker_a": "ENGI.PA", "ticker_b": "ORA.PA"},       # Engie vs Orange

        # Energy & Mining (Commodity Driven)
        {"ticker_a": "SHEL.L", "ticker_b": "BP.L"},          # Shell vs BP
        {"ticker_a": "RIO.L", "ticker_b": "BHP.L"},          # Rio Tinto vs BHP
        {"ticker_a": "AAL.L", "ticker_b": "GLEN.L"},         # Anglo American vs Glencore
        
        # Banking & Insurance
        {"ticker_a": "LLOY.L", "ticker_b": "BARC.L"},        # Lloyds vs Barclays
        {"ticker_a": "HSBA.L", "ticker_b": "STAN.L"},        # HSBC vs Standard Chartered
        {"ticker_a": "AV.L", "ticker_b": "LGEN.L"},          # Aviva vs Legal & General
        
        # Consumer & Retail
        {"ticker_a": "TSCO.L", "ticker_b": "SBRY.L"},        # Tesco vs Sainsbury’s
        {"ticker_a": "ULVR.L", "ticker_b": "RKT.L"},         # Unilever vs Reckitt
        {"ticker_a": "BATS.L", "ticker_b": "IMB.L"},         # British Am. Tobacco vs Imperial Brands

        # Semiconductors (Very High Correlation)
        {"ticker_a": "ASML.AS", "ticker_b": "ASM.AS"},       # ASML vs ASM International (Euronext)
        {"ticker_a": "NVDA", "ticker_b": "AMD"},             # Nvidia vs AMD
        {"ticker_a": "LRCX", "ticker_b": "AMAT"},            # Lam Research vs Applied Materials

        # Big Tech Proxies
        {"ticker_a": "GOOGL", "ticker_b": "META"},           # Alphabet vs Meta
        {"ticker_a": "MSFT", "ticker_b": "AAPL"},            # Microsoft vs Apple

        # Payments & Fintech
        {"ticker_a": "V", "ticker_b": "MA"},                 # Visa vs Mastercard
        # PYPL/SQ removed 2026-04-28: SQ (Block Inc.) returning "possibly delisted" from Yahoo Finance.
        # Re-add once correct current ticker is confirmed.

        # --- SEMICONDUCTORS & HARDWARE (Expanded) ---
        {'ticker_a': 'AVGO',    'ticker_b': 'QCOM'},
        {'ticker_a': 'AMAT',    'ticker_b': 'LRCX'},
        {'ticker_a': 'KLAC',    'ticker_b': 'ASML'},
        {'ticker_a': 'TXN',     'ticker_b': 'ADI'},
        {'ticker_a': 'MCHP',    'ticker_b': 'NXPI'},
        {'ticker_a': 'WDC',     'ticker_b': 'STX'},
        {'ticker_a': 'HPQ',     'ticker_b': 'HPE'},

        # --- SAAS & CLOUD SOFTWARE ---
        {'ticker_a': 'CRM',     'ticker_b': 'ADBE'},
        {'ticker_a': 'NOW',     'ticker_b': 'TEAM'},
        {'ticker_a': 'SNOW',    'ticker_b': 'PLTR'},
        {'ticker_a': 'WDAY',    'ticker_b': 'SAP'},
        {'ticker_a': 'ADSK',    'ticker_b': 'PTC'},
        {'ticker_a': 'ZS',      'ticker_b': 'CRWD'},
        {'ticker_a': 'PANW',    'ticker_b': 'FTNT'},
        {'ticker_a': 'DDOG',    'ticker_b': 'NET'},
        {'ticker_a': 'OKTA',    'ticker_b': 'MDB'},

        # --- FINTECH & BANKING ---
        {'ticker_a': 'C',       'ticker_b': 'WFC'},
        {'ticker_a': 'BLK',     'ticker_b': 'TROW'},
        {'ticker_a': 'SCHW',    'ticker_b': 'IBKR'},
        {'ticker_a': 'PNC',     'ticker_b': 'USB'},
        {'ticker_a': 'BX',      'ticker_b': 'KKR'},
        {'ticker_a': 'SPGI',    'ticker_b': 'MCO'},
        {'ticker_a': 'CME',     'ticker_b': 'ICE'},
        {'ticker_a': 'MET',     'ticker_b': 'PRU'},
        {'ticker_a': 'AIG',     'ticker_b': 'TRV'},

        # --- CONSUMER RETAIL & LUXURY ---
        {'ticker_a': 'COST',    'ticker_b': 'BJ'},
        {'ticker_a': 'LULU',    'ticker_b': 'NKE'},
        {'ticker_a': 'DG',      'ticker_b': 'DLTR'},
        {'ticker_a': 'TJX',     'ticker_b': 'ROST'},
        {'ticker_a': 'EL',      'ticker_b': 'ULTA'},
        {'ticker_a': 'BKNG',    'ticker_b': 'EXPE'},
        {'ticker_a': 'MAR',     'ticker_b': 'HLT'},
        {'ticker_a': 'YUM',     'ticker_b': 'QSR'},
        {'ticker_a': 'MDLZ',    'ticker_b': 'HSY'},
        {'ticker_a': 'CL',      'ticker_b': 'KMB'},

        # --- ENERGY & INDUSTRIALS ---
        {'ticker_a': 'PSX',     'ticker_b': 'VLO'},
        {'ticker_a': 'COP',     'ticker_b': 'EOG'},
        {'ticker_a': 'CAT',     'ticker_b': 'DE'},
        {'ticker_a': 'LMT',     'ticker_b': 'NOC'},
        {'ticker_a': 'GD',      'ticker_b': 'RTX'},
        {'ticker_a': 'WM',      'ticker_b': 'RSG'},
        {'ticker_a': 'UNP',     'ticker_b': 'NSC'},
        {'ticker_a': 'CSX',     'ticker_b': 'CP'},
        {'ticker_a': 'ETN',     'ticker_b': 'EMR'},
        {'ticker_a': 'URI',     'ticker_b': 'HRI'},
        {'ticker_a': 'VMC',     'ticker_b': 'MLM'},
        {'ticker_a': 'GE',      'ticker_b': 'HON'},

        # --- PHARMA & HEALTHCARE ---
        {'ticker_a': 'PFE',     'ticker_b': 'MRK'},
        {'ticker_a': 'JNJ',     'ticker_b': 'ABBV'},
        {'ticker_a': 'LLY',     'ticker_b': 'NVO'},
        {'ticker_a': 'UNH',     'ticker_b': 'ELV'},
        {'ticker_a': 'CI',      'ticker_b': 'HUM'},
        {'ticker_a': 'ISRG',    'ticker_b': 'SYK'},
        {'ticker_a': 'BSX',     'ticker_b': 'MDT'},
        {'ticker_a': 'TMO',     'ticker_b': 'A'},
        {'ticker_a': 'AMGN',    'ticker_b': 'GILD'},
        {'ticker_a': 'ZTS',     'ticker_b': 'IDXX'},
        {'ticker_a': 'REGN',    'ticker_b': 'VRTX'},
        {'ticker_a': 'MCK',     'ticker_b': 'COR'},

        # --- REAL ESTATE (REITS) & UTILITIES ---
        {'ticker_a': 'AMT',     'ticker_b': 'CCI'},
        {'ticker_a': 'PLD',     'ticker_b': 'PSA'},
        {'ticker_a': 'O',       'ticker_b': 'ADC'},
        {'ticker_a': 'DUK',     'ticker_b': 'SO'},
        {'ticker_a': 'NEE',     'ticker_b': 'D'},
        {'ticker_a': 'AEP',     'ticker_b': 'SRE'},
        {'ticker_a': 'CMCSA',   'ticker_b': 'CHTR'},
        {'ticker_a': 'SPOT',    'ticker_b': 'WMG'}
    ]

    # Crypto pairs traded 24/7 — including weekends and outside US equity
    # hours. The monitor loads these alongside ARBITRAGE_PAIRS in production
    # mode; process_pair's `is_crypto` guard makes sure equity pairs pause
    # off-hours while crypto pairs keep scanning.
    CRYPTO_TEST_PAIRS: list = [
        {'ticker_a': 'BTC-USD',   'ticker_b': 'ETH-USD'},
        {'ticker_a': 'ETH-USD',   'ticker_b': 'BTC-USD'},
        # --- Layer 1 / smart-contract platforms ---
        # {'ticker_a': 'ETH-USD',   'ticker_b': 'BTC-USD'},
        # {'ticker_a': 'SOL-USD',   'ticker_b': 'AVAX-USD'},
        # {'ticker_a': 'ETH-USD',   'ticker_b': 'SOL-USD'},
        # {'ticker_a': 'BNB-USD',   'ticker_b': 'ETH-USD'},
        # {'ticker_a': 'ADA-USD',   'ticker_b': 'DOT-USD'},
        # {'ticker_a': 'ADA-USD',   'ticker_b': 'SOL-USD'},
        # {'ticker_a': 'AVAX-USD',  'ticker_b': 'DOT-USD'},
        # {'ticker_a': 'NEAR-USD',  'ticker_b': 'SOL-USD'},
        # {'ticker_a': 'ATOM-USD',  'ticker_b': 'DOT-USD'},
        # {'ticker_a': 'AVAX-USD',  'ticker_b': 'ATOM-USD'},
        # {'ticker_a': 'ADA-USD',   'ticker_b': 'ALGO-USD'},
        # {'ticker_a': 'ETH-USD',   'ticker_b': 'ATOM-USD'},
        # # --- Stores of value / Bitcoin forks ---
        # {'ticker_a': 'BTC-USD',   'ticker_b': 'LTC-USD'},
        # {'ticker_a': 'BTC-USD',   'ticker_b': 'BCH-USD'},
        # {'ticker_a': 'LTC-USD',   'ticker_b': 'BCH-USD'},
        # {'ticker_a': 'ETC-USD',   'ticker_b': 'LTC-USD'},
        # # --- Payments / XRP-style ---
        # {'ticker_a': 'XRP-USD',   'ticker_b': 'XLM-USD'},
        # {'ticker_a': 'XRP-USD',   'ticker_b': 'HBAR-USD'},  # Competing payment networks
        # {'ticker_a': 'TRX-USD',   'ticker_b': 'EOS-USD'},
        # # --- DeFi (UNI-USD removed — delisted on Yahoo Finance) ---
        # {'ticker_a': 'AAVE-USD',  'ticker_b': 'LINK-USD'},  # replaces UNI/LINK
        # {'ticker_a': 'AAVE-USD',  'ticker_b': 'CRV-USD'},   # replaces UNI/AAVE
        # {'ticker_a': 'LINK-USD',  'ticker_b': 'DOT-USD'},
        # {'ticker_a': 'INJ-USD',   'ticker_b': 'ATOM-USD'},  # Cosmos DeFi
        # # --- Storage / utility ---
        # {'ticker_a': 'FIL-USD',   'ticker_b': 'ATOM-USD'},
        # # --- Cosmos ecosystem ---
        # {'ticker_a': 'TIA-USD',   'ticker_b': 'ATOM-USD'},  # Celestia modular L1
        # # --- Infrastructure / enterprise ---
        # {'ticker_a': 'HBAR-USD',  'ticker_b': 'ALGO-USD'},  # Enterprise DLT pair
        # # --- Memes (high vol, mean-reverting spreads) ---
        # {'ticker_a': 'DOGE-USD',  'ticker_b': 'SHIB-USD'},
        # {'ticker_a': 'WIF-USD',   'ticker_b': 'BONK-USD'},  # Solana memes
        # # --- Newer L1s ---
        # {'ticker_a': 'ALGO-USD',  'ticker_b': 'NEAR-USD'},
        # # P-09 (2026-04-26): Removed pairs containing tickers that yfinance
        # # consistently reports as delisted (no spot data available):
        # #   SUI-USD, APT-USD (paired with SUI), ARB-USD, OP-USD, POL-USD,
        # #   STX-USD, GRT-USD, RNDR-USD, FET-USD (paired with RNDR),
        # #   JUP-USD, PEPE-USD.
        # # Re-add them once Yahoo Finance restores their feeds.
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

    @property
    def web3_enabled(self) -> bool:
        return bool(
            self.WEB3_RPC_URL.strip()
            and self.WEB3_PRIVATE_KEY.strip()
            and self.WEB3_ROUTER_ADDRESS.strip()
        )

    @property
    def dashboard_allowed_origins(self) -> list[str]:
        raw = self.DASHBOARD_ALLOWED_ORIGINS.strip()
        if not raw:
            return [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:8080",
                "http://127.0.0.1:8080",
            ]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def dashboard_allowed_origin_regex(self) -> str | None:
        raw = self.DASHBOARD_ALLOWED_ORIGIN_REGEX.strip()
        if raw:
            return raw
        return (
            r"^https?://("
            r"localhost|127\.0\.0\.1|\[::1\]|"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}|"
            r"192\.168\.\d{1,3}\.\d{1,3}|"
            r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|"
            r"[A-Za-z0-9-]+(?:\.local)?"
            r")(?::\d{1,5})?$"
        )

    @model_validator(mode="after")
    def validate_secrets(self):
        if not self.POSTGRES_PASSWORD or self.POSTGRES_PASSWORD == "bot_pass":
            raise ValueError("POSTGRES_PASSWORD must be set to a non-default secret")
        dashboard_token = self.DASHBOARD_TOKEN.strip().strip('"').strip("'")
        if not dashboard_token or dashboard_token == "arbi-elite-2026":
            raise ValueError("DASHBOARD_TOKEN must be set to a non-default secret")
        if "*" in self.dashboard_allowed_origins and not self.DEV_MODE:
            raise ValueError("DASHBOARD_ALLOWED_ORIGINS='*' is only allowed when DEV_MODE=true")
        return self

settings = Settings()

# Apply runtime overrides for the trading-pair universe (dashboard-editable).
_override = _load_pairs_override()
if _override:
    if isinstance(_override.get("ARBITRAGE_PAIRS"), list):
        settings.ARBITRAGE_PAIRS = _override["ARBITRAGE_PAIRS"]
    if isinstance(_override.get("CRYPTO_TEST_PAIRS"), list):
        settings.CRYPTO_TEST_PAIRS = _override["CRYPTO_TEST_PAIRS"]

_settings_override = _load_settings_override()
if _settings_override:
    for _key, _value in _settings_override.items():
        if hasattr(settings, _key):
            setattr(settings, _key, _value)
