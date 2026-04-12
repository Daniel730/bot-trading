# Feature Specification: Audit Bug Fixes & System Hardening

**Feature Branch**: `033-fix-audit-bugs`  
**Created**: 2026-04-12  
**Status**: Draft  
**Input**: User description: "Here's the full picture from the multi-environment audit: --- Audit Results — 17 New Bugs Found New Critical (5) ┌──────┬──────────────────────────────────┬────────────────────────────────────────────────────────────────────────────┐ │ ID │ Where │ What │ ├──────┼──────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤ │ T-01 │ risk_service.py:146 │ get_portfolio() missing await in check_hedging() → DEFCON-1 auto-hedging │ │ │ │ protocol never runs │ ├──────┼──────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤ │ A-01 │ cash_management_service.py:20,46 │ Two missing awaits → cash sweep and trade liquidation never execute │ ├──────┼──────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤ │ S-01 │ config.py:37 │ Default Postgres password \"bot_pass\" hardcoded — silent security │ │ │ │ regression if env var unset │ ├──────┼──────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤ │ S-02 │ dashboard_service.py:118 │ Default dashboard token \"arbi-elite-2026\" hardcoded — unauthenticated │ │ │ │ access │ └──────┴──────────────────────────────────┴────────────────────────────────────────────────────────────────────────────┘ New High (8) ┌──────┬───────────────────────────────────┬───────────────────────────────────────────────────────────────────────────┐ │ ID │ Where │ What │ ├──────┼───────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤ │ A-03 │ monitor.py:184,213 │ self.active_signals mutated by concurrent coroutines under asyncio.gather │ │ │ │ — list corruption under load │ ├──────┼───────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤ │ S-03 │ dashboard_service.py:114 │ DEV_MODE=True bypasses all dashboard auth completely │ ├──────┼───────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤ │ S-07 │ monitor.py, orchestrator.py │ Zero test coverage for execute_trade, _close_position, orchestrator veto │ │ │ │ paths │ ├──────┼───────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤ │ S-08 │ test_brokerage.py:50 │ Another broken test — get_portfolio() without await │ ├──────┼───────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤ │ J-01 │ ExecutionServiceImpl.java:105 │ getLatestBook() result not null-checked → NPE inside VwapCalculator │ ├──────┼───────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤ │ J-02 │ ExecutionServiceImpl.java:185,196 │ .block() on gRPC handler thread — exhausts thread pool on slow DB/Redis │ ├──────┼───────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤ │ J-03 │ ExecutionServiceImpl.java:176 │ responseObserver.onCompleted() can fire twice — gRPC contract violation │ └──────┴───────────────────────────────────┴───────────────────────────────────────────────────────────────────────────┘ New Medium/Low (4) REGION config undefined (EU hedge unreachable), asyncio.get_event_loop() deprecated in 5 files (fails Python 3.12+), unbounded WebSocket list, Docker healthcheck probing wrong URL, zero-quantity rounding trap, unused Java variable."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Financial Safety & Protocol Integrity (Priority: P1)

As a Bot Administrator, I need the bot's risk and cash management protocols to execute reliably so that capital is protected and trades are liquidated when necessary.

**Why this priority**: Critical financial risk. Incomplete asynchronous executions cause silent failures of auto-hedging and liquidation, which can lead to catastrophic losses.

**Independent Test**: Can be tested by simulating a emergency state and verifying that the auto-hedging protocol completes all steps, and by triggering a cash sweep/liquidation and verifying execution results in the ledger.

**Acceptance Scenarios**:

1. **Given** a hedging condition is met, **When** the hedging protocol is triggered, **Then** the portfolio data is fully retrieved and the protocol executes to completion without skipping steps.
2. **Given** a liquidation signal is received, **When** the cash management service processes it, **Then** all internal operations complete sequentially and trade liquidation is confirmed.

---

### User Story 2 - Security Hardening & Authentication (Priority: P1)

As a Security-conscious Operator, I need the system to use secure, environment-defined credentials and enforce authentication for the dashboard at all times.

**Why this priority**: Hardcoded credentials and authentication bypasses are high-severity security risks that allow unauthorized access to the trading bot.

**Independent Test**: Can be tested by attempting to access the dashboard with developer mode active without a token, and by verifying that the system does not fall back to default passwords when environment variables are missing.

**Acceptance Scenarios**:

1. **Given** developer mode is active, **When** accessing the dashboard, **Then** valid authentication is still required.
2. **Given** no database password is provided in environment variables, **When** the system starts, **Then** it does NOT use a default "placeholder" password.

---

### User Story 3 - System Stability & Performance (Priority: P1)

As a High-Frequency Trader, I need the bot to remain stable under high concurrency and load without data corruption or service hangs.

**Why this priority**: Concurrent access issues lead to data corruption in active signals or complete service hangs due to thread pool exhaustion, causing missed trades or incorrect executions.

**Independent Test**: Can be tested with high-concurrency load tests for signal monitoring and execution requests.

**Acceptance Scenarios**:

1. **Given** multiple concurrent signals, **When** the internal signal list is updated, **Then** the list remains consistent and no data corruption occurs.
2. **Given** high request volume, **When** the execution service interacts with storage, **Then** it does not block processing threads and remains responsive.

---

### User Story 4 - Modernization & Maintenance (Priority: P2)

As a Developer, I need the codebase to use supported system APIs and have correct infrastructure configurations to ensure long-term maintainability.

**Why this priority**: Avoids runtime failures on newer software versions and ensures infrastructure monitoring tools work correctly.

**Independent Test**: Run tests on the latest supported environment versions and verify container health status.

**Acceptance Scenarios**:

1. **Given** a modern runtime environment, **When** the bot runs, **Then** no deprecation warnings or errors occur from system loop access.
2. **Given** a running container, **When** the health monitoring executes, **Then** it probes the correct endpoint and returns a healthy status.

---

### Edge Cases

- What happens when a data snapshot (e.g., order book) is unavailable? (System MUST handle safely without crashing).
- How does the system handle completion signals in streaming protocols? (MUST NOT signal completion more than once).
- What happens with zero-quantity rounding? (System MUST prevent trades with rounded-to-zero quantities).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Risk service MUST ensure full completion of portfolio retrieval during auto-hedging.
- **FR-002**: Cash management service MUST ensure full completion of all operations in cash sweep and trade liquidation.
- **FR-003**: System MUST NOT contain hardcoded default passwords for database access.
- **FR-004**: System MUST NOT contain hardcoded default tokens for dashboard access.
- **FR-005**: Dashboard authentication MUST be enforced regardless of the operation mode (e.g., developer mode).
- **FR-006**: Signal monitoring MUST ensure atomic updates to active signal lists to prevent corruption under load.
- **FR-007**: Execution service MUST validate data snapshots (like order books) before processing to prevent null-reference errors.
- **FR-008**: Execution service MUST use non-blocking patterns for storage interactions to prevent thread exhaustion.
- **FR-009**: Streaming protocol handlers MUST ensure completion signals are sent exactly once.
- **FR-010**: All system loop access MUST use modern, supported API calls compatible with current runtime versions.
- **FR-011**: Infrastructure healthchecks MUST be updated to probe the correct service endpoint.
- **FR-012**: System MUST implement a validation trap to prevent orders with zero-quantities due to rounding.
- **FR-013**: System MUST define region-specific configurations to ensure all hedging endpoints are reachable.
- **FR-014**: Communication buffers (e.g., WebSocket lists) MUST be bounded to prevent excessive memory usage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 17 identified audit bugs are resolved and verified by automated tests.
- **SC-002**: Critical paths (hedging, liquidation, trade execution) have full test coverage.
- **SC-003**: Zero hardcoded secrets detected in the codebase by static analysis tools.
- **SC-004**: Execution service handles high request volume (e.g., 1000 req/sec) with low latency (e.g., <5ms) without resource exhaustion.
- **SC-005**: Infrastructure health monitoring returns 'healthy' status consistently.

## Assumptions

- Environment variables will be used to provide necessary passwords and tokens.
- The system will be deployed on currently supported runtime versions.
- Infrastructure supports the necessary endpoints for health monitoring.
- Standard concurrency control mechanisms are available in the target languages.
