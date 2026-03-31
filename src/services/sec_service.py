import requests
import logging
import asyncio
from typing import Optional, List, Dict
from src.models.persistence import PersistenceManager
from src.config import settings

logger = logging.getLogger(__name__)

class SECService:
    """
    Handles retrieval of SEC EDGAR filings and ticker-to-CIK mapping.
    """
    TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
    
    def __init__(self):
        self.persistence = PersistenceManager(settings.DB_PATH)
        # SEC requires a descriptive User-Agent
        self.headers = {
            "User-Agent": "ArbitrageBot/1.0 (daniel@example.com)",
            "Accept-Encoding": "gzip, deflate"
        }

    async def get_cik_by_ticker(self, ticker: str) -> Optional[str]:
        """
        Retrieves the 10-digit CIK for a market ticker.
        """
        # 1. Check local cache
        cached_cik = self.persistence.load_cik_mapping(ticker)
        if cached_cik:
            return cached_cik

        # 2. Fetch from SEC if not cached
        try:
            logger.info(f"Fetching CIK mapping from SEC for {ticker}...")
            # Use to_thread for blocking requests
            response = await asyncio.to_thread(requests.get, self.TICKER_CIK_URL, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                for entry in data.values():
                    if entry['ticker'] == ticker.upper():
                        cik = str(entry['cik_str']).zfill(10)
                        self.persistence.save_cik_mapping(ticker.upper(), cik)
                        return cik
            else:
                logger.error(f"SEC Ticker Map returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching SEC CIK mapping: {e}")
        
        return None

    async def get_latest_filings_metadata(self, ticker: str) -> List[Dict]:
        """
        Retrieves the metadata for the most recent 10-K and 10-Q filings.
        """
        cik = await self.get_cik_by_ticker(ticker)
        if not cik:
            return []

        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            response = await asyncio.to_thread(requests.get, url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                recent_filings = data.get('filings', {}).get('recent', {})
                
                filings = []
                # Find most recent 10-K and 10-Q
                for i, f_type in enumerate(recent_filings.get('form', [])):
                    if f_type in ['10-K', '10-Q'] and len(filings) < 5:
                        acc_num = recent_filings['accessionNumber'][i].replace('-', '')
                        doc_name = recent_filings['primaryDocument'][i]
                        
                        filings.append({
                            "accession_number": recent_filings['accessionNumber'][i],
                            "type": f_type,
                            "date": recent_filings['filingDate'][i],
                            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                        })
                return filings
        except Exception as e:
            logger.error(f"Error fetching filing metadata for {ticker}: {e}")
            
        return []

    async def fetch_filing_html(self, url: str) -> Optional[str]:
        """
        Retrieves the raw HTML content of a specific SEC filing.
        """
        try:
            response = await asyncio.to_thread(requests.get, url, headers=self.headers)
            if response.status_code == 200:
                return response.text
            logger.error(f"SEC Filing fetch returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching SEC filing HTML: {e}")
        return None

    def extract_sections(self, html_content: str) -> Dict[str, str]:
        """
        Extracts Item 1A (Risk Factors) and Item 7 (MD&A) from SEC filing HTML.
        """
        import re
        from bs4 import BeautifulSoup

        # Pre-process HTML to remove heavy tags
        soup = BeautifulSoup(html_content, 'html.parser')
        for tag in soup(['script', 'style', 'table']):
            tag.decompose()
        
        text = soup.get_text(separator='\n')
        
        sections = {
            "Item 1A": "",
            "Item 7": "",
            "Item 3": ""
        }

        # Regex patterns for SEC Item headers
        patterns = {
            "Item 1A": r"Item\s+1A\.\s+Risk\s+Factors",
            "Item 7": r"Item\s+7\.\s+Management’s\s+Discussion\s+and\s+Analysis",
            "Item 3": r"Item\s+3\.\s+Legal\s+Proceedings"
        }

        for item, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start_idx = match.start()
                sections[item] = text[start_idx : start_idx + 20000]
        
        return sections

    async def get_analyzed_sections(self, ticker: str) -> Dict:
        """
        Coordinates the fetching, parsing, and caching of SEC filing sections.
        """
        metadata_list = await self.get_latest_filings_metadata(ticker)
        if not metadata_list:
            return {"sections": {}, "metadata": None}
        
        latest = metadata_list[0]
        html = await self.fetch_filing_html(latest['url'])
        if not html:
            return {"sections": {}, "metadata": None}
            
        # extract_sections is CPU-bound, use to_thread
        sections = await asyncio.to_thread(self.extract_sections, html)
        return {"sections": sections, "metadata": latest}

sec_service = SECService()
