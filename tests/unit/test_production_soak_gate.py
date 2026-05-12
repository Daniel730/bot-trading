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


def test_production_soak_gate_blocks_missing_active_market_scan(tmp_path):
    evidence_file = tmp_path / "soak-evidence.json"
    evidence_file.write_text(
        json.dumps(
            {
                "paper_mode": True,
                "soak_duration_minutes": 180,
                "recovery_drills": {
                    "redis": "PASS",
                    "postgres": "PASS",
                    "execution_engine": "PASS",
                },
                "clean_log_window": True,
                "post_recovery_smoke_passed": True,
                "active_market_scan": {"cycles": 0, "pairs_processed": 0},
                "unresolved_reconciliation_rows": 0,
            }
        ),
        encoding="utf-8",
    )

    result = run_gate(evidence_file)

    assert result.returncode == 1
    assert "active market scan" in result.stdout


def test_production_soak_gate_accepts_complete_evidence(tmp_path):
    evidence_file = tmp_path / "soak-evidence.json"
    evidence_file.write_text(
        json.dumps(
            {
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
            }
        ),
        encoding="utf-8",
    )

    result = run_gate(evidence_file)

    assert result.returncode == 0
    assert "Production soak gate OK" in result.stdout
