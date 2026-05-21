from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parents[2]


def test_monitor_execution_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_monitor.py").read_text(encoding="utf-8")
    execution = (unit_dir / "test_monitor_execution.py").read_text(encoding="utf-8")

    assert "def test_execute_trade" not in monolith
    assert "def test_execute_trade_success" in execution
    assert "def test_execute_trade_crypto_budget_cap_applied" in execution


def test_monitor_closing_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_monitor.py").read_text(encoding="utf-8")
    closing = (unit_dir / "test_monitor_closing.py").read_text(encoding="utf-8")

    assert "def test_close_position" not in monolith
    assert "def test_close_position_success" in closing
    assert "def test_close_position_skips_sell_when_broker_has_no_shares" in closing
