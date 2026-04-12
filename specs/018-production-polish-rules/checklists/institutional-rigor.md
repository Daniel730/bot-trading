# Institutional Rigor Checklist: Production-Grade Polish

**Purpose**: Validate specification quality for mission-critical reliability and production-readiness.
**Created**: 2026-04-05
**Feature**: [specs/018-production-polish-rules/spec.md]

## API Cache Rigor (429 Prevention)

- [x] CHK001 - Are all high-frequency endpoints (e.g., portfolio, orders, cash) explicitly mapped for caching? [Completeness, Spec §FR-003]
- [x] CHK002 - Is the 5-second TTL defined as a global constant or per-endpoint configurable value? [Clarity, Spec §FR-003]
- [x] CHK003 - Does the spec define the system's behavior when a request is made exactly at the TTL expiration boundary? [Clarity, Spec §User Story 2]
- [x] CHK004 - Are requirements specified for cache invalidation upon critical events (e.g., order fill confirmation)? [Coverage, Spec Edge Case]
- [x] CHK005 - Is the handling of concurrent identical requests (thundering herd) defined for the cache implementation? [Coverage, Gap]

## Kalman State Persistence & Resilience

- [x] CHK006 - Is the persistence frequency (e.g., every update cycle) clearly specified for the ArbitrageService? [Clarity, Spec §FR-001]
- [x] CHK007 - Are the specific mathematical components (Mean, Covariance, Timestamp) of the persisted state explicitly defined? [Completeness, Spec §Key Entities]
- [x] CHK008 - Does the spec define the recovery protocol for corrupted or unreadable state files (e.g., backup/reset)? [Clarity, Spec Edge Case]
- [x] CHK009 - Is the "success" of a state resume defined by measurable Z-score drift thresholds (SC-001)? [Measurability, Spec §SC-001]
- [x] CHK010 - Are requirements defined for system behavior when the local persistence layer (SQLite) is locked or unavailable? [Coverage, Gap]

## Timezone Synchronization & DST Stability

- [x] CHK011 - Are market operating hours explicitly defined in America/New_York (Wall Street) time rather than server local time? [Clarity, Spec §FR-006]
- [x] CHK012 - Do requirements specify the system behavior during the 2 AM DST shift (March/November) for active monitors? [Coverage, Gap]
- [x] CHK013 - Is the precision for Market Open/Close checks quantified (e.g., ±1 second as per SC-005)? [Measurability, Spec §SC-005]
- [x] CHK014 - Does the spec define behavior for "Early Close" days (e.g., day before Christmas) vs. standard hours? [Coverage, Gap]
- [x] CHK015 - Are requirements for timezone library usage (pytz/zoneinfo) consistent with existing bot infrastructure? [Consistency, Spec §FR-006]

## Capital & Execution Safety

- [x] CHK016 - Is the 1% slippage guard (limitPrice) calculation logic unambiguous for both Buy and Sell orders? [Clarity, Spec §FR-004]
- [x] CHK017 - Does the spec define the fallback behavior if the data_service is unavailable during slippage calculation? [Edge Case, Spec Edge Case]
- [x] CHK018 - Are the units for the DRIP safety cap (gross dividend vs. available cash) explicitly defined to prevent overdraft? [Clarity, Spec §FR-005]

## Traceability & Success Criteria

- [x] CHK019 - Are all functional requirements mapped to measurable Success Criteria outcomes? [Traceability, Spec §Requirements]
- [x] CHK020 - Is the success criterion for Kalman state resume (SC-001) objectively verifiable via logs? [Measurability, Spec §SC-001]
