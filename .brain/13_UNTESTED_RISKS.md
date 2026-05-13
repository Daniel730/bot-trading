# Untested Risks

Last updated: 2026-05-13

## Critical Untested Risks

- None currently listed.

## High Untested Risks

- None currently listed.

## Medium Untested Risks

- ISSUE-0019
  - missing test: Close metadata preserves entry leg metadata.
  - expected failing scenario: Closing a trade overwrites order ids/statuses needed for later reconciliation.
  - suggested test file/name: `tests/unit/test_persistence_service.py::test_close_trade_preserves_entry_leg_metadata`

## Low Untested Risks

- ISSUE-0020
  - missing test: Documentation consistency review only.
  - expected failing scenario: Historical notes drift from canonical issue register.
  - suggested test file/name: Not applicable; periodic documentation review.
