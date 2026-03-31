# Implementation Plan: Agentic SEC RAG Analyst

**Branch**: `009-sec-rag-analyst` | **Date**: 2026-03-31 | **Spec**: `/specs/009-sec-rag-analyst/spec.md`

## Summary
Evolve the existing `NewsAnalyst` into a `FundamentalAnalyst` that validates arbitrage signals using official SEC filings (10-K, 10-Q). The system will map tickers to CIKs, fetch recent filings from EDGAR, extract high-risk sections (Risk Factors, MD&A, Legal Proceedings), and pass them to Gemini for structural risk analysis.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `requests`, `beautifulsoup4` (for HTML parsing), `sec-edgar-api` (optional helper)
**Storage**: SQLite (`sec_filings_cache` and `ticker_cik_map`)
**Testing**: `pytest` (validation of section extraction and CIK mapping)
**Target Platform**: Linux / Docker
**Project Type**: AI Agent / Data Acquisition Upgrade
**Performance Goals**: Filing retrieval < 5s; Section extraction < 3s; Overall AI validation < 25s.

## Constitution Check

- **I. Preservação de Capital**: ✅ Fornece a defesa definitiva contra "Value Traps" ao identificar riscos legais/financeiros reais.
- **II. Racionalidade Mecânica**: ✅ Transforma a validação qualitativa em uma análise baseada em documentos legais oficiais.
- **III. Auditabilidade Total**: ✅ Trechos dos filings que justificam o veto serão persistidos no Thought Journal.
- **IV. Operação Estrita**: ✅ O fetch de dados respeita os limites da SEC (10 req/s).
- **V. Virtual-Pie First**: ✅ N/A (Foco em análise, não execução).

## Project Structure

### Documentation
```text
specs/009-sec-rag-analyst/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # EDGAR API and parsing strategy
└── tasks.md             # Implementation tasks
```

### Source Code Changes
```text
src/
├── services/
│   ├── sec_service.py       # NEW: SEC fetching and Section parsing
│   └── data_service.py      # UPDATED: Add CIK mapping logic
├── agents/
│   └── fundamental_analyst.py # NEW: Gemini-powered RAG agent
├── models/
│   └── persistence.py       # UPDATED: Cache for CIKs and filing metadata
└── orchestrator.py          # UPDATED: Switch NewsAnalyst to FundamentalAnalyst
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Long-Context RAG | Precise reasoning | Standard RAG (Vector DB) often misses nuanced legal clauses scattered across pages. Gemini's context window allows for holistic analysis. |
