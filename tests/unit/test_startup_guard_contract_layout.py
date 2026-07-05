import ast
from pathlib import Path


STARTUP_CONTRACT_FILES = [
    "test_startup_broker_ledger_mismatch.py",
    "test_startup_database_initialization.py",
    "test_startup_entropy_baselines.py",
    "test_startup_health_checks.py",
    "test_startup_no_scannable_pairs.py",
    "test_startup_unresolved_execution_state.py",
]


def _repo_root() -> Path:
    return Path(__file__).parents[2]


def _unit_file(filename: str) -> Path:
    return _repo_root() / "tests" / "unit" / filename


def _read_unit_file(filename: str) -> str:
    return _unit_file(filename).read_text(encoding="utf-8")


def test_startup_guards_monolith_is_removed_after_contract_split():
    assert not _unit_file("test_startup_guards.py").exists()


def test_startup_contract_tests_construct_monitor_through_shared_factory():
    violations = []

    class Visitor(ast.NodeVisitor):
        def __init__(self, filename):
            self.filename = filename

        def visit_Call(self, node):
            if getattr(node.func, "id", None) == "ArbitrageMonitor":
                violations.append(f"{self.filename}:{node.lineno}")
            self.generic_visit(node)

    for filename in STARTUP_CONTRACT_FILES:
        Visitor(filename).visit(ast.parse(_read_unit_file(filename)))

    assert violations == []


def test_startup_broker_ledger_contract_tests_are_split_from_monolith():
    broker_ledger = _read_unit_file("test_startup_broker_ledger_mismatch.py")

    assert "def test_startup_blocks_when_broker_has_unmanaged_position" in broker_ledger
    assert "def test_startup_broker_ledger_mismatch_reports_read_only_reconciliation_audit" in broker_ledger


def test_startup_unresolved_execution_contract_tests_are_split_from_monolith():
    unresolved = _read_unit_file("test_startup_unresolved_execution_state.py")

    assert "def test_startup_blocks_when_unresolved_execution_state_exists" in unresolved
    assert "def test_startup_treats_close_failed_as_unresolved_execution_state" in unresolved
    assert "def test_startup_treats_failed_submitted_and_partial_states_as_unresolved" in unresolved


def test_startup_entropy_baseline_contract_tests_are_split_from_monolith():
    entropy = _read_unit_file("test_startup_entropy_baselines.py")

    assert "def test_alpaca_paper_broker_startup_skips_live_entropy_baselines" in entropy
    assert "def test_startup_refusal_missing_baselines" in entropy
    assert "def test_startup_success_with_baselines" in entropy


def test_startup_health_check_contract_tests_are_split_from_monolith():
    health_checks = _read_unit_file("test_startup_health_checks.py")

    assert "def test_startup_health_check_failures_use_existing_notification_api" in health_checks


def test_startup_database_initialization_contract_tests_are_split_from_monolith():
    database_init = _read_unit_file("test_startup_database_initialization.py")

    assert "def test_startup_handles_database_initialization_failure" in database_init


def test_startup_no_scannable_pairs_contract_tests_are_split_from_monolith():
    no_scannable = _read_unit_file("test_startup_no_scannable_pairs.py")

    assert "def test_startup_marks_no_scannable_pairs_after_health_checks" in no_scannable


def test_startup_monitor_factory_is_shared_from_conftest():
    conftest = (_repo_root() / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert "def startup_monitor_factory" in conftest
    assert "src.monitor.BrokerageService" in conftest

    for filename in STARTUP_CONTRACT_FILES:
        source = _read_unit_file(filename)
        assert "def _make_startup_monitor" not in source
        assert "def startup_monitor_factory" not in source


def test_startup_health_check_connection_is_shared_from_conftest():
    conftest = (_repo_root() / "tests" / "conftest.py").read_text(encoding="utf-8")
    startup_contracts = [
        "test_startup_health_checks.py",
        "test_startup_no_scannable_pairs.py",
    ]

    assert "def startup_health_check_connection" in conftest

    for filename in startup_contracts:
        source = _read_unit_file(filename)
        assert "class _HealthCheckConnection" not in source
        assert "_HealthCheckConnection(" not in source
        assert "startup_health_check_connection" in source
