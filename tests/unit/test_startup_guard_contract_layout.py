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
