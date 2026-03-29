# Implementation Plan: Strategic Arbitrage Engine

**Branch**: `004-strategic-arbitrage-engine` | **Date**: 2026-03-28 | **Spec**: `/specs/004-strategic-arbitrage-engine/spec.md`
**Input**: Feature specification from `/specs/004-strategic-arbitrage-engine/spec.md`

## Summary

Building a statistical arbitrage bot that monitors cointegrated pairs (e.g., KO/PEP) using multi-window Z-Scores (30, 60, 90 days). The system integrates quant math with fundamental AI validation via Gemini CLI to distinguish between technical noise and structural changes. Execution is handled through a "Virtual Pie" system using Trading 212 market orders, with human-in-the-loop approval via Telegram.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `FastMCP`, `pandas`, `statsmodels`, `python-telegram-bot`, `requests`, `yfinance`, `tenacity`  
**Storage**: SQLite (Arbitrage pairs, Signal records, Virtual Pie state, Trade Ledger)  
**Testing**: `pytest`  
**Target Platform**: Linux / Docker  
**Project Type**: Bot Service / CLI  
**Performance Goals**: Z-Score accuracy 99.9%, fundamental analysis latency < 30s  
**Constraints**: Strictly NYSE hours (14:30-21:00 WET), Slippage tolerance check, Atomic swap execution  
**Scale/Scope**: Real-time monitoring of 1-10 cointegrated pairs

## Constitution Check

- **I. Library-First**: Logic for Z-Score and OLS will be implemented in `src/services/arbitrage_service.py` as an independent library.
- **II. Safety-Critical**: Enforcement of 14:30-21:00 WET operating hours in `src/monitor.py`.
- **III. Atomicidade**: Swap logic will ensure both Sell and Buy legs are tracked and compensated if one fails.
- **IV. State Management**: SQLite handles "Virtual Pie" persistence; sync logic runs on startup.
- **V. Human-in-the-loop**: All signals trigger a Telegram interactive message requiring manual "Approve" before execution.

## Project Structure

### Documentation (this feature)

```text
specs/004-strategic-arbitrage-engine/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Data sourcing and AI search patterns
├── data-model.md        # SQLite schema and entity relationships
├── quickstart.md        # Scenario testing and setup
└── contracts/
    └── brokerage_api.md # Trading 212 and MCP tool definitions
```

### Source Code (repository root)

```text
src/
├── models/
│   └── arbitrage_models.py
├── services/
│   ├── arbitrage_service.py # Math and Strategy logic
│   ├── brokerage_service.py # T212 API wrapper
│   ├── data_service.py      # Market data polling
│   └── notification_service.py # Telegram Bot integration
├── mcp_server.py           # FastMCP tool definitions
└── monitor.py              # Main Orchestrator (Monitoring Loop)

tests/
├── integration/
│   └── test_brokerage.py
└── unit/
    └── test_arbitrage_math.py
```

**Structure Decision**: Single project structure with service-oriented layers to ensure library-first isolation.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Multi-window Z-Score | Noise filtering | Single window Z-Score is prone to whipsaws. |
| Virtual Pie Rebalancing | T212 API limits | Native Pies don't expose granular rebalance by quantity. |
