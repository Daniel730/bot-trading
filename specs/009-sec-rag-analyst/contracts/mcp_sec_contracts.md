# Contracts: SEC Model Context Protocol (MCP)

## Tools

### `get_filing_sections`
Retrieves cleaned text from specific sections of the latest 10-K or 10-Q.
- **Input**:
  - `ticker` (string): e.g., "AAPL"
  - `sections` (list[string]): e.g., ["Item 1A", "Item 7"]
- **Output**: 
  - `sections_text` (dict): Map of section name to text content.
  - `metadata` (dict): Date, filing type, accession number.

### `resolve_cik`
Resolves a market ticker to an SEC CIK.
- **Input**: `ticker` (string)
- **Output**: `cik` (string)

### `record_fundamental_verdict`
Saves the Agent's reasoning based on RAG analysis.
- **Input**:
  - `signal_id` (UUID)
  - `score` (int): 0-100 (Structural Integrity)
  - `rationale` (string)
  - `snippet` (string): The evidence from the filing.
- **Output**: Success status.

## Data Schemes

### `SECAnalysisReport`
```json
{
  "ticker": "string",
  "filing_type": "string",
  "integrity_score": "integer",
  "veto_triggered": "boolean",
  "key_risks": ["string"]
}
```
