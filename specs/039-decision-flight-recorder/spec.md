# Feature Specification: Decision Flight Recorder

**Feature Branch**: `039-decision-flight-recorder` / `feat/decision-flight-recorder`
**Created**: 2026-07-16
**Status**: MVP
**Input**: AI-oriented decision trails at branch points (not printf-everything); incident pack export for Cursor/Hermes

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Compact always-on decision trail (Priority: P1)

While the monitor scans pairs, every meaningful branch (skip / veto / execute / anomaly) appends a compact `DecisionEvent` to an in-memory ring buffer, tagged with `scan_id` / `pair_id` / `signal_id` via contextvars.

**Why this priority**: Without a correlated trail, debugging "why did this pair not trade?" requires grepping noisy logs.

**Independent Test**: Run unit tests that `begin_scan` + `record` skip/veto/execute and assert ring contents + context correlation.

**Acceptance Scenarios**:

1. **Given** `DECISION_TRACE_LEVEL=compact`, **When** `process_pair` early-returns with a typed reason, **Then** a DecisionEvent is recorded with that reason and current context ids.
2. **Given** `DECISION_TRACE_LEVEL=off`, **When** `record` is called, **Then** the ring buffer is unchanged.
3. **Given** routine `below_entry_threshold` / `market_closed` skips in compact mode, **When** recorded, **Then** they are omitted (verbose mode includes them).

### User Story 2 — Promote on anomaly + export incident pack (Priority: P1)

When an anomaly reason is recorded, nearby trail events are promoted for retention. An operator (or Cursor/Hermes) exports a pack by `signal_id`, `scan_id`, or last anomaly.

**Why this priority**: Incident packs are the handoff artifact for AI debugging without dumping full journals.

**Independent Test**: `scripts/export_incident_pack.py --last-anomaly` writes `manifest.json`, `trail.jsonl`, `summary.md`, `AGENT_HINT.md` under `data/incident_packs/`.

**Acceptance Scenarios**:

1. **Given** an anomaly event in the ring, **When** export runs with `--last-anomaly`, **Then** the pack includes the anomaly and correlated events.
2. **Given** a `signal_id`, **When** export runs, **Then** `AGENT_HINT.md` instructs joining existing `AgentReasoning.trace_id` / `TradeJournal.signal_id` (no journal duplication).

### User Story 3 — Secret scrubbing (Priority: P2)

Inputs and exported JSON never leak API keys, tokens, passwords, or secrets (reuse scrub patterns from `agent_log_service`).

**Independent Test**: Unit test records inputs containing `api_key` / `password` and asserts `[REDACTED]` in ring + export.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a singleton `DecisionRecorder` with `begin_scan`, `record`, promote helpers, and export helpers.
- **FR-002**: System MUST bind `scan_id` / `pair_id` / `signal_id` via contextvars and include breadcrumb path when available.
- **FR-003**: System MUST keep an in-memory ring buffer (`DECISION_TRACE_RING_SIZE`); MVP MUST NOT perform sync DB I/O on the hot path.
- **FR-004**: System MUST honor `DECISION_TRACE_LEVEL=compact|verbose|off` (default `compact`).
- **FR-005**: Monitor scan loop MUST call `begin_scan`; `process_pair` MUST `record` at typed skip/veto/execute/anomaly branch points, reusing existing reason codes.
- **FR-006**: Export script MUST write packs under `data/incident_packs/` with scrubbed trail + agent hints; MUST NOT duplicate AgentReasoning / TradeJournal rows.
- **FR-007**: Sensitive input keys MUST be scrubbed using the same sensitive-key pattern family as `agent_log_service`.

### Key Entities

- **DecisionEvent**: `{ts, level, scan_id, pair_id?, signal_id?, stage, outcome, reason, inputs, path}`
- **Incident Pack**: directory with `manifest.json`, `trail.jsonl`, `summary.md`, `AGENT_HINT.md`

## Success Criteria *(mandatory)*

- Focused unit tests pass for redaction, ring overflow, record+export.
- Operator can export a pack without restarting the bot process when using the in-process recorder (script documents attaching to live buffer / last-exported snapshot).
- Phase 2 (out of scope): OTel, Postgres decision table, Redis append, mass `logger.info`.

## Phase 2 (explicitly out of scope)

- OpenTelemetry spans
- Postgres `decision_events` table
- Redis stream append (optional later)
- Mass verbose logging on the hot path
