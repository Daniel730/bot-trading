# Production Readiness Plan

## Objective
Decide whether the current bot platform is safe for production and define the exact actions needed to close reliability, security, and operability gaps.

## Scope
- Backend API and trading monitor
- Execution engine and brokerage routing
- Redis/Postgres dependencies
- Frontend operational console
- Docker runtime health and logs
- Automated test coverage for stocks + crypto and varying budget/user profiles

## Current Status Snapshot
- Docker services are up (`bot`, `frontend`, `execution-engine`, `mcp-server`, `postgres`, `redis`, `sec-worker`).
- Focused startup/safety/budget tests passed (`14 passed`).
- Integration simulation matrix passed (`10 passed`) including investor persona, value orders, brokerage, brokerage safety, and volatility switching.
- Deployment env validation passes (`scripts/validate_deploy_env.py .env`).

## Risks To Address Before Production Sign-Off
1. **Postgres auth failures observed in logs**
   - Repeated `password authentication failed for user "bot_admin"` and authentication timeout bursts.
   - Indicates prior config drift, failed clients, or credential mismatch attempts.
2. **Execution engine transient transport errors**
   - gRPC connection reset/broken pipe events were observed.
   - May be benign under reconnects, but should be tracked with error-rate SLO and alert thresholds.
3. **No formal multi-environment chaos/load gate in this run**
   - Tests passed functionally, but resilience under degraded dependencies (Redis/Postgres latency, broker timeout storms) is not yet proven in this audit pass.

## Work Plan

### Phase 1 - Observability Hardening (P0)
- Add log-based alerts:
  - Postgres auth failure count per 5 min
  - gRPC transport error rate per 5 min
  - API non-2xx ratio on `/api/system/health` and trading endpoints
- Add dashboard panel for:
  - Order reject rate by venue
  - Timeout/retry counts
  - Kill-switch activations

### Phase 2 - Runtime Safety Validation (P0)
- Run soak test for 2-4 hours in paper mode with mixed stock/crypto pairs.
- Inject controlled failures:
  - Redis restart during scan loop
  - Postgres restart during order/journal writes
  - Execution-engine delayed responses/timeouts
- Verify:
  - graceful degradation
  - no orphaned open exposure
  - restart recovery and idempotent reprocessing

### Phase 3 - Budget/User Matrix Expansion (P1)
- Run matrix scenarios:
  - users: conservative / balanced / aggressive
  - budgets: small / medium / large
  - assets: stocks-only / crypto-only / mixed
- Track for each scenario:
  - rejection reasons
  - drawdown bounds
  - spread guard trigger rates
  - realized PnL volatility

### Phase 4 - Release Gate (P0)
- Require all below to pass before prod sign-off:
  - test suite green
  - no sustained Postgres auth failures
  - no sustained gRPC transport error spikes
  - successful recovery drills
  - on-call runbook updated

## Exit Criteria
- 0 critical runtime alerts over soak window.
- 100% pass on defined scenario matrix.
- Recovery drill success for Redis/Postgres/execution-engine restart.
- Production rollback plan tested and documented.
