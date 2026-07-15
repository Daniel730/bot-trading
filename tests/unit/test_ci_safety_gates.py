from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"

REQUIRED_SAFETY_TESTS = (
    "tests/unit/test_alpaca_provider.py",
    "tests/unit/test_monitor_execution.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails",
    "tests/unit/test_monitor_execution.py::test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous",
    "tests/unit/test_monitor_execution.py::test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill",
    "tests/unit/test_monitor_execution.py::test_execute_trade_blocks_leg_b_when_leg_a_filled_quantity_is_short",
    "tests/unit/test_monitor_execution.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous",
    "tests/unit/test_monitor_execution.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_partial_fill",
    "tests/unit/test_monitor_closing.py::test_close_position_does_not_close_ledger_until_all_close_orders_fill",
    "tests/unit/test_startup_unresolved_execution_state.py::test_startup_blocks_when_unresolved_execution_state_exists",
    "tests/unit/test_dashboard_wallet_sync.py",
    "tests/unit/test_production_soak_gate.py",
    "tests/unit/test_runtime_alert_rules.py",
    "tests/unit/test_config_broker_routes.py",
)


def test_deploy_workflow_runs_broker_execution_safety_contracts():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "Run broker/execution safety contract tests" in workflow
    assert ".github/workflows/deploy.yml" in workflow
    for test_ref in REQUIRED_SAFETY_TESTS:
        assert test_ref in workflow
    assert "--asyncio-mode=auto" in workflow
