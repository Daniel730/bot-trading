# Production Scan Report

## What Was Scanned
- Docker service status and recent compose logs
- Deployment env validation
- Targeted unit/integration tests for startup guards, brokerage safety, budgets, persona behavior, and stock/crypto trading flows

## Runtime Findings

### Container Health
- `bot`: up
- `frontend`: up
- `execution-engine`: up, healthy
- `mcp-server`: up, healthy
- `postgres`: up, healthy
- `redis`: up, healthy
- `sec-worker`: up

### Log Findings
1. **Historical Postgres auth instability**
   - Repeated `password authentication failed for user "bot_admin"` events.
   - Also saw clustered `canceling authentication due to timeout`.
   - Impact: medium to high if recurring in active trading windows.
2. **Execution-engine transport noise**
   - Observed gRPC broken pipe / connection reset events.
   - Impact: medium if transient; high if correlated with order path failures.
3. **Positive signal**
   - Repeated successful `/api/system/health` responses (`200 OK`) from bot.

## Automated Validation Results

### Environment Validation
- `python scripts/validate_deploy_env.py .env`
- Result: **PASS** (`required secrets are set and non-default`)

### Focused Safety/Budget/Startup Tests
- Command:
  - `pytest -q tests/unit/test_startup_guards.py tests/unit/test_brokerage_limits.py tests/unit/test_cash_service.py tests/integration/test_brokerage_safety.py tests/integration/test_dca_service.py`
- Result: **PASS** (`14 passed`)

### Multi-Profile Integration Simulation
- Command:
  - `pytest -q tests/integration/test_investor_persona.py tests/integration/test_value_orders.py tests/integration/test_brokerage.py tests/integration/test_brokerage_safety.py tests/integration/test_risk_volatility_switch.py`
- Result: **PASS** (`10 passed`)

## Production Readiness Verdict
- **Status: NOT FULLY READY FOR PRODUCTION SIGN-OFF YET**
- Reason:
  - Functional and integration simulations are strong in this audit run.
  - But runtime logs show prior authentication and transport reliability issues that must be proven resolved/stable under soak conditions.

## Immediate Recommendations
1. Add alerts for Postgres auth failures and gRPC transport error spikes.
2. Run 2-4 hour paper-mode soak with fault injections (Redis/Postgres/execution-engine restarts).
3. Require a clean log window (no recurring critical auth failures) before go-live.

## Soak/Fault-Injection Update
- Controlled restarts were executed for `redis`, `postgres`, and `execution-engine` with successful service recovery.
- Post-recovery window showed stable bot heartbeats and repeated `200 OK` API responses.
- Production gate remains **not approved** because an extended post-recovery integration smoke run reported one failing test (`test_terminal_command_integration`).
- Detailed evidence is in `docs/soak-fault-injection-report.md`.
