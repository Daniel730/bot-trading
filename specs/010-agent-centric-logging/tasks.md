# Tasks: Agent-Centric Observability (ACO)

**Input**: Design documents from `/specs/010-agent-centric-logging/`
**Prerequisites**: plan.md (required), spec.md (required)

## Phase 1: Core Infrastructure

- [X] T001 Create `src/services/agent_log_service.py` with `AgentLogger` class.
- [X] T002 Implement `ContextVar` based breadcrumb tracking (stack-like push/pop).
- [X] T003 Implement `generate_markdown_report` logic with remediation hints mapping.
- [X] T004 Ensure `logs/` directory exists and is git-ignored (for history).

## Phase 2: Integration & Instrumentation

- [X] T005 Register global `sys.excepthook` in `src/monitor.py` to catch unhandled crashes.
- [X] T006 Add `@agent_trace` decorator to automatically push/pop breadcrumbs for major service methods.
- [X] T007 Instrument `DataService`, `ArbitrageService`, and `SECService` with breadcrumb markers.
- [X] T008 Add explicit `capture_error` blocks in the `monitor.py` loop to handle concurrent task failures.

## Phase 3: Validation & Polish

- [X] T009 Create a mock error script to verify `AGENT_ERROR.md` generation and content quality.
- [X] T010 Add credential scrubbing logic to prevent API keys from appearing in logs.
- [X] T011 Verify SC-001 (latency) and SC-003 (security).
