# Data Model: Decoupled Fundamental RAG

## Redis Key Structure

### Fundamental Score Cache
- **Key**: `sec:integrity:{ticker}`
- **Type**: String (JSON-encoded object)
- **TTL**: 86400 seconds (24 hours)
- **Fields**:
  - `score`: Integer (0-100)
  - `prosecutor_argument`: String
  - `defender_argument`: String
  - `final_reasoning`: String
  - `last_updated`: ISO-8601 Timestamp

### Telemetry (Metrics)
- **Metric Name**: `orchestrator.fundamental_cache_miss`
- **Labels**: `ticker`
- **Description**: Count of times the Orchestrator used a default score due to missing/stale cache.
