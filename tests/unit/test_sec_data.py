import pytest
from src.services.sec_service import SECService
from src.models.persistence import PersistenceManager
import os

@pytest.fixture
def sec_service():
    return SECService(persistence=PersistenceManager(db_path=":memory:"))

@pytest.mark.asyncio
async def test_cik_extraction_accuracy(sec_service):
    """
    SC-003: 100% de precisão na extração do CIK a partir de tickers.
    Validating against known ground truth.
    """
    ground_truth = {
        "AAPL": "0000320193",
        "MSFT": "0000789019",
        "TSLA": "0001318605",
        "GOOG": "0001652044"
    }
    
    for ticker, expected_cik in ground_truth.items():
        cik = await sec_service.get_cik(ticker)
        # edgartools might return 320193 or 0000320193, we normalize to 10 digits
        normalized_cik = cik.zfill(10) if cik else None
        assert normalized_cik == expected_cik, f"Failed for {ticker}: expected {expected_cik}, got {normalized_cik}"

@pytest.mark.asyncio
async def test_section_extraction(sec_service):
    """
    Verifies that we can extract Risk Factors and MD&A.
    """
    # Use a major ticker that definitely has these sections
    ticker = "AAPL"
    
    risk_factors = await sec_service.get_section_content(ticker, "10-K", "Risk Factors")
    assert risk_factors is not None
    assert len(risk_factors) > 1000
    assert "Item 1A" in risk_factors or "RISK FACTORS" in risk_factors.upper()

    mda = await sec_service.get_section_content(ticker, "10-K", "MD&A")
    assert mda is not None
    assert len(mda) > 1000
    assert "Item 7" in mda or "MANAGEMENT'S DISCUSSION" in mda.upper()
