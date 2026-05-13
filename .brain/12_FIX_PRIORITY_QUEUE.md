# Fix Priority Queue

Last updated: 2026-05-13

## P0 - Must fix before broker-connected testing

- None currently listed.

## P1 - Must fix before extended personal testing

- None currently listed.

## P2 - Must fix before public release / monetization

- ISSUE-0019 - `close_trade()` overwrites per-leg metadata
  - reason for priority: Forensics and reconciliation become harder after exits.
  - smallest safe fix: Merge close metadata without discarding entry leg metadata.
  - required test: Persistence close metadata preservation test.

## P3 - Can wait

- ISSUE-0020 - Brain ledgers mix historical notes, closed invariants, and open gates
  - reason for priority: Documentation clarity issue after canonical register now exists.
  - smallest safe fix: Continue migrating useful historical notes into canonical issue entries.
  - required test: Not applicable; documentation review.
