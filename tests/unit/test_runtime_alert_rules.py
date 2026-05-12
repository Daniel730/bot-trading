import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_production_soak_gate.py"


def run_gate(evidence_file: Path):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--duration",
            "2h",
            "--require-active-scan",
            "--evidence-file",
            str(evidence_file),
        ],
        capture_output=True,
        text=True,
    )


def complete_soak_evidence(**overrides):
    evidence = {
        "paper_mode": True,
        "soak_duration_minutes": 180,
        "recovery_drills": {
            "redis": "PASS",
            "postgres": "PASS",
            "execution_engine": "PASS",
        },
        "clean_log_window": True,
        "post_recovery_smoke_passed": True,
        "active_market_scan": {"cycles": 1, "pairs_processed": 12},
        "unresolved_reconciliation_rows": 0,
        "runtime_error_counts": {
            "postgres_auth_failures": 0,
            "postgres_auth_timeouts": 0,
            "grpc_broken_pipe_errors": 0,
            "grpc_connection_reset_errors": 0,
        },
    }
    evidence.update(overrides)
    return evidence


def test_postgres_and_grpc_error_spikes_fail_soak_gate(tmp_path):
    evidence_file = tmp_path / "soak-evidence.json"
    evidence_file.write_text(
        json.dumps(
            complete_soak_evidence(
                runtime_error_counts={
                    "postgres_auth_failures": 2,
                    "postgres_auth_timeouts": 1,
                    "grpc_broken_pipe_errors": 3,
                    "grpc_connection_reset_errors": 1,
                }
            )
        ),
        encoding="utf-8",
    )

    result = run_gate(evidence_file)

    assert result.returncode == 1
    assert "runtime_error_counts.postgres_auth_failures must be 0" in result.stdout
    assert "runtime_error_counts.grpc_broken_pipe_errors must be 0" in result.stdout
