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


def test_monitor_price_guard_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_monitor.py").read_text(encoding="utf-8")
    price_guard = (unit_dir / "test_monitor_price_guard.py").read_text(encoding="utf-8")

    assert "def test_process_pair_missing_price_reports_skip_reason" not in monolith
    assert "def test_process_pair_blocks_impossible_crypto_price_before_kalman" not in monolith
    assert "def test_process_pair_missing_price_reports_skip_reason" in price_guard
    assert "def test_process_pair_blocks_repeated_alpaca_crypto_quote_mid_timestamp_before_kalman" in price_guard


def test_monitor_process_pair_contract_tests_are_split_from_monolith():
    unit_dir = _repo_root() / "tests" / "unit"
    monolith = (unit_dir / "test_monitor.py").read_text(encoding="utf-8")
    process_pair = (unit_dir / "test_monitor_process_pair.py").read_text(encoding="utf-8")

    assert "def test_process_pair_blocks_clipped_kalman_state_before_orchestrator" not in monolith
    assert "def test_process_pair_does_not_mark_failed_execution_as_executed" not in monolith
    assert "def test_process_pair_blocks_clipped_kalman_state_before_orchestrator" in process_pair
    assert "def test_process_pair_does_not_mark_failed_execution_as_executed" in process_pair
