import os
import asyncio
from typing import Optional, Dict
from datetime import datetime, date
from edgar import set_identity, Company
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.models.persistence import PersistenceManager
from src.config import settings

class SECRateLimitException(Exception):
    """Custom exception for SEC rate limit (429)."""
    pass

class SECService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SECService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, persistence: PersistenceManager = None):
        if self._initialized:
            return
        
        self.persistence = persistence or PersistenceManager()
        set_identity(settings.SEC_USER_AGENT)
        
        self._initialized = True

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(SECRateLimitException)
    )
    async def get_cik(self, ticker: str) -> Optional[str]:
        """
        Retrieves the 10-digit CIK for a given ticker.
        Uses local cache before querying SEC.
        """
        cached_cik = self.persistence.load_cik_mapping(ticker)
        if cached_cik:
            return cached_cik

        try:
            # edgartools Company lookup is synchronous but fast
            # We wrap it in run_in_executor if needed, but for now direct call
            company = Company(ticker)
            if company and company.cik:
                cik = company.cik
                self.persistence.save_cik_mapping(ticker, cik)
                return cik
        except Exception as e:
            if "429" in str(e):
                raise SECRateLimitException(f"SEC Rate Limit for {ticker}")
            print(f"Error fetching CIK for {ticker}: {e}")
        
        return None

    async def fetch_latest_filing_metadata(self, ticker: str, form_type: str = "10-K") -> Optional[Dict]:
        """
        Fetches metadata for the latest filing of a given type.
        """
        try:
            company = Company(ticker)
            filings = company.get_filings(form=[form_type])
            if not filings:
                # Try 10-Q if 10-K requested and vice-versa if appropriate, or just return None
                return None
            
            latest = filings.latest()
            return {
                "accession_number": latest.accession_no,
                "filing_date": latest.filing_date,
                "form": latest.form,
                "filing": latest # Store the edgartools filing object
            }
        except Exception as e:
            print(f"Error fetching latest filing for {ticker}: {e}")
            return None

    async def get_section_content(self, ticker: str, form_type: str, section: str) -> Optional[str]:
        """
        Extracts clean text from a filing section (e.g., 'Risk Factors').
        """
        try:
            metadata = await self.fetch_latest_filing_metadata(ticker, form_type)
            if not metadata:
                return None
            
            filing = metadata["filing"]
            doc = filing.obj()
            
            # Map section names to Item identifiers
            # 10-K: Item 1A (Risk Factors), Item 7 (MD&A)
            # 10-Q: Part II Item 1A (Risk Factors), Part I Item 2 (MD&A)
            item_map = {
                "Risk Factors": "Item 1A" if form_type == "10-K" else "Part II Item 1A",
                "MD&A": "Item 7" if form_type == "10-K" else "Part I Item 2"
            }
            
            item_id = item_map.get(section, section)
            content = doc.get_item(item_id)
            
            return content
        except Exception as e:
            print(f"Error extracting section {section} from {ticker} {form_type}: {e}")
            return None

    async def get_analyzed_sections(self, ticker: str) -> Dict:
        """
        Efficiently fetches Risk Factors and MD&A for a ticker.
        """
        result = {"sections": {}, "metadata": None}
        
        # Try 10-K, then 10-Q
        for form in ["10-K", "10-Q"]:
            metadata = await self.fetch_latest_filing_metadata(ticker, form)
            if not metadata:
                continue
            
            filing = metadata["filing"]
            try:
                doc = filing.obj()
                item_map = {
                    "Risk Factors": "Item 1A" if form == "10-K" else "Part II Item 1A",
                    "MD&A": "Item 7" if form == "10-K" else "Part I Item 2"
                }
                
                rf_content = doc.get_item(item_map["Risk Factors"])
                mda_content = doc.get_item(item_map["MD&A"])
                
                if rf_content or mda_content:
                    result["sections"] = {
                        "Risk Factors": rf_content,
                        "MD&A": mda_content
                    }
                    result["metadata"] = {
                        "date": metadata["filing_date"],
                        "type": form,
                        "accession": metadata["accession_number"]
                    }
                    break
            except Exception as e:
                print(f"Error parsing filing for {ticker} {form}: {e}")
                
        return result

# Singleton instance
sec_service = SECService()
