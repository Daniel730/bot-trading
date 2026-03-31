# Data Model: SEC Filings & CIK Mapping

**Feature**: 009-sec-rag-analyst  
**Date**: 2026-03-31

## Entities

### `TickerCIKMap`
Persistent mapping of market tickers to SEC Central Index Keys.
- `ticker`: String (Primary Key, e.g., 'AAPL')
- `cik`: String (10-digit zero-padded SEC ID)
- `last_updated`: DateTime

### `SecFilingCache`
Metadata and local cache of recently analyzed filings to avoid redundant SEC API calls.
- `pair_id`: String (Foreign Key)
- `accession_number`: String (Unique filing ID)
- `filing_type`: String ('10-K' or '10-Q')
- `filing_date`: Date
- `risk_summary`: Text (The agent's extracted risk summary)
- `structural_integrity_score`: Integer (0-100)

## State Transitions

1. **Mapping**: On first request for a ticker, query the SEC JSON mapping and save to `TickerCIKMap`.
2. **Retrieval**: 
   - Check `SecFilingCache` for the latest filing.
   - If stale (> 90 days for 10-K, > 30 days for 10-Q), fetch new metadata from EDGAR.
3. **Analysis**:
   - Extract sections (Item 1A, 7, 3).
   - Agent produces `risk_summary` and `score`.
   - Update cache.

## Relationships
- A `Signal` will now link to a `SecFilingCache` record via the `ThoughtJournal` to show which document was used for the "GO/NO-GO" decision.
