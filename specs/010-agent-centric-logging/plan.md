# Implementation Plan: Agent-Centric Observability (ACO)

**Branch**: `010-agent-centric-logging` | **Date**: 2026-04-03 | **Spec**: `/specs/010-agent-centric-logging/spec.md`

## Summary
Build a specialized logging service that translates Python exceptions and system failures into structured, actionable Markdown files (`AGENT_ERROR.md`) specifically for Gemini CLI consumption.

## Technical Context
- **Language**: Python 3.11+
- **Primary Mechanism**: ContextVars for thread-safe breadcrumb tracking.
- **Storage**: Flat files (`AGENT_ERROR.md`, `logs/agent_history.md`).
- **Integration**: Global exception hook + explicit `agent_logger.log_error()` calls in critical paths.

## Constitution Check
- **I. Preservation of Capital**: ✅ Faster error detection and resolution minimizes operational risk.
- **II. Mechanical Rationality**: ✅ Structured error logs provide deterministic feedback to the agent.
- **III. Total Auditability**: ✅ The `agent_history.md` provides a chronological record of system failures and proposed fixes.

## Project Structure

### Documentation
```text
specs/010-agent-centric-logging/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Breadcrumb tracking strategies
└── tasks.md             # Actionable tasks
```

### Source Code
```text
src/
├── services/
│   └── agent_log_service.py # NEW: The core logging logic
└── monitor.py              # UPDATED: Register global exception handler
```

## Phase 0: Research (Completed)
- **Decision**: Use `ContextVars` to track the "Breadcrumb Path". This allows us to append `Monitor.run` -> `process_pair` globally without passing a context object through every method.
- **Decision**: Markdown format will use standard SDD headers to ensure Gemini identifies it as a foundational document.

## Phase 1: Design & Contracts
- **Data Model**: No database schema change required; entirely file-based.
- **Interface**: `AgentLogger.trace(step_name)` and `AgentLogger.capture(exception, context)`.
