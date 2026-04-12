# Feature Specification: Shadow-to-Live Transition

**Feature Branch**: `031-shadow-to-live`  
**Created**: 2026-04-07  
**Status**: Draft  
**Input**: User description: "feature="030-shadow-to-live-transition" context="src/config.py,execution-engine/src/main/java/com/arbitrage/engine/config/EnvironmentConfig.java,scripts/calibration_analysis.py,execution-engine/src/main/java/com/arbitrage/engine/api/ExecutionServiceImpl.java" requirements="1. Architect a strict LIVE_CAPITAL_DANGER boolean flag. 2. If LIVE_CAPITAL_DANGER is true, the Python and Java engines must enforce a mandatory startup check against the Redis L2 entropy baselines gathered during Shadow Mode; refusing to boot if baselines are missing. 3. Architect a gRPC 'Kill-Switch' endpoint that completely bypasses the Python Orchestrator, instructing the Java engine to immediately halt all new routing, cancel all pending L2 orders, and liquidate open positions via the LiveBroker. 4. Ensure the SEC RAG daemon logic is locked to pre-market execution only." The Senior QA Engineer: Your summary conveniently omits two critical constraints from the mandate. First, what is the maxsize of your asyncio.Queue? If you left it unbounded, a slow WebSocket consumer or a disconnected frontend will cause the Python backend to queue messages indefinitely until the Orchestrator dies of an Out-Of-Memory (OOM) error. Second, I do not see explicit confirmation of the 100-entry strict ring-buffer in the frontend. If your React/Vanilla DOM is just appending <div> elements into infinity during a 5,000-message Volatility Switch burst, the browser will lock up. I am running a heap snapshot analysis on your PR. If the memory leaks, the build fails. The Senior UI/UX Specialist: You also completely neglected to mention the Pixel Bot sprite integration. The "Thought Journal" text is secondary. If the multi-agent state is not directly mapped to the visual expressions (idle, doubt, glitch, happy) for at-a-glance situational awareness, you have failed the situational awareness mandate. Cognitive overload during a flash crash will result in operator paralysis. Ensure the sprite state machine is perfectly synced to the Risk HUD. The Lead Quant Developer: Assuming the infrastructure does not crash under its own weight, we finally have the tooling to observe the math. The system has been running in DEV_MODE=true over the weekend, absorbing raw L2 crypto data. We must now run the calibration_analysis.py scripts against the PostgreSQL ledger and Redis L2 snapshots. If the L2 entropy baselines do not justify our initial Kalman covariance matrix, we re-tune. We do not guess. The Senior Software Architect: The weekend crucible is concluding. Our infrastructure is mostly hardened. It is time to architect the final, most dangerous phase: The Shadow-to-Live Transition. When we move to live equities on the NYSE/NASDAQ, the transition must require absolutely zero code changes—only environment variables. The system must also possess a mandatory hardware-level 'Kill Switch' that bypasses the Orchestrator entirely to liquidate and halt the Java Virtual Threads."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safe Live Deployment (Priority: P1)

As a System Operator, I want the trading engine to refuse to start in Live mode if it lacks sufficient historical data from Shadow mode, so that I don't risk capital on uncalibrated models.

**Why this priority**: Preventing catastrophic financial loss due to unverified models is the highest priority for the system.

**Independent Test**: Can be tested by attempting to start the system with `LIVE_CAPITAL_DANGER=true` while deleting or emptying the Redis entropy baselines.

**Acceptance Scenarios**:

1. **Given** the environment variable `LIVE_CAPITAL_DANGER` is set to `true`, **When** the system starts and Redis entropy baselines are missing, **Then** both Python and Java engines must log a critical error and terminate immediately.
2. **Given** the environment variable `LIVE_CAPITAL_DANGER` is set to `true`, **When** the system starts and valid Redis entropy baselines are present, **Then** the system proceeds with the boot sequence normally.

---

### User Story 2 - Emergency Liquidation & Halt (Priority: P1)

As a Risk Manager, I want a "Kill Switch" that bypasses all AI decision-making to immediately stop trading and close all positions, so that I can protect capital during a flash crash or system malfunction.

**Why this priority**: A fail-safe mechanism is mandatory for high-frequency live trading to handle unforeseen market events.

**Independent Test**: Can be tested by triggering the Kill Switch gRPC endpoint while the system is actively trading and verifying that all orders are cancelled and positions are liquidated.

**Acceptance Scenarios**:

1. **Given** the system is actively trading, **When** the Kill Switch is triggered, **Then** the Java engine must immediately stop routing new signals, cancel all pending L2 orders, and liquidate all open positions.
2. **Given** the Kill Switch is active, **When** the Python Orchestrator attempts to send new signals, **Then** the Java engine must ignore them until the switch is manually reset.

---

### User Story 3 - Visual Situational Awareness (Priority: P2)

As a Trader, I want the Pixel Bot's emotional state to be perfectly synced with the Risk HUD and market volatility, so that I can immediately sense the system's "mood" and risk regime at a glance.

**Why this priority**: Reduces cognitive load and prevents operator paralysis during high-stress market conditions.

**Independent Test**: Can be tested by simulating a volatility spike (high entropy) and verifying the Pixel Bot enters the `GLITCH` state in sync with the Risk HUD update.

**Acceptance Scenarios**:

1. **Given** the market entropy exceeds 0.8, **When** the Risk HUD updates, **Then** the Pixel Bot must transition to the `GLITCH` mood with zero perceived delay.
2. **Given** the system has high confidence in a signal, **When** the thought journal updates, **Then** the Pixel Bot must transition to the `HAPPY` mood.

---

### Edge Cases

- **Partial Baseline Failure**: What happens if some L2 entropy baselines exist but are stale or corrupted? (Assumption: System treats stale data as missing and refuses to boot).
- **Kill Switch Network Failure**: How does the Java engine handle the Kill Switch if the gRPC connection from the Orchestrator is lost? (Assumption: The Java engine possesses a local "Heartbeat" or "Dead-man's switch" that triggers liquidation if the link is severed).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST enforce a `LIVE_CAPITAL_DANGER` environment flag that gates all live execution logic.
- **FR-002**: Python and Java engines MUST perform a mandatory startup validation against Redis L2 entropy baselines when `LIVE_CAPITAL_DANGER` is true.
- **FR-003**: System MUST provide a gRPC "Kill Switch" endpoint that operates independently of the Python Orchestrator's decision loop.
- **FR-004**: The Java Execution Engine MUST implement immediate order cancellation and position liquidation upon Kill Switch activation.
- **FR-005**: The SEC RAG daemon MUST be restricted to execution only during the pre-market window of 04:00 - 09:15 EST and must be hard-killed at exactly 09:15 EST to ensure a 15-minute infrastructure quiet period before market open.
- **FR-006**: The Python telemetry service MUST enforce a `maxsize` of 10,000 items for the `asyncio.Queue`. The producer MUST use non-blocking `put_nowait()` and immediately drop telemetry frames (catch `QueueFull`) if the queue is full to ensure the arbitrage execution hot-path never blocks.
- **FR-007**: The Frontend Thought Journal MUST implement a 100-entry strict ring-buffer to maintain browser performance.
- **FR-008**: The Pixel Bot sprite state machine MUST be bi-directionally synced with the Risk HUD telemetry.
- **FR-009**: The transition from Shadow to Live MUST be achievable solely via environment variables with zero code modifications.

### Key Entities *(include if feature involves data)*

- **RiskHUD**: Data structure containing current multipliers, drawdown, entropy, and volatility status.
- **EntropyBaseline**: Historical L2 snapshots stored in Redis used to calibrate the Kalman Filter.
- **KillSwitchSignal**: A high-priority gRPC message that triggers immediate cessation of trading activities.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System startup validation completes in under 2 seconds.
- **SC-002**: Kill Switch trigger-to-liquidation latency is under 500ms (excluding broker API latency).
- **SC-003**: Frontend Dashboard remains responsive (60fps) even during a 5,000-message-per-second telemetry burst.
- **SC-004**: Transition from Shadow to Live environment is completed in under 5 minutes by a single operator.
- **SC-005**: 0% loss of messages in the telemetry queue until the `maxsize` limit is reached.

## Assumptions

- **Environment Config**: It is assumed that the `EnvironmentConfig` in Java and `config.py` in Python are the single sources of truth for the `LIVE_CAPITAL_DANGER` flag.
- **Pre-Market Definition**: It is assumed that "pre-market" refers to the official NYSE/NASDAQ pre-market session (04:00 - 09:30 EST) unless specified otherwise.
- **Hardware-level Switch**: It is assumed that "hardware-level" refers to a dedicated, high-availability gRPC channel or separate process that can send signals directly to the Java Virtual Threads, bypassing the primary application logic.
- **Liquidation Strategy**: Position liquidation will use Market Orders to ensure immediate execution during emergency halts.
