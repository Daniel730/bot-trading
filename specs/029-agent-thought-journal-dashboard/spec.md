# Feature Specification: Agent Thought Journal Dashboard

**Feature Branch**: `029-agent-thought-journal-dashboard`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: User description: "1. Architect an asynchronous WebSocket telemetry stream from the Python Orchestrator to the React/vanilla frontend. 2. Implement the 'Pixel Bot' UI element that dynamically updates its sprite/expression (idle, doubt, glitch, happy) based on the agent's Thought Journal and Risk States. 3. Visually expose the active Risk Multiplier, Current Drawdown %, and Volatility Status (L2 Shannon Entropy level). 4. The frontend must use a strict ring-buffer (max 100 entries) for the Thought Journal logs to prevent DOM bloat and memory leaks. 5. The backend telemetry service must use a decoupled fire-and-forget pattern to guarantee zero latency impact on the core arbitrage execution hot path."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-time Risk HUD (Priority: P1)

As a trader, I want to see the real-time risk parameters (Risk Multiplier, Drawdown, Volatility Status) on the dashboard, so I can understand why the bot is scaling down or halting trades without checking logs.

**Acceptance Scenarios**:

1. **Given** the bot is running in `DEV_MODE` with high market entropy, **When** I look at the dashboard, **Then** the "Volatility Status" must display "HIGH_VOLATILITY" and the entropy level must be visible.
2. **Given** a simulated portfolio drawdown of 10%, **When** the dashboard updates, **Then** the "Risk Multiplier" must reflect the ~0.33 scaling factor.

---

### User Story 2 - Pixel Bot Emotional State (Priority: P1)

As a quant developer, I want the Pixel Bot to reflect the system's health and market conditions via visual expressions, so I can intuitively sense the risk regime.

**Acceptance Scenarios**:

1. **Given** the Volatility Switch is triggered (High Entropy), **When** the dashboard updates, **Then** the Pixel Bot expression must switch to "GLITCH".
2. **Given** a high Sharpe ratio and active execution, **When** trades are delta-neutral, **Then** the Pixel Bot must appear "HAPPY/AGGRESSIVE".
3. **Given** a Kalman Filter covariance mismatch or L2 fill achievability < 90%, **When** the bot is uncertain, **Then** it must display "DOUBT".

---

### User Story 3 - Zero-Latency Telemetry & Stable UI (Priority: P1)

As a systems architect, I want the telemetry streaming and UI rendering to be non-blocking and memory-safe, ensuring the command center remains responsive during high-volume signal bursts.

**Acceptance Scenarios**:

1. **Given** a burst of 10,000 telemetry messages, **When** the dashboard is open, **Then** the browser memory must remain stable due to the 100-entry ring-buffer.
2. **Given** hardware-accelerated CSS is enabled, **When** the Pixel Bot animates, **Then** the main thread must not experience layout thrashing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement a WebSocket server endpoint in `DashboardService` (FastAPI) to stream real-time JSON updates.
- **FR-002**: `TelemetryService` MUST implement an asynchronous, non-blocking `push_update` method using a `fire-and-forget` pattern.
- **FR-003**: System MUST stream the following risk metrics: `risk_multiplier`, `max_drawdown`, `volatility_status`, and `l2_entropy`.
- **FR-004**: System MUST stream agent thoughts including `bull_argument`, `bear_argument`, and `fundamental_summary`.
- **FR-005**: Pixel Bot MUST support 4 states: `IDLE` (monitoring/SEC), `DOUBT` (low confidence/Kalman mismatch), `GLITCH` (high volatility), `HAPPY` (high sharpe/executing).
- **FR-006**: Frontend MUST implement a strict ring-buffer (max 100 entries) for the Thought Journal logs to prevent DOM bloat.
- **FR-007**: Frontend MUST use hardware-accelerated CSS (e.g., `translate3d`, `will-change`) for all animations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Dashboard updates arrive within 100ms of the backend event.
- **SC-002**: Zero increase in `ExecuteTrade` gRPC latency when telemetry is active.
- **SC-003**: Frontend memory usage remains < 256MB even after 24h of continuous telemetry streaming.
- **SC-004**: Pixel Bot state transitions occur in < 50ms upon receipt of the corresponding telemetry message.

## Assumptions

- **Browser Support**: The user's browser supports modern WebSockets and hardware acceleration.
- **Network Stability**: The connection between the bot and the dashboard is stable enough for streaming.
- **Vite/React**: The frontend uses Vite and React as per the established project structure.
