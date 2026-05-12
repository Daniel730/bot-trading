#!/usr/bin/env python3
"""Validate paper-mode soak evidence before production approval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_FILE = ROOT / "docs" / "production-soak-evidence.json"
REQUIRED_DRILLS = ("redis", "postgres", "execution_engine")
RUNTIME_ERROR_COUNT_FIELDS = (
    "postgres_auth_failures",
    "postgres_auth_timeouts",
    "grpc_broken_pipe_errors",
    "grpc_connection_reset_errors",
)


def parse_duration_minutes(value: str) -> int:
    raw = value.strip().lower()
    if not raw:
        raise argparse.ArgumentTypeError("duration cannot be empty")
    try:
        if raw.endswith("h"):
            return int(float(raw[:-1]) * 60)
        if raw.endswith("m"):
            return int(float(raw[:-1]))
        return int(float(raw))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("duration must be like 120m, 2h, or 120") from exc


def _passed(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().upper() == "PASS"
    return False


def load_evidence(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        return None, [f"evidence file is missing: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"evidence file is not valid JSON: {exc.msg}"]
    if not isinstance(data, dict):
        return None, ["evidence file must contain a JSON object"]
    return data, []


def validate_evidence(
    evidence: dict[str, Any],
    *,
    minimum_duration_minutes: int,
    require_active_scan: bool,
) -> list[str]:
    errors: list[str] = []

    if evidence.get("paper_mode") is not True:
        errors.append("paper_mode must be true for the soak evidence.")

    duration = evidence.get("soak_duration_minutes")
    if not isinstance(duration, (int, float)) or duration < minimum_duration_minutes:
        errors.append(
            f"soak_duration_minutes must be at least {minimum_duration_minutes}."
        )

    drills = evidence.get("recovery_drills")
    if not isinstance(drills, dict):
        errors.append("recovery_drills must include redis, postgres, and execution_engine results.")
    else:
        for drill in REQUIRED_DRILLS:
            if not _passed(drills.get(drill)):
                errors.append(f"recovery_drills.{drill} must be PASS.")

    if evidence.get("clean_log_window") is not True:
        errors.append("clean_log_window must be true.")

    runtime_error_counts = evidence.get("runtime_error_counts")
    if not isinstance(runtime_error_counts, dict):
        errors.append(
            "runtime_error_counts must include postgres and gRPC transport error counts."
        )
    else:
        for field in RUNTIME_ERROR_COUNT_FIELDS:
            value = runtime_error_counts.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value != 0:
                errors.append(f"runtime_error_counts.{field} must be 0.")

    if evidence.get("post_recovery_smoke_passed") is not True:
        errors.append("post_recovery_smoke_passed must be true.")

    unresolved_rows = evidence.get("unresolved_reconciliation_rows")
    if unresolved_rows != 0:
        errors.append("unresolved_reconciliation_rows must be 0.")

    if require_active_scan:
        active_scan = evidence.get("active_market_scan")
        cycles = active_scan.get("cycles") if isinstance(active_scan, dict) else 0
        pairs_processed = active_scan.get("pairs_processed") if isinstance(active_scan, dict) else 0
        if not isinstance(cycles, int) or cycles <= 0:
            errors.append("active market scan must include at least one completed cycle.")
        if not isinstance(pairs_processed, int) or pairs_processed <= 0:
            errors.append("active market scan must include non-zero pair processing.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed unless production soak evidence satisfies the release gate."
    )
    parser.add_argument(
        "--duration",
        default="2h",
        type=parse_duration_minutes,
        help="Minimum soak duration, e.g. 120m or 2h. Defaults to 2h.",
    )
    parser.add_argument(
        "--require-active-scan",
        action="store_true",
        help="Require at least one active market scan cycle with processed pairs.",
    )
    parser.add_argument(
        "--evidence-file",
        type=Path,
        default=DEFAULT_EVIDENCE_FILE,
        help="Path to structured soak evidence JSON.",
    )
    args = parser.parse_args()

    evidence, load_errors = load_evidence(args.evidence_file)
    errors = load_errors if evidence is None else validate_evidence(
        evidence,
        minimum_duration_minutes=args.duration,
        require_active_scan=args.require_active_scan,
    )

    if errors:
        print("Production soak gate failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Production soak gate OK: required paper-mode soak evidence is present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
