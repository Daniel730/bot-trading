# Soak and Fault-Injection Report

## Run Timestamp
- Start: `2026-05-02T15:01:49Z`

## Drills Executed
1. Restarted `redis` during active bot runtime.
2. Restarted `postgres` during active bot runtime.
3. Restarted `execution-engine` during active bot runtime.

## Recovery Outcomes
- `redis`: recovered to `healthy`.
- `postgres`: recovered to `healthy`.
- `execution-engine`: recovered to `healthy`.
- Full compose stack remained up after all drills.

## Post-Recovery Log Window
- Window analyzed from `2026-05-02T15:04:00Z` onward (`logs/recovery_window.log`).
- Observed:
  - repeated bot loop heartbeat (`Iteration Complete`).
  - repeated API `200 OK` for summary/charts/positions/health/wallet endpoints.
  - no new critical crash signatures in the captured window.

## Post-Drill Tests
- `pytest -q tests/integration/test_brokerage_safety.py tests/integration/test_data_resilience.py`
  - Result: `2 passed`.
- Extended post-recovery smoke run:
  - `pytest -q tests/integration/test_brokerage_safety.py tests/integration/test_data_resilience.py tests/integration/test_terminal_bridge.py`
  - Result: `1 failed, 4 passed`
  - Failure: `test_terminal_command_integration` (missing `session_token` in `/api/auth/login` response path in test assumptions).

## Gate Decision (Per Requested Policy)
- Policy requested: **clean log window + recovery drill success required before production approval**.
- Result:
  - Recovery drill: **PASS**
  - Clean log window: **PASS** for the captured window
  - Full post-recovery smoke suite: **NOT FULLY PASSING** (terminal bridge integration failure)

## Production Approval Status
- **NOT APPROVED YET**.

## Required Next Actions Before Approval
1. Fix or update `tests/integration/test_terminal_bridge.py` auth/session expectation and re-run.
2. Run a longer soak interval (target 2-4h from readiness plan) with same recovery checks.
3. Confirm at least one active market scan cycle with non-zero pair processing under realistic market conditions.
