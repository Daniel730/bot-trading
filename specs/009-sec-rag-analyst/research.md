# Research: SEC RAG Analyst & Scalability Enhancements

## Phase 0: Technical Decisions

### 1. SEC Data Extraction & RAG
- **Decision**: Use `edgartools` (Python) for automated filing discovery and `sec-api` (mapping) or direct EDGAR (text extraction).
- **Rationale**: `edgartools` provides a high-level API for filtering 10-K/10-Q by ticker/CIK. Text extraction will focus on Item 1A (Risk Factors) and Item 7 (MD&A).
- **Alternatives**: `sec-edgar-downloader` (too low-level), `BeautifulSoup` scraping (fragile).

### 2. Adversarial RAG Architecture
- **Decision**: Implement a "Prosecutor vs. Defender" Debate Pattern.
- **Rationale**: 
    - **Prosecutor**: Finds evidence in 10-K/Q that *invalidates* the arbitrage trade (risks).
    - **Defender**: Finds context that *mitigates* or explains those risks.
    - **Judge (Gemini)**: Emits final 'Structural Integrity Score'.
- **Security**: Use XML delimiters (`<context>`) and system-level semantic guards to prevent prompt injection from SEC filings.

### 3. Profitability & Scalability (User Request)
- **A. Fractional Kelly Criterion (Implementation)**:
    - **Current**: 0.25x (Quarter-Kelly) per Constitution.
    - **Enhancement**: Dynamic Kelly based on the 'Confidence Score' from the Fundamental Analyst.
- **B. Kalman Filter Integration (Spec 007)**:
    - **Goal**: Move from rolling windows to dynamic beta estimation for z-scores, reducing lag and "false signals" during regime shifts.
- **C. Correlation Cluster Guard (Spec 008)**:
    - **Goal**: Prevent the bot from taking 5 different "Buy" positions in the same sector (e.g., all Banking), which leads to catastrophic tail risk.
- **D. Scalability via Multi-Broker abstraction**:
    - **Goal**: Support Alpaca or Interactive Brokers alongside Trading 212 to increase liquidity and capital capacity.
- **E. Alternative Data (Macro/Sentiment)**:
    - **Goal**: Use Gemini to analyze FED minutes or high-impact news as a "Sector Freeze" trigger.

## Technical Unknowns & Clarifications

| Unknown | Finding | Decision |
|---------|---------|----------|
| Ticker-to-CIK Mapping | SEC maintains a JSON mapping file (ticker.json). | Fetch and cache this file locally in `persistence.py`. |
| RAG Vector DB | For single-asset analysis, context usually fits in Gemini's long context window. | No Vector DB for now; use long-context retrieval (Map-Reduce pattern). |
| Rate Limits | SEC EDGAR allows 10 requests/sec. | Implement `tenacity` retries and rate-limiting in `sec_service.py`. |

## Summary of Profitability Boosters
1. **False Positive Reduction**: SEC RAG filters out "Value Traps" (tickers falling for fundamental reasons, not noise).
2. **Execution Efficiency**: Kalman filter enters trades at the optimal turn.
3. **Risk Diversification**: Cluster Guard ensures non-correlated bets.
