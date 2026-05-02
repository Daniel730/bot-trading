# Needs To Analyse Next

## High Priority
- Root cause of `bot_admin` authentication failures in Postgres logs.
- Whether gRPC broken pipe/reset events align with order placement delays/failures.
- Recovery behavior when Redis/Postgres restart during active scans and open position management.
- End-to-end order idempotency under retries/timeouts across T212 and WEB3 paths.

## Medium Priority
- Long-run budget drift across venue caps (`T212_BUDGET_USD`, `WEB3_BUDGET_USD`) under mixed portfolios.
- Distribution of risk rejection reasons by user persona and budget tier.
- Signal veto/approval latency impact on missed opportunities under high pair counts.
- Frontend operational UX under degraded backend states (stale telemetry, partial API failures).

## Additional Scenario Matrix To Execute
- Personas: conservative, balanced, aggressive
- Budget tiers: 1k, 10k, 100k
- Markets:
  - equities only
  - crypto only
  - mixed equities + crypto
- Modes:
  - paper mode
  - live-simulation mode (no real funds)
- Disturbance scenarios:
  - broker timeout burst
  - redis restart
  - postgres restart
  - elevated spread/slippage

## Evidence Needed Before Final Production Approval
- 24h clean operational logs (no repeated auth failure pattern).
- Soak test report with max drawdown, rejection profile, and incident count.
- Verified runbook for incident response and rollback.
- Confirmed on-call alert routing and escalation path.
