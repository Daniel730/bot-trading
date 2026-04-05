# Implementation Plan: Agentic SEC RAG Analyst (with Profitability & Scalability Research)

**Branch**: `009-sec-rag-analyst` | **Date**: 2026-04-04 | **Spec**: [/specs/009-sec-rag-analyst/spec.md]
**Input**: Feature specification for Agentic SEC RAG Analyst + User request for profitability/scalability research.

## Summary

This feature implements an SEC RAG Analyst to validate arbitrage signals against fundamental risks (10-K/10-Q filings). It aims to reduce false positives by 40% using an "Adversarial Debate" architecture. Additionally, this plan includes research into further profitability and scalability enhancements for the overall bot.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: `FastMCP`, `pydantic`, `sec-api` (or direct EDGAR), `langchain` or native Gemini RAG, `pandas`, `statsmodels`
**Storage**: SQLite (Signal records, Thought Journal, CIK mapping)
**Testing**: `pytest`
**Target Platform**: Linux Server (Dockerized)
**Project Type**: MCP Server / Trading Bot Service
**Performance Goals**: RAG processing < 20s, Sector Freeze < 5s
**Constraints**: NYSE/NASDAQ hours, < 2% risk per trade
**Scale/Scope**: Arbitrage pairs validation, fundamental risk filtering

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

1. **Principle I (Capital Preservation)**: The SEC RAG Analyst implements a VETO mechanism (Score < 40/100) and adversarial validation. **PASS**
2. **Principle II (Mechanical Rationality)**: Uses structured SEC data and MCP for deterministic tool calls. **PASS**
3. **Principle III (Auditability)**: All RAG decisions and debate logs are persisted in the Thought Journal. **PASS**
4. **Principle IV (Strict Operation)**: Inherits bot's operation window constraints. **PASS**
5. **Principle V (Virtual-Pie First)**: SEC analysis informs the virtual-pie weights and risk clusters. **PASS**

## Project Structure

### Documentation (this feature)

```text
specs/009-sec-rag-analyst/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (to be generated)
```

### Source Code (repository root)

```text
src/
├── agents/
│   ├── fundamental_analyst.py  # New agent (evolved from NewsAnalyst)
│   └── orchestrator.py         # Updated to include fundamental analysis step
├── services/
│   ├── sec_service.py          # SEC EDGAR integration
│   └── agent_log_service.py    # Thought Journal persistence
├── models/
│   ├── arbitrage_models.py     # Update with Structural Integrity Score
│   └── persistence.py          # SQLite schema updates
```

**Structure Decision**: Following the established `src/agents/` and `src/services/` singleton pattern.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Adversarial Debate | Reduce LLM hallucinations in risk assessment | Single-pass analysis is prone to over-optimism or missing subtle legal risks. |
| RAG on 10-K/Q | Context window limits for large filings | Analyzing entire documents is token-expensive and noisy. |
