# Checklist: Model Calibration Full Audit (PR Gate)

**Purpose**: This checklist serves as a "Unit Test for English" to validate the quality, clarity, and completeness of the Model Calibration requirements. It acts as a mandatory PR gate for feature `027-model-calibration`.
**Created**: 2026-04-06
**Status**: Active

## Requirement Completeness
- [X] CHK001 - Are the high-precision latency interceptors specified for both the Python (Client) and Java (Server) sides? [Completeness, Spec §FR-001]
- [X] CHK002 - Is the reporting format for Shadow Mode fill accuracy vs. theoretical mid-price explicitly defined? [Clarity, Spec §FR-003]
- [X] CHK003 - Are the specific Redis keyspace and TTL (Time-To-Live) for idempotency locks documented? [Clarity, DataModel]
- [X] CHK004 - Does the spec define the exact error payload and HTTP/gRPC status code for "Duplicate Request" responses? [Completeness, Spec Story 3]

## Requirement Clarity & Precision
- [X] CHK005 - Is the "Alpha Stale Time" calculation formula (Engine Received - Orchestrator Sent) unambiguous regarding unit of measure (e.g., nanoseconds vs. microseconds)? [Clarity, Spec §FR-002]
- [X] CHK006 - Is the `LATENCY_ALARM` threshold "consistently exceeds 1ms" quantified (e.g., 5 consecutive samples, or X% over 1 minute)? [Clarity, Spec §FR-006]
- [X] CHK007 - Is "walk-the-book" VWAP calculation defined with specific depth requirements (e.g., top 5 levels vs. full book)? [Clarity, Spec Story 2]
- [X] CHK008 - Are the criteria for "L2 snapshot validity" (e.g., max age in ms, minimum depth) explicitly quantified? [Clarity, Spec §FR-004]

## Clock Synchronization (Lead Quant Mandate)
- [X] CHK009 - Is the mechanism for ensuring clock synchronization (e.g., PTP, NTP/Chrony, or Shared Monotonic Reference) explicitly mandated for cross-environment measurement? [Clarity, Spec §FR-007]
- [X] CHK010 - Does the spec define a "Clock Drift Tolerance" threshold, above which latency metrics are marked as invalid? [Clarity, Spec §FR-007]
- [X] CHK011 - Is there a requirement to log the synchronization status of the host clocks alongside the RTT metrics? [Clarity, DataModel]

## Scenario & Edge Case Coverage
- [X] CHK012 - Is the system behavior defined for Redis connection timeouts or failures during an idempotency check? [Coverage, Spec §FR-008]
- [X] CHK013 - Does the spec define the fallback behavior when L2 data is missing or stale during a Shadow Trade audit? [Coverage, Exception Flow]
- [X] CHK014 - Are requirements defined for handling gRPC "deadline exceeded" scenarios within the latency interceptor? [Coverage, Contract]

## Measurability & Success Criteria
- [X] CHK015 - Can the "100% verifiable" success criterion for fill prices be objectively measured with an automated script? [Measurability, Spec §SC-002]
- [X] CHK016 - Is the "zero (0) duplicate records" target verifiable under a specific concurrency load (e.g., 1000 req/sec)? [Measurability, Spec §SC-003]
- [X] CHK017 - Can "unachievable" targets (spread < slippage) be objectively identified based on the provided L2 requirements? [Measurability, Spec §SC-004]

## gRPC Cross-Language Contracts (Architectural Mandate)
- [X] CHK018 - Are the data types and precision for timestamps (e.g., float64 vs. nanosecond integer) consistently defined for both Python and Java environments? [Consistency, Contract]
- [X] CHK019 - Is the interceptor contract for metadata propagation (e.g., trace IDs, sent-timestamps) explicitly specified for cross-language alignment? [Clarity, Contract]
- [X] CHK020 - Does the spec define the behavior for mismatched gRPC message versions between the Orchestrator and the Engine? [Coverage, Contract]

## Simulation Fidelity & Liquidity (Lead Quant Mandate)
- [X] CHK021 - Are requirements defined for trade size penalties when the Shadow Trade quantity exceeds the available top-of-book depth? [Completeness, Spec §FR-009]
- [X] CHK022 - Is the slippage model for "walking the book" (VWAP vs. Mid-price) explicitly specified for Shadow Mode simulation? [Clarity, Spec Story 2]
- [X] CHK023 - Does the spec define the minimum required L2 depth (number of levels) for a valid "Achievable Alpha" calculation? [Clarity, Spec Story 2]
- [X] CHK024 - Is the "market impact" of simulated trades addressed in the fill realism requirements? [Coverage, Spec §FR-009]
