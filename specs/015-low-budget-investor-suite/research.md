# Research: Elite Micro-Investor Bot (Phase 0)

## Decisions & Findings

### 1. WebSocket & Order Book Shadowing
- **Decision**: Use **Polygon.io WebSocket** for real-time market data streaming (LOB Shadowing) and **Redis** as the low-latency cache for the "Local Order Book".
- **Rationale**: Trading 212 API is REST-only. The existing `DataService` already connects to Polygon, but it lacks a persistent cache for sub-100ms trade evaluations.
- **Alternatives**: Alpaca WebSockets (Requires separate funding/API), `yfinance` streaming (too slow/unreliable).

### 2. Infrastructure Expansion (Redis)
- **Decision**: Introduce Redis as a mandatory service in `docker-compose.backend.yml`.
- **Rationale**: SQLite is too slow for sub-50ms price-check loops under high-frequency signal generation. Redis allows for atomic updates to price snapshots.

### 3. Interactive Visualizations & Voice Synthesis
- **Decision**: Use `matplotlib` for generating Monte Carlo "What-If" charts and **OpenAI TTS-1** for voice notes.
- **Rationale**: `matplotlib` is standard and produces high-quality PNGs for Telegram. OpenAI TTS-1 provides a professional "Advisor" voice with minimal latency (< 2s generation).
- **Alternatives**: `pyttsx3` (robotic, low-quality), `gTTS` (requires internet, lacks voice choice).

### 4. Idle-Cash Yield Sweeps
- **Decision**: Implement `CashManagementService` targeting **SGOV** (iShares 0-3 Month Treasury Bond ETF) for sweeps.
- **Rationale**: T212 allows fractional buys of SGOV. It offers a 5%+ yield with near-zero volatility, acting as a "sweep account" for idle USD.

### 5. Federated Swarm Intelligence
- **Decision**: Implement an anonymized JSON telemetry payload (`TelemetryRecord`) to a mock central server endpoint.
- **Rationale**: Allows the system to collect "Ghost Trading" outcomes (theoretical vs actual) to refine agent weights across the entire user base.

## Unknowns Resolved
- **Redis availability**: Confirmed NOT present. Added as a requirement.
- **T212 WebSocket support**: Confirmed NOT present. Polygon.io + Redis is the path.
- **Monte Carlo implementation**: Will utilize `scipy.stats` for Normal/T-distributions for returns simulation.
