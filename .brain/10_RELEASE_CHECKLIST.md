# Release Checklist

## Current Release Status

Status: not production-approved.

The repo can be used for local development and paper-mode validation, but unresolved readiness gates remain.

## Before Merging Current Execution-Safety Work

- [x] Verify no-default PostgreSQL password behavior in `infra/docker-compose.backend.yml`.
- [x] Resolve the historical 2026-05-07 six-test monitor failure list.
- [x] Ensure monitor tests mock fill polling and persistence boundaries correctly.
- [ ] Ensure risk-service test fixtures include `max_allowed_fiat` when monitor reads it.
- [ ] Decide expected precedence between orchestrator veto and profit guard veto.
- [ ] Confirm Alpaca ambiguous-submit tests cover both reconciled and unreconciled outcomes.
- [ ] Confirm paper-mode wallet sync tests prove no broker calls.
- [x] Update docs that still imply active T212/Web3 live routing, or restore routing with tests.
- [ ] Re-run the focused test gate in `08_TESTING_PROTOCOL.md`.

## Local Development Release Gate

- [ ] `python -m pytest -q tests/unit/test_monitor.py tests/unit/test_alpaca_provider.py tests/unit/test_spread_guard_unit.py tests/unit/test_startup_guards.py`
- [ ] `python -m pytest -q tests/unit/test_dashboard_wallet_sync.py`
- [ ] `python scripts/validate_deploy_env.py .env`
- [ ] `cd frontend && npm run lint`
- [ ] `cd frontend && npm run test`
- [ ] `cd frontend && npm run build`
- [ ] `cd execution-engine && gradle test --no-daemon`

## Paper-Mode Operational Gate

- [ ] `PAPER_TRADING=true`.
- [ ] `DRY_RUN=true`.
- [ ] `DEV_MODE=false` unless intentionally testing crypto/dev behavior.
- [ ] Dashboard login works with token plus session.
- [ ] `/api/system/health` returns healthy.
- [ ] SSE and WebSocket telemetry authenticate.
- [ ] Scan loop logs active pair processing.
- [ ] Paper trades preserve `signal_id` across reasoning, journal, and ledger.
- [ ] Wallet sync in paper mode returns paper orders and does not submit broker orders.
- [ ] No unresolved `NEEDS_MANUAL_RECONCILIATION` rows before scan.

## Production Sign-Off Gate

- [ ] Full Python test suite green or explicit documented waiver.
- [ ] Frontend lint/test/build green.
- [ ] Java build/test green.
- [ ] Deployment env validation green with non-default secrets.
- [ ] Docker stack healthy.
- [ ] 2-4 hour paper-mode soak completed.
- [ ] Redis restart drill passed.
- [ ] Postgres restart drill passed.
- [ ] Execution-engine restart drill passed.
- [ ] Clean post-recovery logs.
- [ ] No repeated Postgres auth failures.
- [ ] No sustained gRPC transport error spikes.
- [ ] At least one active market scan cycle with non-zero pair processing.
- [ ] No unresolved manual-reconciliation ledger state.
- [ ] `python scripts/run_production_soak_gate.py --duration 2h --require-active-scan` passes against structured soak evidence.
- [ ] Alerts exist for Postgres auth failures, gRPC transport spikes, API non-2xx, order reject rate, timeouts, and kill-switch activations.
- [ ] Rollback plan tested.
- [ ] Operator runbook updated.

## Live Capital Gate

Live capital remains blocked until production sign-off is complete. Even after sign-off:

- [ ] Use the smallest possible budget.
- [ ] Confirm Alpaca paper endpoint versus live endpoint explicitly.
- [ ] Confirm account cash, buying power, and pending-order reads.
- [ ] Confirm Telegram approvals.
- [ ] Confirm sell inventory preflight.
- [ ] Confirm order IDs and client order IDs are visible in broker UI/API.
- [ ] Monitor first live run manually.

## Release Note Template

Use this shape:

```text
Summary:
- What changed.

Safety:
- How execution state, auth, or persistence safety changed.

Verification:
- Commands run and results.

Known risks:
- Anything not fixed.

Operator notes:
- What to check before running.
```
