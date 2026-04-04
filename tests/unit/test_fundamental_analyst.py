import pytest
import asyncio
from src.agents.fundamental_analyst import FundamentalAnalyst

@pytest.fixture
def analyst():
    return FundamentalAnalyst()

@pytest.mark.anyio
async def test_prosecutor_detects_litigation(analyst):
    sections = {"Item 3": "The company is involved in major material litigation with several vendors."}
    result = await analyst.prosecutor_analyze("AAPL", sections)
    assert any("litigation" in f['factor'].lower() for f in result['findings'])
    assert result['findings'][0]['source'] == "Item 3"
    assert "litigation" in result['findings'][0]['snippet'].lower()
    assert result['severity_score'] > 0

@pytest.mark.anyio
async def test_defender_detects_liquidity(analyst):
    sections = {"Item 7": "Management believes it has sufficient liquidity to fund operations for 12 months."}
    result = await analyst.defender_analyze("AAPL", sections)
    assert any("liquidity" in f['factor'].lower() for f in result['findings'])
    assert result['findings'][0]['source'] == "Item 7"
    assert result['resilience_score'] > 0

@pytest.mark.anyio
async def test_no_go_on_high_risk(analyst):
    # Setup sections with high risk (litigation + default) and low strength
    sections = {
        "Item 1A": "Risks of default on high indebtedness.",
        "Item 3": "Major litigation pending.",
        "Item 7": "Challenging year ahead."
    }
    result = await analyst.analyze_structural_integrity("TEST", sections)
    assert result['integrity_score'] < 40
    assert result['recommendation'] == "NO-GO"
    assert "litigation" in result['rationale'].lower()
    assert result['filing_url'] != ""

@pytest.mark.anyio
async def test_neutral_on_missing_data(analyst):
    result = await analyst.analyze_structural_integrity("TEST", {})
    assert result['recommendation'] == "NEUTRAL"
    assert result['risk_factors'] == []
