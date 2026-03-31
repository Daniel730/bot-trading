# Research: Agentic RAG for SEC EDGAR

**Feature**: 009-sec-rag-analyst  
**Date**: 2026-03-31

## Technical Decision: SEC Data Sourcing

### Choice: SEC-API.io or Official EDGAR REST API
- **Selection**: We will start with the **Official EDGAR REST API** (free) combined with a local parser for XBRL/HTML sections.
- **Rationale**: The official API is highly reliable and provides full JSON indexes of filings. For complex section extraction (e.g., Extracting Item 1A: Risk Factors), we will use regex-based segmentation or the `sec-api` python wrapper if needed.

## RAG Strategy: "Semantic Sectioning"

Instead of embedding the entire 100-page document (which is token-inefficient), we will use **Semantic Sectioning**:
1.  **Index**: Retrieve the URL for the most recent 10-K or 10-Q.
2.  **Sectioning**: Extract only:
    -   *Item 1A: Risk Factors*
    -   *Item 7: Management's Discussion and Analysis (MD&A)*
    -   *Item 3: Legal Proceedings*
3.  **Context Injection**: Pass these segments into the Gemini context window directly (since Gemini 1.5 Pro has a 1M+ token limit, we may bypass a vector DB initially and use "Long-Context RAG" for better reasoning).

## CIK Mapping
The SEC uses CIK (Central Index Key), not tickers. We need a robust mapping:
-   **Solution**: Use the `sec-edgar-api` mapping or the official SEC Ticker-to-CIK JSON file.

## Expected Risks
-   **Rate Limiting**: SEC EDGAR limits to 10 requests per second. Our bot polls every 15s for 20 pairs, so we must cache filings locally.
-   **Inconsistent HTML**: SEC filings have non-standard HTML structures. Mitigation: Implement a "Heuristic Parser" that looks for specific header patterns.

## Performance Goals
-   **Latency**: Retrieval (5s) + Parsing (3s) + LLM Inference (10s) = ~18s total. Well within our 30s target for AI validation.
