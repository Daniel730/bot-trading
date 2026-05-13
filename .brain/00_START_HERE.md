# Local Brain: Start Here

Last refreshed: 2026-05-07, Europe/Lisbon.

This folder is the repo-local memory for Alpha Arbitrage Bot. Use it before touching code, running audits, or deciding whether the system is safe to trade. It is intentionally opinionated: the goal is to preserve the current mental model, the active safety work, and the things that must not be forgotten between sessions.

## Current Snapshot

- Project: open-source statistical arbitrage / pairs-trading research and execution stack.
- Primary runtime: Python backend in `src/`, React operator console in `frontend/`, Java gRPC execution sidecar in `execution-engine/`.
- Current production verdict: not production-approved.
- Current safe operating posture: paper mode first; live capital remains blocked until audit and soak gates are clean.
- Current active broker reality in code and current docs: `src/services/brokerage_service.py` hard-wires Alpaca as the active provider; Trading 212 / Web3 are legacy-only and unsupported provider settings fail startup.
- Current active audit theme: prove workflow safety around order submission ambiguity, partial fills, close reconciliation, startup recovery, wallet paper mode, and budget/spread guards.
- Current worktree state when this brain was created: dirty, with active edits in execution-safety paths and new untracked audit prompts under `docs/prompts/`.

## Start Order

Read these in order:

1. `00_START_HERE.md` for the operating posture.
2. `01_PROJECT_GOAL.md` for what the project is trying to become.
3. `02_ARCHITECTURE_MAP.md` before changing any code.
4. `03_CRITICAL_WORKFLOWS.md` before auditing or fixing execution logic.
5. `04_AUDIT_LEDGER.md` and `05_BUG_LEDGER.md` before declaring anything safe.
6. `08_TESTING_PROTOCOL.md` before and after changes.
7. `09_DO_NOT_DO.md` before touching live execution, secrets, startup, or recovery code.

## Fresh Verification Snapshot

Historical command from 2026-05-07:

```bash
python -m pytest -q tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py
```

That broad focused slice was red at the time. The named monitor failures from that snapshot were rechecked on 2026-05-13 with:

```bash
python -m pytest -q tests/unit/test_monitor.py::test_execute_trade_success tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fails tests/unit/test_monitor.py::test_close_position_skips_sell_when_broker_has_no_shares tests/unit/test_monitor.py::test_execute_trade_crypto_live_uses_broker tests/unit/test_monitor.py::test_execute_trade_crypto_budget_cap_applied tests/unit/test_monitor.py::test_orchestrator_veto
```

Result:

- 6 passed.

Rechecked tests:

- `tests/unit/test_monitor.py::test_execute_trade_success`
- `tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fails`
- `tests/unit/test_monitor.py::test_close_position_skips_sell_when_broker_has_no_shares`
- `tests/unit/test_monitor.py::test_execute_trade_crypto_live_uses_broker`
- `tests/unit/test_monitor.py::test_execute_trade_crypto_budget_cap_applied`
- `tests/unit/test_monitor.py::test_orchestrator_veto`

Interpretation:

- The named historical monitor failures are no longer active.
- This is not proof of live execution readiness.
- Remaining release gates still live in `10_RELEASE_CHECKLIST.md`.

## Brain File Map

| File | Purpose |
|---|---|
| `00_START_HERE.md` | Entry point and current snapshot |
| `01_PROJECT_GOAL.md` | Mission, non-goals, and safety posture |
| `02_ARCHITECTURE_MAP.md` | Component map and state boundaries |
| `03_CRITICAL_WORKFLOWS.md` | Startup, signal, execution, close, and dashboard flows |
| `04_AUDIT_LEDGER.md` | Audit evidence, active audition, recent test state |
| `05_BUG_LEDGER.md` | Open bugs and risks ranked by danger |
| `06_DECISIONS_ADR.md` | Architecture decision records |
| `07_PROMPT_LIBRARY.md` | Audit prompts and prompt order |
| `08_TESTING_PROTOCOL.md` | Test gates and commands |
| `09_DO_NOT_DO.md` | Guardrails and anti-patterns |
| `10_RELEASE_CHECKLIST.md` | Release and production gates |

## Update Rule

When a future session changes behavior, update the matching brain file in the same change. Do not leave this folder as a fossil. If code and brain disagree, treat the code as the source of truth but treat the disagreement as a documentation bug.
