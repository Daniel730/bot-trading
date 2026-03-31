---

description: "Dependency-ordered tasks for Correlation Cluster Guard"
---

# Tasks: Correlation Cluster Guard

**Input**: Design documents from `/specs/008-correlation-cluster-guard/`
**Prerequisites**: plan.md (required), spec.md (required), data-model.md

**Organization**: Implementation starts with configuration and core risk logic, then integrates into the monitor.

## Phase 1: Setup & Logic (Phase 1)

**Purpose**: Core infrastructure for sector tracking.

- [ ] T001 Update `src/config.py` with `MAX_SECTOR_EXPOSURE` and `PAIR_SECTORS` map
- [ ] T002 Implement `check_cluster_exposure` in `src/services/risk_service.py` to calculate current sector weights
- [ ] T003 [P] Add unit tests in `tests/unit/test_risk_clusters.py` to verify veto logic for overlapping sectors
- [ ] T004 Implement a `get_active_portfolio_sectors` helper in `src/services/shadow_service.py` (and live equivalent)

---

## Phase 2: Integration & Veto (Phase 2)

**Purpose**: Wire the guard into the monitoring loop.

- [ ] T005 Update the main loop in `src/monitor.py` to check cluster exposure before signal generation
- [ ] T006 Implement a "Pre-emptive Veto" log when a signal is skipped due to sector concentration
- [ ] T007 Update the `AgentState` in `src/agents/orchestrator.py` to include `sector_overlap` in the context passed to the agents

---

## Phase 3: Observability (Phase 3)

**Purpose**: Auditability of cluster decisions.

- [ ] T008 Update `Thought Journal` to log the current sector exposure % at the time of a trade decision
- [ ] T009 Add "Sector Concentration" as a metric in the daily HTML report in `src/services/audit_service.py`
- [ ] T010 [P] Add Telegram `/exposure` command to show current sector allocation via `notification_service.py`

---

## Dependencies & Execution Order

1. **Setup (Phase 1)**: Defines the rules and math.
2. **Integration (Phase 2)**: Enforces the rules in real-time.
3. **Observability (Phase 3)**: Makes the process transparent (Principle III).

### Implementation Strategy

1. **Map the pairs**: Ensure all 20 default pairs have assigned sectors.
2. **Dry Run**: Log "Cluster Warning" without actually vetoing for 24 hours to observe behavior.
3. **Full Enforcement**: Enable the hard veto once thresholds are validated.
