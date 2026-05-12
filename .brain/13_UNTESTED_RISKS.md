# Untested Risks

Last updated: 2026-05-12

## Critical Untested Risks

- None currently listed.

## High Untested Risks

- None currently listed.

## Medium Untested Risks

- ISSUE-0014
  - missing test: Local setup uses the same dependency path as CI/Docker.
  - expected failing scenario: Local command passes while containerized startup fails from dependency mismatch.
  - suggested test file/name: `tests/unit/test_backend_compose_secrets.py::test_local_dependency_path_matches_container_expectation`

- ISSUE-0015
  - missing test: CI includes broker failure contract tests.
  - expected failing scenario: Broker timeout/rejection behavior regresses without CI failure.
  - suggested test file/name: `.github/workflows/*` job running broker fake-provider tests.

- ISSUE-0017
  - missing test: Background task exceptions surface to logs/status.
  - expected failing scenario: A fire-and-forget task raises and operator never sees degraded state.
  - suggested test file/name: `tests/unit/test_monitor.py::test_background_task_failure_is_observed`

- ISSUE-0019
  - missing test: Close metadata preserves entry leg metadata.
  - expected failing scenario: Closing a trade overwrites order ids/statuses needed for later reconciliation.
  - suggested test file/name: `tests/unit/test_persistence_service.py::test_close_trade_preserves_entry_leg_metadata`

## Low Untested Risks

- ISSUE-0020
  - missing test: Documentation consistency review only.
  - expected failing scenario: Historical notes drift from canonical issue register.
  - suggested test file/name: Not applicable; periodic documentation review.
