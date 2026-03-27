# Implementation Plan: Trading Arbitrage Bot with Virtual Pie and AI Validation

**Branch**: `002-trading-arbitrage-bot` | **Date**: 2026-03-27 | **Spec**: `/specs/002-trading-arbitrage-bot/spec.md`

## Summary
Build an autonomous statistical arbitrage system that monitors competitor pairs (up to 5), calculates Z-score deviations (30-90 day lookback), and validates trades via Gemini CLI based on contextual market news. Implements a **Hybrid Oversight** model requiring manual user confirmation via Telegram before executing rebalances. Due to API limitations, a "Virtual Pie" system using local SQLite persistence with **Brokerage Startup Re-sync** manages target allocations.

## Technical Context
- **Language/Version**: Python 3.11+
- **Primary Dependencies**: `FastMCP`, `requests`, `yfinance`, `pytz`, `statsmodels`, `pandas`, `python-dotenv`, `Polygon.io` (Snapshot API)
- **Storage**: SQLite (Local database for Pie targets, Audit Logs, and Signals)
- **Testing**: `pytest` for Z-score math and rebalance logic
- **Target Platform**: Linux (capable of running Gemini CLI)
- **Project Type**: AI Agent Orchestrator / Automated Trading
- **Performance Goals**: AI validation < 15s; Allocation drift < 1%
- **Constraints**: Operating window 14:30 - 21:00 WET; Max allocation 10% (Principle II)
- **Scale/Scope**: Support for 1-5 concurrent cointegrated pairs.

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Horário de Operação Estrito**: ✅ Logic enforces 14:30 - 21:00 WET window.
- **II. Gestão de Risco e Capital**: ✅ Rebalance logic caps orders at 10% of free balance.
- **III. Neutralidade de Mercado**: ✅ Pairs trading strategy focuses on spreads, ignoring market direction.
- **IV. Segurança da API**: ✅ Credentials stored exclusively in `.env`.
- **V. Validação Estratégica via IA**: ✅ Mandatory Gemini news analysis loop for all signals.

## Project Structure

### Documentation (this feature)
```text
specs/002-trading-arbitrage-bot/
├── spec.md              # Feature specification (v2 after clarifications)
├── plan.md              # This file
├── research.md          # API and data sourcing decisions
├── data-model.md        # SQLite schema with startup re-sync
├── quickstart.md        # Setup and execution guide
└── contracts/
    └── mcp_t212_contracts.md # API and MCP Tool definitions
```

### Source Code (repository root)
```text
src/
├── models/
│   └── trading_models.py    # SQLite/Pydantic schemas
├── services/
│   ├── arbitrage_service.py # Z-score math & Rebalance logic (Risk aware)
│   ├── brokerage_service.py # T212 API (Orders, Portfolio Sync, Balance)
│   ├── data_service.py      # Polygon.io/yfinance (Market hours aware)
│   └── notification_service.py # Telegram alerts with inline confirmation
├── mcp_server.py           # FastMCP tool server
└── monitor.py              # Main loop / Scheduler / Startup Sync
tests/
├── unit/
│   └── test_arbitrage.py    # Validate Z-score and Rebalance math
└── integration/
    └── test_brokerage.py    # Mock T212 API calls
```

## Complexity Tracking
| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Startup API Sync | Ensure quantity accuracy | Local-only DB prone to drift from manual trades |
| Manual Confirm Loop | Constitutional safety / User oversight | Full autonomy risky for high-value accounts |

## Phase 0: Research (COMPLETE)
- [x] Official T212 Portfolio and Balance endpoints.
- [x] FastMCP Telegram integration patterns.
- [x] statsmodels ADF test implementation.

## Phase 1: Design & Contracts (COMPLETE)
- [x] Updated data model for Confirmation tracking.
- [x] MCP tools for user confirmation flow.
- [x] Agent context updated.
