# Tasks: Agentic SEC RAG Analyst

## 1. Summary
This document outlines the execution plan for the SEC RAG Analyst feature, including the profitability and scalability research items requested by the user.

## 2. Implementation Strategy
- **MVP First**: Focus on the core SEC integration (CIK mapping and extraction) before implementing the full Adversarial RAG.
- **Incremental Delivery**: Deliver User Story 1 (Structural Risk Detection) as the primary milestone.
- **Parallelism**: Independent service (SECService) can be developed in parallel with model updates.

## 3. Dependency Graph
```text
Phase 1 (Setup) 
  └── Phase 2 (Foundational)
        └── Phase 3 (US1: Structural Risk Detection)
              └── Phase 4 (Polish & Scalability)
```

## 4. Parallel Execution Examples
- **US1**: `T006` (Models) and `T007` (SECService) can be started simultaneously.

## 5. Phases

### Phase 1: Setup
- [X] T001 Install new dependencies (`edgartools`, `pydantic`) in `requirements.txt`
- [X] T002 Update `.env.template` with `SEC_USER_AGENT` placeholder
- [X] T003 [P] Create `scripts/verify_sec_parser.py` for manual integration tests

### Phase 2: Foundational
- [X] T004 Implement CIK local cache in `src/models/persistence.py`
- [X] T005 [P] Implement `SECService` interface in `src/services/sec_service.py` (Ticker-to-CIK and Section extraction)

### Phase 3: User Story 1 - Structural Risk Detection
**Story Goal**: Implement SEC-based risk filtering for arbitrage signals.
**Independent Test**: Run `scripts/verify_sec_parser.py --ticker AAPL` and confirm "Risk Factors" section extraction.

- [X] T006 [P] [US1] Create `FundamentalSignal` model in `src/models/arbitrage_models.py`
- [X] T007 [P] [US1] Implement `fetch_latest_filing` in `src/services/sec_service.py`
- [X] T008 [US1] Implement `FundamentalAnalyst` in `src/agents/fundamental_analyst.py` with Adversarial Debate (Prosecutor/Defender)
- [X] T009 [US1] Update `src/agents/orchestrator.py` to call `FundamentalAnalyst` and enforce VETO logic (FR-004)
- [X] T010 [US1] Implement fallback to News Analysis in `src/agents/fundamental_analyst.py` (FR-005)

### Phase 4: Polish & Scalability (User Request)
- [X] T011 Update `src/services/risk_service.py` with Dynamic Kelly based on `structural_integrity_score`
- [X] T012 [P] Implement Sector Freeze logic in `src/services/risk_service.py` based on correlated risks (SC-004)
- [X] T013 Ensure 100% CIK accuracy via unit tests in `tests/unit/test_sec_data.py` (SC-003)
- [X] T014 Final audit of Thought Journal logs in `src/services/agent_log_service.py` for auditability (Principle III)

## 6. MVP Scope
- **User Story 1** (T001-T010) is the MVP. It provides the core fundamental risk filtering required for "Racionalidade Mecânica".
