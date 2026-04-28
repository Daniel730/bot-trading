import asyncio
import re
from typing import Optional, Dict
from edgar import set_identity, Company
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.models.persistence import PersistenceManager
from src.config import settings

class SECRateLimitException(Exception):
    """Custom exception for SEC rate limit (429)."""

class SECService:
    GROUND_TRUTH_CIKS = {
        "AAPL": "0000320193", "MSFT": "0000789019", "GOOGL": "0001652044", "GOOG": "0001652044",
        "AMZN": "0001018724", "META": "0001326801", "TSLA": "0001318605", "BRK-B": "0001067983",
        "V": "0001403161", "JPM": "0000019617", "JNJ": "0000200406", "WMT": "0000104169",
        "NVDA": "0001045810", "PG": "0000080424", "XOM": "0000034088", "MA": "0001141391",
        "HD": "0000354950", "CVX": "0000093410", "LLY": "0000059478", "PEP": "0000077476",
        "KO": "0000021344", "ABBV": "0001551152", "BAC": "0000070858", "COST": "0000909832",
        "AVGO": "0001730168", "TMO": "0000097745", "CSCO": "0000858877", "MCD": "0000063908",
        "ADBE": "0000796343", "DIS": "0001744489", "ACN": "0001467373", "LIN": "0001707925",
        "NFLX": "0001065280", "ABT": "0000001800", "ORCL": "0001341439", "TXN": "0000097476",
        "VZ": "0000732712", "DHR": "0000313616", "INTC": "0000050863", "PM": "0001413329",
        "NEE": "0000753308", "RTX": "0000101829", "HON": "0000773840", "AMAT": "0000006951",
        "LOW": "0000060667", "BKNG": "0001075531", "T": "0000732717", "UPS": "0001090727",
        "IBM": "0000051143", "CAT": "0000018230", "GE": "0000040545",
    }
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

    async def prewarm_cik_cache(self, tickers: list[str]):
        """
        Bulk checks and populates CIK cache for a list of tickers.
        Significantly reduces 'one-by-one' DB roundtrips.
        """
        if not tickers:
            return

        # 1. Bulk load from SQLite
        existing = self.persistence.get_cik_mappings(tickers)
        missing = [t for t in tickers if t not in existing]
        
        if not missing:
            return

        print(f"SEC_SERVICE: Pre-warming CIK cache for {len(missing)} missing tickers...")
        
        # 2. Fetch missing. We use a semaphore to avoid slamming the SEC too hard
        semaphore = asyncio.Semaphore(5)
        
        async def fetch_and_cache(ticker: str):
            async with semaphore:
                try:
                    # This calls our existing retry-wrapped get_cik
                    await self.get_cik(ticker)
                except Exception:
                    pass

        tasks = [fetch_and_cache(t) for t in missing]
        await asyncio.gather(*tasks)
        print(f"SEC_SERVICE: CIK cache pre-warming complete.")

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
        ticker = ticker.upper()
        if ticker in self.GROUND_TRUTH_CIKS:
            cik = self.GROUND_TRUTH_CIKS[ticker]
            self.persistence.save_cik_mapping(ticker, cik)
            return cik

        cached_cik = self.persistence.load_cik_mapping(ticker)
        if cached_cik:
            return str(cached_cik).zfill(10)

        try:
            # edgartools Company lookup is synchronous but fast
            # We wrap it in run_in_executor if needed, but for now direct call
            company = Company(ticker)
            if company and company.cik:
                cik = str(company.cik).zfill(10)
                self.persistence.save_cik_mapping(ticker, cik)
                return cik
        except Exception as e:
            if "429" in str(e):
                raise SECRateLimitException(f"SEC Rate Limit for {ticker}")
            print(f"Error fetching CIK for {ticker}: {e}")
        
        return None

    async def get_cik_by_ticker(self, ticker: str) -> Optional[str]:
        return await self.get_cik(ticker)

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
            content = doc[item_id]
            
            if content is None:
                return None
            return content.text if hasattr(content, 'text') else str(content)
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
                
                rf_section = doc[item_map["Risk Factors"]]
                mda_section = doc[item_map["MD&A"]]
                
                rf_content = rf_section.text if hasattr(rf_section, 'text') else str(rf_section) if rf_section else None
                mda_content = mda_section.text if hasattr(mda_section, 'text') else str(mda_section) if mda_section else None
                
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

    def extract_sections(self, html: str) -> Dict[str, str]:
        text = re.sub(r"<[^>]+>", "\n", html)
        text = re.sub(r"\s+", " ", text)
        pattern = re.compile(r"\bITEM\s+(\d+[A-Z]?)\s*[\.:]\s*", re.IGNORECASE)
        matches = list(pattern.finditer(text))
        sections: Dict[str, str] = {}
        wanted = {"1A", "3", "7"}
        for idx, match in enumerate(matches):
            item = match.group(1).upper()
            if item not in wanted:
                continue
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            sections[f"Item {item}"] = text[start:end].strip()
        return sections

# Singleton instance
sec_service = SECService()
