# Implementation Plan: Strategic Arbitrage Engine

**Branch**: `003-strategic-arbitrage-engine` | **Date**: 2026-03-27 | **Spec**: `/specs/003-strategic-arbitrage-engine/spec.md`

## Summary
Building a statistical arbitrage engine that monitors cointegrated pairs using rolling Z-Scores (30, 60, 90 days). Integrates Gemini CLI for fundamental validation of signals and uses a "Virtual Pie" system to execute trades via individual market orders on Trading 212.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `FastMCP`, `yfinance`, `polygon-api-client`, `statsmodels`, `pandas`, `python-telegram-bot`, `tenacity`, `quantstats`, `holidays`
**Storage**: SQLite (ArbitragePair, SignalRecord, VirtualPieAsset, TradeLedger)
**Testing**: `pytest` (Z-Score math, rebalance logic, Mock API)
**Target Platform**: Dockerized (Bot + MCP Server)
**Performance Goals**: Z-Score accuracy 99.9%, AI validation < 30s
**Constraints**: 14:30 - 21:00 WET (NYSE hours), 5 req/min (Polygon Free Tier), 10% max allocation
**Scale/Scope**: Support for 1-10 concurrent cointegrated pairs

## Constitution Check

- **I. Library-First**: ✅ `src/services/arbitrage_service.py` is an independent math library.
- **II. Safety-Critical**: ✅ `src/monitor.py` enforces 14:30-21:00 WET operating window.
- **III. Atomicidade**: ✅ Rebalance logic executes Sell-then-Buy in a single logical block with error recovery.
- **IV. State Management**: ✅ SQLite persists Virtual Pie weights; synced with T212 on startup.
- **V. Human-in-the-loop**: ✅ Telegram approval required for all trades (Entry/Exit).

## Project Structure

### Documentation (this feature)

```text
specs/003-strategic-arbitrage-engine/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Data sourcing and AI validation findings
├── data-model.md        # SQLite schema for arbitrage and pie
├── quickstart.md        # Setup guide
└── contracts/
    └── mcp_t212_contracts.md # Brokerage and MCP definitions
```

### Source Code (repository root)

```text
src/
├── models/
│   └── arbitrage_models.py  # Pydantic schemas for pairs/signals
├── services/
│   ├── arbitrage_service.py # Cointegration & Z-Score math
│   ├── brokerage_service.py # T212 API wrapper (Basic Auth)
│   ├── data_service.py      # yfinance + Polygon WS
│   └── notification_service.py # Async Telegram bot
├── mcp_server.py           # FastMCP tools (sentiment/risk)
└── monitor.py              # Orchestrator / Main Loop
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Multi-window Z-Score | Robustness against noise | Single window too prone to whipsaws |
| Virtual Pie Re-sync | Data integrity | Brokerage state is source of truth |

## Phase 0: Research (COMPLETE)
- [x] WebSockets support for Polygon.io Free tier confirmed.
- [x] FastMCP tool definitions for Gemini integration.

## Phase 1: Design & Contracts (COMPLETE)
- [x] SQLite schema for ArbitragePair and TradeLedger.
- [x] Brokerage API contracts for Trading 212 Beta.
- [x] Agent context updated for Gemini.
