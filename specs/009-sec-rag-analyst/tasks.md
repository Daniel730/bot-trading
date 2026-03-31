---

description: "Dependency-ordered tasks for Agentic SEC RAG Analyst"
---

# Tasks: Agentic SEC RAG Analyst

**Input**: Design documents from `/specs/009-sec-rag-analyst/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Organization**: Tasks group by data acquisition, parsing, agent logic, and orchestration integration.

## Phase 1: SEC Data Infrastructure (Phase 1)

**Purpose**: Establish connection to SEC EDGAR and handle ticker mappings.

- [ ] T001 Implement `TickerCIKMap` table and `save_cik_mapping` in `src/models/persistence.py`
- [ ] T002 Implement `SECService.get_cik_by_ticker` in `src/services/sec_service.py` using SEC official JSON
- [ ] T003 Implement `SECService.get_latest_filings_metadata` to retrieve URLs for 10-K/10-Q
- [ ] T004 [P] Add unit tests for CIK mapping and metadata retrieval in `tests/unit/test_sec_data.py`

---

## Phase 2: Semantic Sectioning (Phase 2)

**Purpose**: Extract critical text segments from large HTML/XBRL filings.

- [ ] T005 Implement `SECService.fetch_filing_html` with user-agent compliance (SEC requirement)
- [ ] T006 Implement regex-based parser to extract `Item 1A (Risk Factors)` and `Item 7 (MD&A)`
- [ ] T007 Implement extraction for `Item 3 (Legal Proceedings)`
- [ ] T008 [P] Add tests verifying section extraction against sample 10-K HTML files

---

## Phase 3: Fundamental Agent (Phase 3)

**Purpose**: Create the Gemini-powered analyst that reasons over the filings.

- [ ] T009 Create `src/agents/fundamental_analyst.py` (evolving from `news_analyst.py`)
- [ ] T010 Implement the "Structural Risk Prompt" focusing on debt, litigation, and contract breaches
- [ ] T011 Integrate section text into the agent's context window for "Long-Context RAG"
- [ ] T012 Implement `structural_integrity_score` (0-100) logic based on agent findings

---

## Phase 4: Integration & Orchestration (Phase 4)

**Purpose**: Wire the RAG analyst into the signal validation loop.

- [ ] T013 Update `src/agents/orchestrator.py` to replace `news_node` with `fundamental_node`
- [ ] T014 Update the `aggregator_node` to give high weight (veto power) to the Fundamental Analyst's integrity score
- [ ] T015 Update `src/monitor.py` to pass SEC context to the orchestrator
- [ ] T016 Log extracted risk factors to the `Thought Journal` for full auditability

---

## Phase N: Polish & Caching

- [ ] T017 Implement `sec_filings_cache` in SQLite to prevent redundant parsing and API calls
- [ ] T018 Add a fallback to News Analysis if SEC EDGAR is unreachable or the filing is unavailable
- [ ] T019 [P] Performance optimization: Ensure filing fetch and parse doesn't block the monitor loop

---

## Dependencies & Execution Order

1. **Infrastructure (Phase 1)**: Core prerequisite for all SEC data.
2. **Parsing (Phase 2)**: Necessary to provide clean text to the AI.
3. **Agent Logic (Phase 3)**: The "brain" of the feature.
4. **Integration (Phase 4)**: Deployment into the bot's workflow.

### Implementation Strategy

1. **CIK First**: Ensure we can find companies before we try to read their files.
2. **Sectioning Validation**: SEC HTML is messy; ensure the parser works on top 5 tickers (AAPL, MSFT, KO, JPM, XOM).
3. **Veto Power**: During the first week, use the RAG findings as a "Warning" in Telegram before giving it full "Veto" power in the code.
