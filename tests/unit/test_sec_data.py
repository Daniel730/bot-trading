import pytest
from unittest.mock import patch, MagicMock
from src.services.sec_service import SECService

@pytest.fixture
def sec_service():
    return SECService()

@pytest.mark.anyio
async def test_get_cik_by_ticker_cached(sec_service):
    with patch.object(sec_service.persistence, 'load_cik_mapping', return_value="0000320193"):
        cik = await sec_service.get_cik_by_ticker("AAPL")
        assert cik == "0000320193"

@pytest.mark.anyio
async def test_get_cik_by_ticker_network(sec_service):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
    }
    
    with patch.object(sec_service.persistence, 'load_cik_mapping', return_value=None), \
         patch('asyncio.to_thread', return_value=mock_response), \
         patch.object(sec_service.persistence, 'save_cik_mapping') as mock_save:
        
        cik = await sec_service.get_cik_by_ticker("AAPL")
        assert cik == "0000320193"
        mock_save.assert_called_once_with("AAPL", "0000320193")

def test_extract_sections(sec_service):
    html_content = """
    <html>
        <body>
            <div>Item 1A. Risk Factors</div>
            <p>We might lose money because of competition.</p>
            <div>Item 3. Legal Proceedings</div>
            <p>No major lawsuits.</p>
            <div>Item 7. Management’s Discussion and Analysis</div>
            <p>Our revenue increased by 10%.</p>
        </body>
    </html>
    """
    sections = sec_service.extract_sections(html_content)
    assert "Item 1A" in sections
    assert "Item 7" in sections
    assert "Item 3" in sections
    assert "Risk Factors" in sections["Item 1A"]
    assert "Management’s Discussion" in sections["Item 7"]

@pytest.mark.anyio
async def test_get_latest_filings_metadata(sec_service):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-23-000106"],
                "filingDate": ["2023-11-03"],
                "form": ["10-K"],
                "primaryDocument": ["aapl-20230930.htm"]
            }
        }
    }
    
    with patch.object(sec_service, 'get_cik_by_ticker', return_value="0000320193"), \
         patch('asyncio.to_thread', return_value=mock_response):
        
        metadata = await sec_service.get_latest_filings_metadata("AAPL")
        assert len(metadata) > 0
        assert metadata[0]["type"] == "10-K"
        assert "Archives/edgar/data/0000320193" in metadata[0]["url"]
