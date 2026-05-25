from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parents[2]


def test_startup_broker_ledger_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_startup_guards.py").read_text(encoding="utf-8")
    broker_ledger = (unit_dir / "test_startup_broker_ledger_mismatch.py").read_text(encoding="utf-8")

    assert "def test_startup_blocks_when_broker_has_unmanaged_position" not in monolith
    assert "def test_startup_broker_ledger_mismatch_reports_read_only_reconciliation_audit" not in monolith
    assert "def test_startup_blocks_when_broker_has_unmanaged_position" in broker_ledger
    assert "def test_startup_broker_ledger_mismatch_reports_read_only_reconciliation_audit" in broker_ledger


def test_startup_unresolved_execution_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_startup_guards.py").read_text(encoding="utf-8")
    unresolved = (unit_dir / "test_startup_unresolved_execution_state.py").read_text(encoding="utf-8")

    assert "def test_startup_blocks_when_unresolved_execution_state_exists" not in monolith
    assert "def test_startup_treats_close_failed_as_unresolved_execution_state" not in monolith
    assert "def test_startup_treats_failed_submitted_and_partial_states_as_unresolved" not in monolith
    assert "def test_startup_blocks_when_unresolved_execution_state_exists" in unresolved
    assert "def test_startup_treats_close_failed_as_unresolved_execution_state" in unresolved
    assert "def test_startup_treats_failed_submitted_and_partial_states_as_unresolved" in unresolved


def test_startup_entropy_baseline_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_startup_guards.py").read_text(encoding="utf-8")
    entropy = (unit_dir / "test_startup_entropy_baselines.py").read_text(encoding="utf-8")

    assert "def test_alpaca_paper_broker_startup_skips_live_entropy_baselines" not in monolith
    assert "def test_startup_refusal_missing_baselines" not in monolith
    assert "def test_startup_success_with_baselines" not in monolith
    assert "def test_alpaca_paper_broker_startup_skips_live_entropy_baselines" in entropy
    assert "def test_startup_refusal_missing_baselines" in entropy
    assert "def test_startup_success_with_baselines" in entropy


def test_startup_health_check_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_startup_guards.py").read_text(encoding="utf-8")
    health_checks = (unit_dir / "test_startup_health_checks.py").read_text(encoding="utf-8")

    assert "def test_startup_health_check_failures_use_existing_notification_api" not in monolith
    assert "def test_startup_health_check_failures_use_existing_notification_api" in health_checks


def test_startup_database_initialization_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_startup_guards.py").read_text(encoding="utf-8")
    database_init = (unit_dir / "test_startup_database_initialization.py").read_text(encoding="utf-8")

    assert "def test_startup_handles_database_initialization_failure" not in monolith
    assert "def test_startup_handles_database_initialization_failure" in database_init


def test_startup_no_scannable_pairs_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_startup_guards.py").read_text(encoding="utf-8")
    no_scannable = (unit_dir / "test_startup_no_scannable_pairs.py").read_text(encoding="utf-8")

    assert "def test_startup_marks_no_scannable_pairs_after_health_checks" not in monolith
    assert "def test_startup_marks_no_scannable_pairs_after_health_checks" in no_scannable


def test_startup_monitor_factory_is_shared_from_conftest():
    root = _repo_root()
    conftest = (root / "tests" / "conftest.py").read_text(encoding="utf-8")
    startup_contracts = [
        "test_startup_broker_ledger_mismatch.py",
        "test_startup_database_initialization.py",
        "test_startup_entropy_baselines.py",
        "test_startup_health_checks.py",
        "test_startup_no_scannable_pairs.py",
        "test_startup_unresolved_execution_state.py",
    ]

    assert "def startup_monitor_factory" in conftest
    assert "src.monitor.BrokerageService" in conftest

    for filename in startup_contracts:
        source = (root / "tests" / "unit" / filename).read_text(encoding="utf-8")
        assert "def _make_startup_monitor" not in source
        assert "def startup_monitor_factory" not in source
