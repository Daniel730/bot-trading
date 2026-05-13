# Fix Priority Queue

Last updated: 2026-05-13

## P0 - Must fix before broker-connected testing

- None currently listed.

## P1 - Must fix before extended personal testing

- None currently listed.

## P2 - Must fix before public release / monetization

- ISSUE-0015 - CI misses broker failure contracts and soak scenarios
  - reason for priority: Important execution regressions can pass local and CI tests.
  - smallest safe fix: Add narrow fake-provider failure contracts to CI before broader soak.
  - required test: Broker failure contract suite in CI.

- ISSUE-0017 - Fire-and-forget background tasks lack watchdog
  - reason for priority: Failures can disappear and degrade operations.
  - smallest safe fix: Track background task handles and log/alert exceptions.
  - required test: Background task failure surfacing test.

- ISSUE-0019 - `close_trade()` overwrites per-leg metadata
  - reason for priority: Forensics and reconciliation become harder after exits.
  - smallest safe fix: Merge close metadata without discarding entry leg metadata.
  - required test: Persistence close metadata preservation test.

## P3 - Can wait

- ISSUE-0020 - Brain ledgers mix historical notes, closed invariants, and open gates
  - reason for priority: Documentation clarity issue after canonical register now exists.
  - smallest safe fix: Continue migrating useful historical notes into canonical issue entries.
  - required test: Not applicable; documentation review.
