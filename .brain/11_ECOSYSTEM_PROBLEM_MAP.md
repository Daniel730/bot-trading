# Ecosystem Problem Map

Last updated: 2026-05-13

Canonical issue details are in `.brain/04_AUDIT_LEDGER.md`.

## Execution Safety

- ISSUE-0015 - CI lacks the broker failure contract tests that should catch execution regressions.

## Exit Safety

- ISSUE-0019 - Close persistence can overwrite order metadata needed for forensic reconciliation.
## Risk Management

- None currently listed.

## Strategy Logic

- None currently listed.

## Data Pipeline

- None currently listed.

## Persistence and State

- ISSUE-0019 - `close_trade()` replaces entry metadata with close metadata.
- ISSUE-0020 - Brain state previously lacked one canonical issue register.

## Orchestration

- ISSUE-0015 - Automated gates do not cover broker failure contracts and soak scenarios.
- ISSUE-0017 - Background tasks are not centrally watched or surfaced.

## Observability

- ISSUE-0017 - Fire-and-forget task failures can disappear into logs.

## Testing

- ISSUE-0015 - Missing broker fake-provider and Java gRPC failure contract suites.
## Configuration and Deployment

- ISSUE-0015 - CI quality lanes do not include all runtime safety gates.

## Frontend / Dashboard

- None currently listed.

## Documentation / Brain Quality

- ISSUE-0020 - Historical brain notes need canonical issue IDs and maps.
