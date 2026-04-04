# Data Model: Agentic SEC RAG Analyst

## 1. Entities

### FundamentalSignal
Extends `ArbitrageSignal` with fundamental validation results.

| Field | Type | Description |
|-------|------|-------------|
| `signal_id` | UUID | FK to base signal. |
| `ticker` | String | Ticker being analyzed. |
| `cik` | String | SEC Central Index Key. |
| `structural_integrity_score` | Integer (0-100) | 0-100 score; <40 = VETO. |
| `prosecutor_argument` | String | LLM-generated argument AGAINST the trade. |
| `defender_argument` | String | LLM-generated argument FOR the trade. |
| `final_reasoning` | String | Judge's final decision summary. |
| `analyzed_at` | DateTime | Timestamp of analysis. |

### CIKMapping
Local cache for SEC mapping.

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | String (PK) | Stock ticker. |
| `cik` | String | 10-digit CIK. |
| `last_updated` | DateTime | Cache TTL management. |

### SECReportSection
Cache of extracted filings.

| Field | Type | Description |
|-------|------|-------------|
| `cik` | String | Ticker CIK. |
| `form_type` | String | '10-K' or '10-Q'. |
| `period_end` | Date | Date of the filing period. |
| `section_name` | String | 'Risk Factors' or 'MD&A'. |
| `content` | Text | Cleaned text extracted from SEC. |
| `cached_at` | DateTime | Cache management. |

## 2. Relationships
- One `ArbitrageSignal` has many (or 2) `FundamentalSignal` (one per ticker in the pair).
- `FundamentalAnalyst` reads `SECReportSection` and writes to `FundamentalSignal`.

## 3. Validation Rules
- **VETO Gate**: If `structural_integrity_score` < 40 for either ticker, the signal's `confidence_score` MUST be set to 0.
- **Cache TTL**: SEC filings only need to be updated once per quarter (90 days).
- **Adversarial Integrity**: Prosecutor and Defender prompts MUST be distinct and isolated to avoid cross-contamination.
