# Contract: SEC Service Interface

## Overview
The `SECService` is responsible for ticker-to-CIK mapping and extracting specific sections from 10-K/10-Q filings.

## Interface (Python Type Hints)

```python
from typing import Optional, Dict
from datetime import date

class SECService:
    async def get_cik(self, ticker: str) -> Optional[str]:
        """
        Retrieves the 10-digit CIK for a given ticker.
        Uses local cache before querying SEC.
        """
        ...

    async def fetch_latest_filing(self, cik: str, form_type: str = "10-K") -> Dict:
        """
        Fetches metadata (accessionNumber, filingDate, etc.) for the latest filing.
        """
        ...

    async def get_section_content(self, cik: str, form_type: str, section: str) -> str:
        """
        Extracts clean text from a filing section (e.g., 'Risk Factors').
        """
        ...
```

## Data Format (Section Output)
```json
{
  "cik": "0000320193",
  "form": "10-K",
  "section": "Risk Factors",
  "content": "...",
  "filing_date": "2025-10-31"
}
```

## Error Handling
- **Rate Limit**: Raises `SECRateLimitException` (Handled by `tenacity`).
- **Missing Section**: Returns empty string or raises `SECSectionMissingError`.
- **Invalid Ticker**: Returns `None` for CIK.
