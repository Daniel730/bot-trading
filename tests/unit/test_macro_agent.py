import pytest
import pandas as pd
from unittest.mock import AsyncMock
from src.agents.macro_economic_agent import MacroEconomicAgent

def test_macro_agent_risk_on_signal():
    agent = MacroEconomicAgent()

    # Low rates, low inflation -> Risk On
    signal = agent.analyze_market_state(interest_rate=0.03, inflation=0.02)
    assert signal == "RISK_ON"

def test_macro_agent_risk_off_signal():
    agent = MacroEconomicAgent()

    # High rates or high inflation -> Risk Off
    signal = agent.analyze_market_state(interest_rate=0.06, inflation=0.05)
    assert signal == "RISK_OFF"

def test_threshold_logic():
    agent = MacroEconomicAgent(rate_threshold=0.05, inflation_threshold=0.04)

    assert agent.analyze_market_state(0.04, 0.03) == "RISK_ON"
    assert agent.analyze_market_state(0.051, 0.03) == "RISK_OFF"


# ---------------------------------------------------------------------------
# analyze_market_state – boundary and edge cases (PR docstring coverage)
# ---------------------------------------------------------------------------

def test_analyze_market_state_exactly_at_rate_threshold_is_risk_on():
    # Strict greater-than: equal to threshold => RISK_ON
    agent = MacroEconomicAgent(rate_threshold=0.05, inflation_threshold=0.04)
    assert agent.analyze_market_state(0.05, 0.02) == "RISK_ON"

def test_analyze_market_state_exactly_at_inflation_threshold_is_risk_on():
    agent = MacroEconomicAgent(rate_threshold=0.05, inflation_threshold=0.04)
    assert agent.analyze_market_state(0.03, 0.04) == "RISK_ON"

def test_analyze_market_state_rate_just_above_threshold_is_risk_off():
    agent = MacroEconomicAgent(rate_threshold=0.05, inflation_threshold=0.04)
    assert agent.analyze_market_state(0.0501, 0.02) == "RISK_OFF"

def test_analyze_market_state_inflation_just_above_threshold_is_risk_off():
    agent = MacroEconomicAgent(rate_threshold=0.05, inflation_threshold=0.04)
    assert agent.analyze_market_state(0.03, 0.0401) == "RISK_OFF"

def test_analyze_market_state_both_above_threshold_is_risk_off():
    agent = MacroEconomicAgent(rate_threshold=0.05, inflation_threshold=0.04)
    assert agent.analyze_market_state(0.07, 0.06) == "RISK_OFF"

def test_analyze_market_state_zero_values_are_risk_on():
    agent = MacroEconomicAgent()
    assert agent.analyze_market_state(0.0, 0.0) == "RISK_ON"

def test_analyze_market_state_custom_thresholds():
    agent = MacroEconomicAgent(rate_threshold=0.10, inflation_threshold=0.08)
    assert agent.analyze_market_state(0.09, 0.07) == "RISK_ON"
    assert agent.analyze_market_state(0.11, 0.07) == "RISK_OFF"


# ---------------------------------------------------------------------------
# _extract_series – documented behaviour (PR docstring coverage)
# ---------------------------------------------------------------------------

class TestExtractSeries:
    def test_series_input_returns_itself_without_nans(self):
        s = pd.Series([1.0, float("nan"), 3.0], name="SPY")
        result = MacroEconomicAgent._extract_series(s, "SPY")
        assert list(result) == [1.0, 3.0]

    def test_empty_dataframe_returns_empty_float_series(self):
        df = pd.DataFrame()
        result = MacroEconomicAgent._extract_series(df, "SPY")
        assert isinstance(result, pd.Series)
        assert len(result) == 0
        assert result.dtype == "float64"

    def test_none_dataframe_returns_empty_float_series(self):
        result = MacroEconomicAgent._extract_series(None, "SPY")
        assert isinstance(result, pd.Series)
        assert len(result) == 0

    def test_ticker_column_is_preferred(self):
        df = pd.DataFrame({"SPY": [100.0, 101.0], "QQQ": [200.0, 201.0]})
        result = MacroEconomicAgent._extract_series(df, "SPY")
        assert list(result) == [100.0, 101.0]

    def test_close_column_used_when_no_ticker_column(self):
        df = pd.DataFrame({"Close": [150.0, 151.0], "Volume": [1000, 2000]})
        result = MacroEconomicAgent._extract_series(df, "AAPL")
        assert list(result) == [150.0, 151.0]

    def test_single_column_df_used_when_no_close_or_ticker(self):
        df = pd.DataFrame({"PriceData": [10.0, 20.0, 30.0]})
        result = MacroEconomicAgent._extract_series(df, "XYZ")
        assert list(result) == [10.0, 20.0, 30.0]

    def test_nans_dropped_from_ticker_column(self):
        df = pd.DataFrame({"AAPL": [100.0, float("nan"), 102.0]})
        result = MacroEconomicAgent._extract_series(df, "AAPL")
        assert list(result) == [100.0, 102.0]

    def test_multi_column_no_ticker_no_close_returns_empty(self):
        df = pd.DataFrame({"Open": [1.0, 2.0], "High": [3.0, 4.0]})
        result = MacroEconomicAgent._extract_series(df, "AAPL")
        assert isinstance(result, pd.Series)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# get_ticker_regime – documented behaviour (PR docstring coverage)
# ---------------------------------------------------------------------------

def _make_price_series(prices: list) -> pd.Series:
    return pd.Series(prices, index=pd.date_range("2025-01-01", periods=len(prices), freq="D"))


@pytest.mark.asyncio
async def test_get_ticker_regime_extreme_volatility_on_large_drop():
    """If most recent daily drop > 3%, regime is EXTREME_VOLATILITY."""
    agent = MacroEconomicAgent()
    # Build a 55-day series where last bar drops ~5%
    prices = [100.0] * 54 + [95.0]
    series = _make_price_series(prices)

    mock_ds = AsyncMock()
    mock_ds.get_historical_data_async = AsyncMock(return_value=series)
    agent.data_service = mock_ds

    regime = await agent.get_ticker_regime("SPY")
    assert regime == "EXTREME_VOLATILITY"


@pytest.mark.asyncio
async def test_get_ticker_regime_bullish_when_sma20_above_sma50():
    """SMA20 > SMA50 → BULLISH."""
    agent = MacroEconomicAgent()
    # Uptrend: 55 gradually rising prices
    prices = [float(i) for i in range(1, 56)]
    series = _make_price_series(prices)

    mock_ds = AsyncMock()
    mock_ds.get_historical_data_async = AsyncMock(return_value=series)
    agent.data_service = mock_ds

    regime = await agent.get_ticker_regime("SPY")
    assert regime == "BULLISH"


@pytest.mark.asyncio
async def test_get_ticker_regime_bearish_when_sma20_below_sma50():
    """SMA20 < SMA50 → BEARISH."""
    agent = MacroEconomicAgent()
    # Downtrend: 55 declining prices
    prices = [float(55 - i) for i in range(55)]
    series = _make_price_series(prices)

    mock_ds = AsyncMock()
    mock_ds.get_historical_data_async = AsyncMock(return_value=series)
    agent.data_service = mock_ds

    regime = await agent.get_ticker_regime("SPY")
    assert regime == "BEARISH"


@pytest.mark.asyncio
async def test_get_ticker_regime_defaults_bearish_on_insufficient_data():
    """Less than 2 price points → BEARISH."""
    agent = MacroEconomicAgent()
    series = _make_price_series([100.0])

    mock_ds = AsyncMock()
    mock_ds.get_historical_data_async = AsyncMock(return_value=series)
    agent.data_service = mock_ds

    regime = await agent.get_ticker_regime("SPY")
    assert regime == "BEARISH"


@pytest.mark.asyncio
async def test_get_ticker_regime_returns_bearish_on_exception():
    """If data service throws, get_ticker_regime returns BEARISH."""
    agent = MacroEconomicAgent()

    mock_ds = AsyncMock()
    mock_ds.get_historical_data_async = AsyncMock(side_effect=RuntimeError("network error"))
    agent.data_service = mock_ds

    regime = await agent.get_ticker_regime("SPY")
    assert regime == "BEARISH"


@pytest.mark.asyncio
async def test_get_ticker_regime_bullish_when_insufficient_for_sma50():
    """When SMA50 is NaN (< 50 data points), returns BULLISH."""
    agent = MacroEconomicAgent()
    # 25 flat prices – SMA50 will be NaN; no flash-crash (prices flat)
    prices = [100.0] * 25
    series = _make_price_series(prices)

    mock_ds = AsyncMock()
    mock_ds.get_historical_data_async = AsyncMock(return_value=series)
    agent.data_service = mock_ds

    regime = await agent.get_ticker_regime("SPY")
    assert regime == "BULLISH"


@pytest.mark.asyncio
async def test_get_ticker_regime_calls_historical_data_with_60d_1d():
    """Verifies that get_historical_data_async is called with the right params."""
    agent = MacroEconomicAgent()
    prices = [100.0] * 55
    series = _make_price_series(prices)

    mock_ds = AsyncMock()
    mock_ds.get_historical_data_async = AsyncMock(return_value=series)
    agent.data_service = mock_ds

    await agent.get_ticker_regime("QQQ")

    mock_ds.get_historical_data_async.assert_called_once_with(["QQQ"], "60d", "1d")
