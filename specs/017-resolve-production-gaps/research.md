# Research & Design Decisions: Resolve Production Rigor Gaps

This document resolves the technical design choices for the safety enhancements mandated by the `production_rigor.md` checklist.

## Decision 1: Price Retrieval Retry Strategy (FR-001)

- **Decision**: Utilize the `tenacity` library to wrap `DataService.get_latest_price` calls.
- **Rationale**: `tenacity` provides a declarative way to handle retries and exponential backoff, reducing boilerplate and ensuring consistency with industry standards.
- **Implementation**: 
  - Max attempts: 3.
  - Wait schedule: `wait_exponential(multiplier=1, min=1, max=4)`.
- **Alternatives Considered**: Manual `asyncio.sleep` loops (rejected as error-prone).

## Decision 2: Circuit Breaker Persistence (FR-003, FR-004)

- **Decision**: Persist consecutive failure counts and system status in a new SQLite table `system_state`.
- **Rationale**: Memory-only tracking would reset on bot restarts, potentially allowing the bot to bypass the circuit breaker during a series of crashes/restarts.
- **Implementation**:
  - Table: `system_state (key TEXT PRIMARY KEY, value TEXT)`.
  - Keys: `consecutive_api_timeouts` (int), `operational_status` (`NORMAL`|`DEGRADED_MODE`).
  - `Orchestrator` will increment/reset this state.
- **Alternatives Considered**: In-memory global variable (rejected due to lack of persistence).

## Decision 3: EU UCITS Compliance Mapping (FR-005)

- **Decision**: Hardcode the mapping dictionary in `RiskService`.
- **Rationale**: These mappings are for major US indices and are relatively static. Hardcoding ensures high performance and no external dependency for critical hedging.
- **Mapping**:
  - SPY -> XSPS.L
  - QQQ -> SQQQ.L
  - IWM -> R2SC.L
- **Alternatives Considered**: Database-driven mapping (rejected as overkill for 3 entries).

## Decision 4: Micro-Budget Friction Enforcement (FR-007)

- **Decision**: Update `RiskService.calculate_friction` to accept an `amount` parameter and apply the $5.00 threshold check.
- **Rationale**: Friction is non-linear at very low budgets. A $0.03 fee on $2.00 is exactly 1.5%.
- **Status Codes**: 
  - `ACCEPTED`
  - `FRICTION_REJECT`
- **Alternatives Considered**: Percent-only check (rejected because $5.00 is a specific business threshold for "micro-budget" safety).

## Decision 5: Statistical Intercept Reinforcement (FR-008)

- **Decision**: Mandatory use of `sm.add_constant()` in `arbitrage_service.py`.
- **Rationale**: Standard OLS in `statsmodels` does not include an intercept by default. Without it, the model assumes the spread mean is zero, leading to biased hedge ratios and false cointegration signals if a constant offset exists.
- **Alternatives Considered**: None; this is a mathematical requirement for correctness.
